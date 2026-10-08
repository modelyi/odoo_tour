# -*- coding: utf-8 -*-
"""批5 仿真数据（多层分成 + 人均线 + 佣金凭证落账）。
DRY_RUN 默认 True；SIM_DRY_RUN=0 正式执行。幂等：PREFIX get_or_create。
odoo shell 不自动提交，正式模式末尾显式 env.cr.commit()。
"""
import os

PREFIX = '仿真|批5'
DRY_RUN = os.environ.get('SIM_DRY_RUN', '1') == '1'

print('=' * 60)
print(f"批5 仿真 {'DRY-RUN（不落库）' if DRY_RUN else '正式执行'}")


def goc(model, domain, vals):
    rec = env[model].search(domain, limit=1)
    if rec:
        return rec, False
    return env[model].create(vals), True


ADMIN = env.ref('base.user_admin')

# 复用批4 购物记录 GW00005 的发团（有已确认订单，团队人数已知）
base_shop = env['ta.shop'].search([], limit=1)
if not base_shop:
    print('!! 未找到既有购物记录（GW00005），中止；需先有批4 仿真数据')
    raise SystemExit(1)
departure = base_shop.departure_id
print(f"发团计划：{departure.code}（{departure.route_id.name}），状态 {departure.state}")

shop_partner, created = goc('res.partner',
    [('name', '=', f'{PREFIX}购物店')],
    {'name': f'{PREFIX}购物店', 'supplier_rank': 1})
guide, _ = goc('res.partner', [('name', '=', f'{PREFIX}导游')], {'name': f'{PREFIX}导游'})
driver, _ = goc('res.partner', [('name', '=', f'{PREFIX}司机')], {'name': f'{PREFIX}司机'})
escort, _ = goc('res.partner', [('name', '=', f'{PREFIX}陪同')], {'name': f'{PREFIX}陪同'})
print(f"购物店：{shop_partner.name}（{'新建' if created else '复用'}）")

# 发团挂司机/陪同（P1-2）
if not departure.driver_id or departure.driver_id != driver:
    departure.driver_id = driver
if not departure.escort_id or departure.escort_id != escort:
    departure.escort_id = escort

# 购物协议（阶梯 0-1000:20 / 1000-5000:25 / 5000+:30）
agreement, ag_created = goc('ta.shop.agreement',
    [('shop_partner_id', '=', shop_partner.id), ('state', 'in', ('draft', 'active'))],
    {'shop_partner_id': shop_partner.id, 'begin_date': '2026-01-01', 'end_date': '2026-12-31',
     'base_rate': 15.0,
     'tier_rule_ids': [
         (0, 0, {'min_per_capita': 0.0, 'max_per_capita': 1000.0, 'commission_rate': 20.0}),
         (0, 0, {'min_per_capita': 1000.0, 'max_per_capita': 5000.0, 'commission_rate': 25.0}),
         (0, 0, {'min_per_capita': 5000.0, 'commission_rate': 30.0})]})
if agreement.state == 'draft':
    agreement.action_active()
print(f"购物协议：{agreement.name}（{'新建' if ag_created else '复用'}）")

# 司陪导协议：导游40%劳务 + 奖金；司机10%劳务；陪同5%工资薪金
staff_specs = [
    ('guide', guide, 40.0, 'labor',
     [(0, 0, {'min_per_capita': 2500.0, 'premium_amount': 300.0}),
      (0, 0, {'min_per_capita': 5000.0, 'premium_amount': 500.0})]),
    ('driver', driver, 10.0, 'labor', []),
    ('escort', escort, 5.0, 'salary', []),
]
for staff_type, partner, share, tax_type, premium_rules in staff_specs:
    agr, ag_c = goc('ta.staff.agreement',
        [('staff_type', '=', staff_type), ('staff_id', '=', partner.id),
         ('state', 'in', ('draft', 'active'))],
        {'staff_type': staff_type, 'staff_id': partner.id, 'tax_type': tax_type,
         'share_rate': share, 'id_number': '****0000',
         'premium_rule_ids': premium_rules})
    if agr.state == 'draft':
        agr.action_active()
    print(f"司陪导协议：{staff_type} {partner.name} {share}% {tax_type}"
          f"（{'新建' if ag_c else '复用'}）")

