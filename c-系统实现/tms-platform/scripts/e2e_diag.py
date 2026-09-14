# -*- coding: utf-8 -*-
"""E2E 前置诊断：检查在线报名→财务闭环所需的配置与测试数据。"""
print('=== E2E 前置诊断 ===')

# 1. 官网报名所需：已审核线路 + 已发布且未过期的班期（有余位）
Line = env['tour.line']
line = Line.search([('audit_state', '=', 'approved'), ('active', '=', True)], limit=1)
print('approved line:', line.id, line.name if line else None, 'total=%d' % Line.search_count([('audit_state','=','approved')]))

Dep = env['tour.departure']
dep = None
if line:
    dep = Dep.search([('line_id', '=', line.id), ('state', '=', 'published')], order='start_date desc', limit=1)
    print('published departure for line:', dep.id if dep else None,
          'start_date=%s' % (dep.start_date if dep else None),
          'remain_seats=%s' % (dep.remain_seats if dep else None),
          'has get_online_prices=%s' % (hasattr(Dep, 'get_online_prices')))

# 2. 收款渠道
Ch = env['tour.pay.channel']
ch = Ch.search([('channel_type', '=', 'bank_transfer')], limit=1)
print('bank_transfer channel:', ch.id if ch else None, 'all channels:', Ch.search([]).mapped('channel_type'))

BA = env['tour.bank.account']
ba = BA.search([], limit=1)
print('tour.bank.account:', ba.id if ba else None, 'total=%d' % BA.search_count([]))

# 3. 关键科目
AA = env['account.account']
for code in ['1001','1002','1012','2202','2203','2203.01','6401','6001.01','6001.02','6001.03','2221.01','2221.03','2221.07','1122.01','1221.01']:
    a = AA.search([('code','=',code)], limit=1)
    print('account %s -> %s (type=%s)' % (code, a.id if a else 'MISSING', a.account_type if a else '-'))

# 4. 公司纳税人配置
co = env.company
print('company:', co.name, 'taxpayer_type=%s' % co.tour_taxpayer_type,
      'vat_rate=%s' % co.tour_vat_rate, 'levy_rate=%s' % co.tour_vat_levy_rate,
      'diff_tax_enabled=%s' % co.tour_diff_tax_enabled)

# 5. 财务三表定义
FR = env['account.financial.report']
roots = FR.search([('parent_id', '=', False)])
print('financial.report roots:')
for r in roots:
    print('  -', r.name, 'type=%s' % r.type, 'id=%s' % r.id)

# 6. 记账现状
Move = env['account.move']
print('posted moves=%d' % Move.search_count([('state','=','posted')]))
print('in_invoice=%d out_invoice=%d' % (
    Move.search_count([('move_type','=','in_invoice')]),
    Move.search_count([('move_type','=','out_invoice')])))
env.cr.execute("SELECT COALESCE(SUM(debit),0)-COALESCE(SUM(credit),0) FROM account_move_line WHERE parent_state='posted'")
print('posted debit-credit diff=', env.cr.fetchone()[0])

# 7. 序列
Seq = env['ir.sequence']
for c in ['tour.plan.reg.online','tour.plan.online','tour.payment.claim','tour.pay.request']:
    s = Seq.search([('code','=',c)], limit=1)
    print('sequence %s -> %s' % (c, s.id if s else 'MISSING'))

print('=== 诊断结束 ===')
