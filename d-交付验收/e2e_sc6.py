# -*- coding: utf-8 -*-
"""场景6：异常/边界路径（状态机非法流转、收款退回与幂等、应收挂账、催收缺失）"""
from odoo import fields
from odoo.exceptions import UserError, ValidationError

PASS, FAIL, GAP = [], [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def gap(name, detail=''):
    GAP.append(name)
    print('  [GAP ] %s %s' % (name, detail))


def expect_error(name, fn, detail=''):
    try:
        fn()
        check(name, False, '未抛错')
    except (ValidationError, UserError) as e:
        check(name, True, str(e)[:50])
    except Exception as e:
        check(name, False, repr(e)[:80])


print('=== 场景6：异常路径与幂等 ===')

# 1 状态机非法流转
print('\n-- 1 状态机守卫 --')
d = env['tour.plan'].search([('state', '=', 'draft')], limit=1)
print('  draft 团: %s(%s)' % (d.plan_code, d.id))
expect_error('1.1 draft 不可直接出团', d.action_start)
expect_error('1.2 draft 不可完成', d.action_complete)
expect_error('1.3 draft 不可归档', d.action_archive)
expect_error('1.4 非 confirmed 不可进计调', d.action_operate)
c = env['tour.plan'].search([('state', '=', 'confirmed')], limit=1)
expect_error('1.5 已确认团不可直接完成(须先出行)', c.action_complete)
expect_error('1.6 已确认团不可直接归档', c.action_archive)

# 2 收款退回与幂等
print('\n-- 2 收款退回 / 幂等 / 金额校验 --')
plan = env['tour.plan'].browse(88789)
ch = env['tour.pay.channel'].search([('channel_type', '=', 'bank_transfer')], limit=1)
c2 = env['tour.payment.claim'].create({
    'supplier_id': plan.supplier_id.id, 'plan_id': plan.id,
    'pay_date': plan.begin_date, 'pay_money': 100.0,
    'pay_channel_id': ch.id, 'account_id': 6, 'brief': 'UAT-E2E 场景6 退回测试',
})
expect_error('2.1 未认领不可审核', c2.action_audit)
c2.action_claim()
c2.action_claim() if False else None
c2.action_reject()
check('2.2 退回 1→0 且无凭证', c2.claim_state == '0' and not c2.move_id,
      'state=%s move=%s' % (c2.claim_state, c2.move_id.id))
c2.action_claim()
c2.action_audit()
mv = c2.move_id
check('2.3 审核生成凭证', bool(mv) and mv.state == 'posted', '%s' % mv.name)
c2.action_audit()
check('2.4 重复审核幂等(不重复生成)', c2.move_id.id == mv.id and
      env['account.move'].search_count([('id', '=', mv.id)]) == 1)
check('2.5 审核后凭证存在', mv.exists())
# 退回已审核（应被拦截）
expect_error('2.6 已审核不可退回', c2.action_reject)
# 余额字段
check('2.7 收款余额=金额-已使用', abs(c2.balance_money - 100.0) < 0.01, 'balance=%s' % c2.balance_money)
c2.claim_state = '3'
expect_error('2.8 已平账不可重复平账', c2.action_settle)
expect_error('2.9 收款金额必须>0',
             lambda: env['tour.payment.claim'].create({
                 'plan_id': plan.id, 'pay_money': 0.0, 'pay_date': fields.Date.today()}))

# 3 应收挂账（收款未核销存量团应收）
print('\n-- 3 应收核销一致性 --')
acc = env['account.account'].search([('code', '=', '1122.01')], limit=1)
env.cr.execute("""SELECT round(COALESCE(SUM(amount_residual),0),2) FROM account_move_line
  WHERE account_id=%s AND reconciled=false AND amount_residual > 0""", (acc.id,))
open_all = env.cr.fetchone()[0]
env.cr.execute("""SELECT round(COALESCE(SUM(l.amount_residual),0),2) FROM account_move_line l
  JOIN account_analytic_line al ON al.move_line_id=l.id
  WHERE l.account_id=%s AND l.reconciled=false AND l.amount_residual > 0 AND al.account_id=68418""", (acc.id,))
open_88791 = env.cr.fetchone()[0]
print('  全库 1122.01 未核销借方余额=%s; 团 88791 挂账=%s（已收款 8170 进 2203.01，未核销应收）' % (open_all, open_88791))
check('3.1 团 88791 应收挂账存在(收付未打通存量应收)', open_88791 > 0, '挂账=%s' % open_88791)
check('3.2 全库 1122.01 未核销余额>0', open_all > 0, '合计=%s' % open_all)
p891 = env['tour.plan'].browse(88791)
gap('3.3 团发票关联表为空 → 收款无从核销应收',
    'tour_invoice_plan_rel=0 条；claim 无 claim_line_ids 明细无法核销发票 → 存量团应收只能靠人工核销')
print('  台账应收余额(业务快照 sum_un_pay)=%s  vs 记账应收挂账=%s' % (p891.sum_un_pay, open_88791))

# 4 分佣边界
print('\n-- 4 分佣边界 --')
guide = env['tour.guide'].browse(6525)
expect_error('4.1 佣金金额为0不可计提', lambda: env['tour.commission'].create({
    'plan_id': p891.id, 'guide_id': guide.id, 'guide_share_before_tax': 0.0,
    'commission_total': 0.0}).action_confirm())
cm = env['tour.commission'].create({
    'plan_id': p891.id, 'guide_id': guide.id,
    'commission_total': 500.0, 'guide_share_rate': 50.0, 'guide_share_before_tax': 250.0})
check('4.2 ≤800 元不预扣个税', cm.guide_tax == 0.0 and cm.guide_net_pay == 250.0,
      '个税=%s 实发=%s' % (cm.guide_tax, cm.guide_net_pay))
cm.action_confirm()
cm.action_pay()
pm1 = cm.pay_move_id
cm.action_pay()
check('4.3 发放幂等(pay_move_id 不变)', cm.pay_move_id.id == pm1.id and cm.state == 'paid',
      'pay_move=%s state=%s' % (pm1.name, cm.state))
c4 = env['tour.commission'].create({
    'plan_id': p891.id, 'guide_id': guide.id, 'commission_total': 100.0,
    'guide_share_rate': 50.0, 'guide_share_before_tax': 50.0})
expect_error('4.4 未确认佣金不可发放', c4.action_pay)

# 5 催收/对账/购物数据缺口
print('\n-- 5 相关模块数据缺口 --')
for model, label in (('tour.dunning', '催收台账'), ('tour.reconciliation', '对账'),
                     ('tour.shop.record', '购物记录'), ('tour.shop.agreement', '购物协议'),
                     ('tour.plan.change', '单团变更'), ('tour.guide.loan', '导游借款'),
                     ('tour.guide.real.pay', '导游报账'), ('tour.invoice.deduct.line', '差额扣除明细')):
    if model in env:
        n = env[model].search_count([])
        if n == 0:
            gap('5.x %s 无数据(%s)' % (label, model), '模型已装但 0 条记录，业务链无法用真实数据验证')
        else:
            check('5.x %s 有数据 %d 条' % (label, n), True)
    else:
        gap('5.x %s 模型缺失(%s)' % (label, model), '模型未安装')

print('\n########## 场景6 汇总 ##########')
print('PASS=%d FAIL=%d GAP=%d' % (len(PASS), len(FAIL), len(GAP)))
if FAIL:
    print('FAIL: %s' % FAIL)
if GAP:
    print('GAP: %s' % GAP)
env.cr.commit()
print('[COMMITTED]')
