# -*- coding: utf-8 -*-
"""第二阶段电商闭环验证（事务内，退出自动回滚）。

docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http --dev '' < scripts/verify_website_sale.py
"""
import datetime
from odoo import fields
from odoo.exceptions import ValidationError

PASS, FAIL = [], []


def check(name, cond, detail=''):
    if cond:
        PASS.append(name)
        print('  [PASS] %s %s' % (name, detail))
    else:
        FAIL.append(name)
        print('  [FAIL] %s %s' % (name, detail))


tag = 'WS-%s' % datetime.datetime.now().strftime('%H%M%S')
today = fields.Date.today()
start_d = today + datetime.timedelta(days=30)
end_d = start_d + datetime.timedelta(days=1)

print('=== 0. 测试数据准备 ===')
tmpl = env['product.template'].create({
    'name': '电商测试线路 %s' % tag,
    'type': 'service',
    'list_price': 1000.0,
    'sale_ok': True,
    'is_published': True,
})
line = env['tour.line'].create({
    'product_tmpl_id': tmpl.id,
    'day_num': 2,
    'audit_state': 'approved',
    'child_price': 500.0,
    'old_man_price': 800.0,
    'student_price': 700.0,
    'baby_price': 0.0,
})
dep = env['tour.departure'].create({
    'line_id': line.id,
    'start_date': start_d,
    'end_date': end_d,
    'seats': 50,
    'state': 'published',
    'price_adult': 1000.0,
    'price_child': 500.0,
    'price_old_man': 800.0,
    'price_student': 700.0,
    'price_baby': 0.0,
})
partner = env['res.partner'].create({
    'name': '电商客户 %s' % tag,
    'phone': '13800138000',
})
variant = tmpl.product_variant_id
check('0.1 线路+班期+客户+变体就绪',
      bool(line) and bool(dep) and bool(partner) and bool(variant),
      'line=%s dep=%s variant=%s' % (line.id, dep.id, variant.id))
check('0.2 委托字段可读', line.list_price == 1000.0 and line.name == tmpl.name,
      'list_price=%s name=%r' % (line.list_price, line.name))

print('\n=== 1. 电商加购（_cart_add） ===')
so = env['sale.order'].create({'partner_id': partner.id})
so = so.with_context(skip_cart_verification=True)
res = so._cart_add(
    product_id=variant.id,
    quantity=3,
    departure_id=dep.id,
    adult_num=2, child_num=1, old_man_num=0, student_num=0, baby_num=0,
)
ol = so.order_line.filtered(lambda l: l.departure_id)
QUOTE = round(2 * 1000.0 + 1 * 500.0, 2)  # 2500
check('1.1 生成带班期的订单行', len(ol) == 1 and ol.departure_id.id == dep.id,
      'line_id=%s' % (ol.id if ol else '-'))
check('1.2 五档人数落库', ol.adult_num == 2 and ol.child_num == 1
      and ol.old_man_num == 0 and ol.student_num == 0 and ol.baby_num == 0,
      'adult=%s child=%s' % (ol.adult_num, ol.child_num))
check('1.3 数量 = 总人数', ol.product_uom_qty == 3, 'qty=%s' % ol.product_uom_qty)
check('1.4 单价 = 服务端重算(报价/人数)', abs(ol.price_unit - QUOTE / 3) < 0.01,
      'price_unit=%s 期望=%s' % (ol.price_unit, round(QUOTE / 3, 2)))
check('1.5 行小计 = 报价', abs(ol.price_subtotal - QUOTE) < 0.01,
      'price_subtotal=%s 期望=%s' % (ol.price_subtotal, QUOTE))
check('1.6 线路电商行不计税', not ol.tax_ids, 'tax=%s' % ol.tax_ids.mapped('name'))
check('1.7 订单金额 = 报价(无税)', abs(so.amount_total - QUOTE) < 0.01,
      'amount_total=%s 期望=%s' % (so.amount_total, QUOTE))
# 同班期再次加购 → 复用同一行，人数更新
so._cart_add(product_id=variant.id, quantity=3, departure_id=dep.id,
             adult_num=2, child_num=2, old_man_num=0, student_num=0, baby_num=0)
ol2 = so.order_line.filtered(lambda l: l.departure_id)
check('1.8 同班期复用单行', len(ol2) == 1, 'lines=%s' % len(ol2))
check('1.9 人数更新(儿童1→2)', ol2.child_num == 2 and ol2.product_uom_qty == 4,
      'child=%s qty=%s' % (ol2.child_num, ol2.product_uom_qty))
