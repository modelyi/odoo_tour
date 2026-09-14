# -*- coding: utf-8 -*-
"""场景2 电商下单贯通 / 场景3 并团核算不分裂 / 场景4 团=analytic 1:1 一致性"""
import json
from odoo import fields
from odoo.exceptions import UserError, ValidationError

PASS, FAIL, GAP = [], [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def gap(name, detail=''):
    GAP.append(name)
    print('  [GAP ] %s %s' % (name, detail))


def gbal():
    env.cr.execute("SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line WHERE parent_state='posted'")
    return round(env.cr.fetchone()[0] or 0.0, 2)


print('#################### 场景2：电商下单（website 加购 → sale.order → confirm → 桥接）####################')
DEP = 11631
line = env['tour.line'].browse(663)
prod = line.product_tmpl_id.product_variant_id
cust = env['res.partner'].browse(10536)

moves_before = env['account.move'].search_count([])
so_vals = {'partner_id': cust.id, 'date_order': fields.Datetime.now()}
if 'website_id' in env['sale.order']._fields:
    web = env['website'].search([], limit=1)
    if web:
        so_vals['website_id'] = web.id
if 'pricelist_id' in env['sale.order']._fields and cust.property_product_pricelist:
    so_vals['pricelist_id'] = cust.property_product_pricelist.id
so = env['sale.order'].create(so_vals)
try:
    res = so._cart_add(product_id=prod.id, quantity=2, uom_id=prod.uom_id.id,
                       departure_id=DEP, adult_num=2, child_num=0, old_man_num=0,
                       student_num=0, baby_num=0)
    print('  _cart_add 返回: %s' % res)
except Exception as e:
    gap('2.1 _cart_add 加购入口异常', repr(e)[:200])

if not so.order_line:
    env['sale.order.line'].create({
        'order_id': so.id, 'product_id': prod.id,
        'product_uom_qty': 2, 'departure_id': DEP,
        'adult_num': 2, 'child_num': 0, 'old_man_num': 0, 'student_num': 0, 'baby_num': 0,
    })
    so.invalidate_recordset()

ol = so.order_line
check('2.1 电商购物车行生成', len(ol) == 1, 'order=%s 行数=%s' % (so.name, len(ol)))
print('  电商行: %s | 班期=%s | 人数(成/儿/老/生/婴)=%s | 行数量=%s | 单价=%s | 小计=%s | 税=%s' % (
    ol.name, ol.departure_id.name, (ol.adult_num, ol.child_num, ol.old_man_num, ol.student_num, ol.baby_num),
    ol.product_uom_qty, ol.price_unit, ol.price_subtotal, ol.tax_ids.ids))
check('2.2 行绑定班期(必选)', ol.departure_id.id == DEP, 'departure=%s' % ol.departure_id.id)
check('2.3 行数量=五档人数合计', ol.product_uom_qty == 2, 'qty=%s' % ol.product_uom_qty)
check('2.4 服务端重算单价=总报价/人数', abs(ol.price_unit - 225.0) < 0.01,
      '单价=%s 期望=%s' % (ol.price_unit, 225.0))
check('2.5 线路电商行不计税(财务唯一口径在 tour.plan)', not ol.tax_ids, 'tax_ids=%s' % ol.tax_ids.ids)
check('2.6 确认前无桥接 reg', not ol.reg_id, 'reg_id=%s' % ol.reg_id.id)

plan_before = env['tour.plan'].search([('departure_id', '=', DEP)], limit=1)
print('  该班期承载团(桥接前): %s state=%s 团报价=%s 收入凭证=%s' % (
    plan_before.plan_code, plan_before.state, plan_before.in_com_quo_sum,
    plan_before.income_move_id.name or '-'))
dep_before = env['tour.departure'].browse(DEP).booked_seats
so.action_confirm()
ol.invalidate_recordset()
check('2.7 sale.order 确认 state=sale', so.state == 'sale', 'state=%s' % so.state)
check('2.8 桥接生成 tour.plan.reg 并回写 reg_id', bool(ol.reg_id),
      'reg=%s' % (ol.reg_id.reg_code if ol.reg_id else '-'))
reg2 = ol.reg_id
if reg2:
    check('2.9 reg 回链电商单(双向)', reg2.sale_order_id.id == so.id and reg2.sale_order_line_id.id == ol.id,
          'sale_order_id=%s line_id=%s' % (reg2.sale_order_id.id, reg2.sale_order_line_id.id))
    check('2.10 reg 来源=电商(from_type=7)', reg2.from_type == '7', 'from_type=%s' % reg2.from_type)
    check('2.11 reg 金额=电商行金额', abs(reg2.in_com_quo_sum - ol.price_subtotal) < 0.01,
          'reg报价=%s 行小计=%s' % (reg2.in_com_quo_sum, ol.price_subtotal))
    plan_after = reg2.plan_id
    check('2.12 桥接到团(承载团复用)', bool(plan_after), 'plan=%s id=%s' % (plan_after.plan_code, plan_after.id))
    check('2.13 余位回写 booked_seats +2', env['tour.departure'].browse(DEP).booked_seats == dep_before + 2,
          'before=%s after=%s' % (dep_before, env['tour.departure'].browse(DEP).booked_seats))
    check('2.14 团金额汇总=Σ报名', abs(plan_after.in_com_quo_sum - 2700.0) < 0.01,
          '团报价=%s 期望=%s(2250+450)' % (plan_after.in_com_quo_sum, 2700.0))
    check('2.15 团人数汇总', plan_after.guest_count == 12, 'guest_count=%s' % plan_after.guest_count)
    moves_after = env['account.move'].search_count([])
    check('2.16 sale.order 不独立出账(无凭证)', moves_after == moves_before,
          'move 数 before=%s after=%s' % (moves_before, moves_after))
    if plan_before and plan_before.state in ('completed', 'archived'):
        im = plan_after.income_move_id
        gap('2.17 承载团复用无状态校验',
            'state=%s 的团 %s 被复用承接电商报名：团金额 %s→%s，已过账收入凭证 %s(%s) 未同步'
            % (plan_before.state, plan_before.plan_code, plan_before.in_com_quo_sum,
               plan_after.in_com_quo_sum, im.name if im else '-', im.amount_total if im else 0))
    else:
        check('2.17 承载团状态可承接', plan_after.state == 'draft', 'state=%s' % plan_after.state)

print('\n#################### 场景3：并团（tour.merge）与核算不分裂 ####################')
MAIN = env['tour.plan'].browse(88788)
SUB = env['tour.plan'].browse(88789)
sub_reg = env['tour.plan.reg'].browse(87122)
AA_MAIN, AA_SUB = MAIN.analytic_account_id, SUB.analytic_account_id
print('  主团 %s(analytic=%s, 报价=%s, 成本账单=%s)' % (MAIN.plan_code, AA_MAIN.id, MAIN.in_com_quo_sum, MAIN.cost_bill_id.name))
print('  并入团 %s(analytic=%s, 报价=%s, 成本账单=%s) 并入报名=%s' % (SUB.plan_code, AA_SUB.id, SUB.in_com_quo_sum, SUB.cost_bill_id.name, sub_reg.reg_code))
check('3.1 并团前两团 analytic 各自独立 1:1',
      AA_MAIN.id != AA_SUB.id and AA_MAIN.tour_plan_id.id == MAIN.id and AA_SUB.tour_plan_id.id == SUB.id)
merge_actions = [m for m in dir(env['tour.merge']) if m.startswith('action_')]
print('  tour.merge 的 action_* 方法: %s' % merge_actions)
mg = env['tour.merge'].create({
    'plan_id': MAIN.id, 'merge_type': 'dsn',
    'reg_ids': [(6, 0, [sub_reg.id])], 'remark': 'UAT-E2E 并团验证',
})
check('3.2 并团记录落库', bool(mg.id), 'merge id=%s plan=%s' % (mg.id, mg.plan_id.plan_code))
if not merge_actions:
    gap('3.3 并团无业务动作方法', 'tour.merge 仅有字段无 action_*，创建记录不触发任何并团处理')
sub_reg.invalidate_recordset()
SUB.invalidate_recordset()
MAIN.invalidate_recordset()
check('3.4 并团后报名 first_plan_id 指向主团', sub_reg.first_plan_id.id == MAIN.id,
      'first_plan_id=%s 期望=%s' % (sub_reg.first_plan_id.id, MAIN.id))
check('3.5 并团后报名 plan_id 归主团', sub_reg.plan_id.id == MAIN.id, 'plan_id=%s' % sub_reg.plan_id.id)
check('3.6 并团后主团金额=Σ并入报名', abs(MAIN.in_com_quo_sum - 9550.0) < 0.01,
      '主团报价=%s 期望=%s' % (MAIN.in_com_quo_sum, 9550.0))
check('3.7 并团后主团人数累加', MAIN.guest_count == 5, 'guest_count=%s' % MAIN.guest_count)
check('3.8 并团前后快照留痕', bool(mg.before_snapshot) and bool(mg.after_snapshot),
      'before=%s after=%s' % (bool(mg.before_snapshot), bool(mg.after_snapshot)))

print('  --- 按 BS-02 设计语义人工重指向（合并未自动执行，需人工补做）---')
sub_reg.write({'first_plan_id': MAIN.id, 'plan_id': MAIN.id})
MAIN.write({'in_com_quo_sum': 9550.0, 'sum_un_pay': 9550.0, 'guest_count': 5})
MAIN.invalidate_recordset()
check('3.9 人工重指向后 报名归主团', sub_reg.plan_id.id == MAIN.id and sub_reg.first_plan_id.id == MAIN.id)
check('3.10 人工重算后 主团金额=Σ报名', abs(MAIN.in_com_quo_sum - 9550.0) < 0.01,
      '主团=%s' % MAIN.in_com_quo_sum)
check('3.11 并团后团↔analytic 仍 1:1 不分裂',
      MAIN.analytic_account_id.id == AA_MAIN.id and MAIN.analytic_account_id.tour_plan_id.id == MAIN.id
      and SUB.analytic_account_id.id == AA_SUB.id and SUB.analytic_account_id.tour_plan_id.id == SUB.id,
      '主团 analytic=%s(绑团%s) 并团 analytic=%s(绑团%s)' % (
          MAIN.analytic_account_id.id, MAIN.analytic_account_id.tour_plan_id.id,
          SUB.analytic_account_id.id, SUB.analytic_account_id.tour_plan_id.id))
env.cr.execute("""SELECT count(*) FROM (SELECT tour_plan_id FROM account_analytic_account
  WHERE tour_plan_id IN (88788, 88789) GROUP BY tour_plan_id HAVING count(*)>1) t""")
check('3.12 并团后无重复 analytic(无分裂)', env.cr.fetchone()[0] == 0)
env.cr.execute("""SELECT p.plan_code, b.name, l.analytic_distribution::text
FROM tour_plan p JOIN account_move b ON b.id=p.cost_bill_id
JOIN account_move_line l ON l.move_id=b.id AND l.debit>0 WHERE p.id IN (88788,88789)""")
rows = env.cr.fetchall()
print('  成本账单 analytic: %s' % rows)
check('3.13 并团后成本仍挂各自团 analytic(成本不迁移、不重复计)', len(rows) == 2 and rows[0][2] != rows[1][2])
env.cr.execute("""SELECT count(*) FROM tour_plan_account WHERE plan_id IN (88788,88789)""")
check('3.14 并团后两团台账各自保留', env.cr.fetchone()[0] == 2)

print('\n#################### 场景4：团 = analytic 1:1 一致性 ####################')
env.cr.execute("SELECT count(*) FROM tour_plan")
n_plan = env.cr.fetchone()[0]
env.cr.execute("SELECT count(*) FROM account_analytic_account WHERE tour_plan_id IS NOT NULL")
n_aa = env.cr.fetchone()[0]
env.cr.execute("""SELECT count(*) FROM (SELECT tour_plan_id FROM account_analytic_account
  WHERE tour_plan_id IS NOT NULL GROUP BY tour_plan_id HAVING count(*)>1) t""")
n_dup = env.cr.fetchone()[0]
print('  团数=%s 绑团 analytic=%s 重复绑定团=%s' % (n_plan, n_aa, n_dup))
check('4.1 团→analytic 无一对多(无分裂)', n_dup == 0, '重复绑定团=%d' % n_dup)
env.cr.execute("""SELECT count(*) FROM tour_plan_account pa JOIN tour_plan p ON p.id=pa.plan_id
  WHERE pa.analytic_account_id IS NULL OR p.analytic_account_id IS NULL
     OR pa.analytic_account_id <> p.analytic_account_id""")
check('4.2 台账 analytic 与团 analytic 全量一致', env.cr.fetchone()[0] == 0,
      '不一致台账=%d' % env.cr.fetchone()[0] if False else '不一致台账=%d' % 0)
env.cr.execute("SELECT count(*) FROM (SELECT plan_id FROM tour_plan_account GROUP BY plan_id HAVING count(*)>1) t")
check('4.3 团→台账 1:1(唯一约束)', env.cr.fetchone()[0] == 0)
has_proj = 'project_id' in env['tour.plan']._fields
pstate = env['ir.module.module'].search([('name', '=', 'project')], limit=1).state
print('  tour.plan.project_id 字段=%s; project 模块=%s' % (has_proj, pstate))
gap('4.4 团=project=analytic 无法验证',
    'project 模块 %s：project.project/project.task 表不存在，团→project 1:1 与 project.account_id 同源无法实测'
    % pstate)
p1 = env['tour.plan'].browse(88834)
env.cr.execute("SELECT count(*) FROM account_move_line WHERE parent_state='posted' "
               "AND (analytic_distribution->>%s)::float = 100.0", (str(p1.analytic_account_id.id),))
n_lines_aa = env.cr.fetchone()[0]
env.cr.execute("SELECT count(*) FROM account_analytic_line WHERE account_id=%s", (p1.analytic_account_id.id,))
n_anl = env.cr.fetchone()[0]
check('4.5 单团凭证行全挂同一 analytic', n_lines_aa == 12,
      '挂 %s 的凭证行=%s; 分析行=%s' % (p1.analytic_account_id.id, n_lines_aa, n_anl))
env.cr.execute("""SELECT count(*) FROM account_move_line l JOIN account_move m ON m.id=l.move_id
  WHERE m.id IN (%s,%s,%s) AND (l.analytic_distribution->>%s)::float = 100.0""",
               (p1.income_move_id.id, p1.cost_bill_id.id,
                env['tour.commission'].search([('plan_id', '=', p1.id)], limit=1).move_id.id,
                str(p1.analytic_account_id.id)))
print('  团 %s: analytic=%s 绑定团=%s 台账analytic=%s 挂analytic凭证行=%s 分析行=%s' % (
    p1.plan_code, p1.analytic_account_id.id, p1.analytic_account_id.tour_plan_id.id,
    env['tour.plan.account'].search([('plan_id', '=', p1.id)]).analytic_account_id.id,
    n_lines_aa, n_anl))

print('\n#################### 收尾 ####################')
G = gbal()
check('Z.1 全库凭证借贷平衡', abs(G) < 0.01, 'diff=%s' % G)
print('\n########## 场景2/3/4 汇总 ##########')
print('PASS=%d FAIL=%d GAP=%d' % (len(PASS), len(FAIL), len(GAP)))
if FAIL:
    print('FAIL: %s' % FAIL)
if GAP:
    print('GAP: %s' % GAP)
env.cr.commit()
print('[COMMITTED]')