# 人均线（全局）：基础2000/优秀5000；基础档留空回退协议，标准35/优秀45
pcl, pcl_c = goc('ta.per.capita.line',
    [('line_id', '=', False), ('shop_id', '=', False), ('state', 'in', ('draft', 'active'))],
    {'base_line': 2000.0, 'excellent_line': 5000.0,
     'standard_rate': 35.0, 'excellent_rate': 45.0})
if pcl.state == 'draft':
    pcl.action_active()
print(f"人均线：{pcl.name}（{'新建' if pcl_c else '复用'}）")

# 人均算法（全局）：简单平均 四舍五入 2 位
calc, calc_c = goc('ta.per.capita.calc',
    [('line_id', '=', False), ('shop_id', '=', False), ('state', 'in', ('draft', 'active'))],
    {'calc_mode': 'simple', 'round_way': 'half_up', 'decimal_places': 2})
if calc.state == 'draft':
    calc.action_active()
print(f"人均算法：{calc.name}（{'新建' if calc_c else '复用'}）")

# 购物记录（12000 元；该团该店组内新增，引擎将生成新佣金单）
existing_shop = env['ta.shop'].search([
    ('departure_id', '=', departure.id), ('shop_partner_id', '=', shop_partner.id)])
if existing_shop:
    print(f"购物记录已存在（{existing_shop.mapped('name')}），跳过新建")
    shop = existing_shop[0]
else:
    shop = env['ta.shop'].create({
        'departure_id': departure.id,
        'shop_partner_id': shop_partner.id,
        'shop_date': '2026-10-08',
        'guest_count': 10,
        'total_amount': 12000.0,
        'guide_id': guide.id,
        'source': 'sys',
        'remark': '批5 仿真：多层分成+人均线+凭证落账',
    })
    print(f"购物记录已创建：{shop.name}")

if shop.state == 'draft':
    shop.with_user(ADMIN).action_confirm()
    print(f"购物记录已确认：{shop.name}")

commission = env['ta.guide.commission'].search([
    ('departure_id', '=', departure.id), ('shop_partner_id', '=', shop_partner.id)])
if commission.state == 'draft':
    commission.with_user(ADMIN).action_confirm()
    print(f"佣金单已确认：{commission.name}")

heads = shop._team_heads()
per_capita = shop.per_capita
print(f"团队人数 {heads}，人均购物 {per_capita}")
print(f"佣金总额 {commission.commission_total}，销项税 {commission.commission_tax}")
rows = commission.staff_line_ids
print(f"分成行 {len(rows)} 行：")
for r in rows:
    print(f"  {r.staff_type} {r.staff_id.name}: 比例{r.share_rate}% 税前{r.share_before_tax}"
          f" 奖金{r.premium} 税型{r.tax_type} 个税{r.tax_amount} 实发{r.net_pay}")
print(f"主单：allowance={commission.allowance} tax={commission.tax_amount} "
      f"net={commission.net_amount} 留存={commission.company_retain}")
print(f"税记录 {len(commission.tax_record_ids)} 条")
if commission.move_id:
    m = commission.move_id
    deb = sum(l.debit for l in m.line_ids)
    cred = sum(l.credit for l in m.line_ids)
    print(f"确认凭证 {m.name}（{len(m.line_ids)} 行）借 {deb} 贷 {cred} "
          f"差 {round(deb - cred, 2)} 状态 {m.state}")
else:
    print("!! 无确认凭证")

if DRY_RUN:
    print('DRY-RUN 结束（已回滚）')
else:
    env.cr.commit()
    print('正式执行完成，已提交')
print('=' * 60)