QUOTE2 = round(2 * 1000.0 + 2 * 500.0, 2)  # 3000
check('1.10 金额随人数重算', abs(ol2.price_subtotal - QUOTE2) < 0.01,
      'price_subtotal=%s 期望=%s' % (ol2.price_subtotal, QUOTE2))

print('\n=== 2. 结账确认 → 桥接 tour.plan.reg ===')
so.action_confirm()
check('2.1 订单确认 sale', so.state == 'sale', 'state=%s' % so.state)
reg = ol2.reg_id
check('2.2 桥接生成报名并回链行', bool(reg) and ol2.reg_id.id == reg.id,
      'reg=%s' % (reg.reg_code if reg else '-'))
check('2.3 报名来源=电商(7)', reg.from_type == '7', 'from_type=%s' % reg.from_type)
plan = reg.plan_id
check('2.4 团=线路+班期', plan.line_id.id == line.id and plan.departure_id.id == dep.id,
      'plan.line=%s plan.dep=%s' % (plan.line_id.id, plan.departure_id.id))
check('2.5 报名人数正确', reg.adult_num == 2 and reg.child_num == 2 and reg.guest_count == 4,
      'adult=%s child=%s guest=%s' % (reg.adult_num, reg.child_num, reg.guest_count))
check('2.6 报名金额正确', abs(reg.in_com_quo_sum - QUOTE2) < 0.01
      and abs(reg.sum_un_pay - QUOTE2) < 0.01,
      'in_com_quo_sum=%s 期望=%s' % (reg.in_com_quo_sum, QUOTE2))
check('2.7 报名回链 sale.order', reg.sale_order_id.id == so.id
      and reg.sale_order_line_id.id == ol2.id,
      'so=%s sol=%s' % (reg.sale_order_id.id, reg.sale_order_line_id.id))
check('2.8 余位回写(50→46)', dep.remain_seats == 46, 'remain=%s' % dep.remain_seats)
check('2.9 团金额汇总=报价', abs(plan.in_com_quo_sum - QUOTE2) < 0.01
      and abs(plan.sum_un_pay - QUOTE2) < 0.01,
      'in_com_quo_sum=%s' % plan.in_com_quo_sum)
# 幂等：桥接方法本身可重入（不重复建报名）
so._create_plan_regs_from_order()
check('2.10 桥接幂等(不重复建报名)',
      env['tour.plan.reg'].search_count([('sale_order_id', '=', so.id)]) == 1,
      'count=%s' % env['tour.plan.reg'].search_count([('sale_order_id', '=', so.id)]))
# 计调不破坏：sale.order 确认不另建 project（计调锚点仍在 tour.plan）
proj = env['project.project'].search([('sale_order_id', '=', so.id)])
check('2.11 sale 确认不另建 project(计调口径不变)',
      not proj, 'projects=%s' % len(proj))

print('\n=== 3. 财务口径：sale.order 不独立出账 ===')
inv = env['account.move'].search([('invoice_origin', '=', so.name), ('move_type', '!=', 'entry')])
posted = so.invoice_ids.filtered(lambda m: m.state == 'posted')
check('3.1 确认不自动开票', not inv and not posted, 'invoice_ids=%s' % len(so.invoice_ids))
check('3.2 sale.order 无独立凭证',
      env['account.move'].search_count([('invoice_origin', '=', so.name)]) == 0,
      'moves=0')

print('\n=== 4. 与 create_online_reg 共享方法（入口2 不破坏） ===')
vals = {
    'supplier_name': '轻量报名 %s' % tag,
    'supplier_user_mobile': '13900139000',
    'adult_num': '1', 'child_num': '0', 'old_man_num': '0',
    'student_num': '0', 'baby_num': '0',
    'remark': '入口2 回归',
}
reg2 = env['tour.plan.reg'].sudo().create_online_reg(line, dep, vals)
check('4.1 入口2 仍可用', bool(reg2) and reg2.from_type == '6',
      'reg=%s from_type=%s' % (reg2.reg_code, reg2.from_type))
check('4.2 入口2 挂同一承载团', reg2.plan_id.id == plan.id,
      'plan=%s' % reg2.plan_id.id)
check('4.3 共享方法单一路径(同一承载团/余位连续)',
      env['tour.plan'].search_count([('departure_id', '=', dep.id)]) == 1
      and dep.remain_seats == 45, 'plans=1 remain=%s' % dep.remain_seats)

print('\n========== 结果 ==========')
print('通过 %d / 失败 %d' % (len(PASS), len(FAIL)))
if FAIL:
    print('失败项: %s' % ', '.join(FAIL))
print('（事务内运行，退出自动回滚，不污染历史数据）')
