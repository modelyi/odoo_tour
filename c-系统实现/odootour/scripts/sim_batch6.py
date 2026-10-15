# -*- coding: utf-8 -*-
"""批6 仿真数据（购物成本 + 佣金收款 + 退单红冲与个税抵扣 + 收入确认复验）。
DRY_RUN 默认 True；SIM_DRY_RUN=0 正式执行。幂等：PREFIX get_or_create。
odoo shell 不自动提交，正式模式末尾显式 env.cr.commit()。
用法：source .env && docker compose run --rm odoo $(ODOO) $(DBARGS) \
  -d tour20 --no-http shell < scripts/sim_batch6.py  (DRY-RUN)
  SIM_DRY_RUN=0 时同命令正式执行。
"""
import os

PREFIX = '仿真|批6'
DRY_RUN = os.environ.get('SIM_DRY_RUN', '1') == '1'

print('=' * 60)
print(f"批6 仿真 {'DRY-RUN（不落库）' if DRY_RUN else '正式执行'}")


def goc(model, domain, vals):
    rec = env[model].search(domain, limit=1)
    if rec:
        return rec, False
    return env[model].create(vals), True


ADMIN = env.ref('base.user_admin')

# ---- 基础：复用批5 的发团（团队人数已知）与批5 佣金单（已确认、无收款）----
base_shop = env['ta.shop'].search([('remark', 'like', '批5 仿真')], limit=1) \
    or env['ta.shop'].search([], limit=1)
if not base_shop:
    print('!! 未找到既有购物记录，中止；需先有批4/批5 仿真数据')
    raise SystemExit(1)
departure = base_shop.departure_id
print(f"发团计划：{departure.code}（{departure.route_id.name}），状态 {departure.state}")

# ---- 场景 A：P1-4 购物成本（BS-08 §4.4，菜单 4305）----
cost_partner, _ = goc('res.partner', [('name', '=', f'{PREFIX}购物店')],
                      {'name': f'{PREFIX}购物店', 'supplier_rank': 1})
shop_cost, sc_created = goc('ta.shop.cost',
    [('departure_id', '=', departure.id), ('supplier_id', '=', cost_partner.id),
     ('cost_type', '=', 'rebate')],
    {'departure_id': departure.id, 'supplier_id': cost_partner.id,
     'cost_type': 'rebate', 'amount': 500.0,
     'remark': f'{PREFIX}购物回扣（不可从增值税计税依据中扣除）'})
print(f"购物成本：{shop_cost.amount:.2f}（{'新建' if sc_created else '复用'}，"
      f"供应商 {cost_partner.name}）")

# ---- 场景 B：P1-5 佣金收款（AC-17 菜单 3622）----
b5_commission = env['ta.guide.commission'].search([
    ('departure_id', '=', departure.id),
    ('shop_partner_id.name', '=', '仿真|批5购物店')], limit=1)
journal = env['account.journal'].search([
    ('type', 'in', ('bank', 'cash')), ('default_account_id', '!=', False)], limit=1)
if not journal:
    print('!! 无带默认科目的银行/现金日记账，收款场景中止')
else:
    if b5_commission.receipt_ids:
        print(f"佣金单 {b5_commission.name} 已有收款（幂等跳过）："
              f"已收 {b5_commission.received_total:.2f}")
    else:
        take = min(500.0, round(b5_commission.commission_total, 2))
        if take > 0:
            receipt = env['ta.commission.receipt'].create({
                'commission_id': b5_commission.id,
                'date': '2026-10-15',
                'amount': take,
                'journal_id': journal.id,
                'remark': f'{PREFIX} 到账登记',
            })
            m = receipt.move_id
            deb = sum(l.debit for l in m.line_ids)
            cred = sum(l.credit for l in m.line_ids)
            print(f"佣金收款：{receipt.name} {take:.2f}（凭证 {m.name} 借 {deb} 贷 {cred} "
                  f"差 {round(deb - cred, 2)} 状态 {m.state}）")
            print(f"佣金单 {b5_commission.name} 已收 {b5_commission.received_total:.2f}"
                  f" / 总额 {b5_commission.commission_total:.2f}")
        else:
            print('批5 佣金单已收满或缺失，收款场景跳过')

# ---- 场景 C：P0-4 退单红冲 + 个税抵扣（新购物店，避免与场景 B 收款冲突）----
b6_guide, _ = goc('res.partner', [('name', '=', f'{PREFIX}导游')],
                  {'name': f'{PREFIX}导游'})
guide_agr, ga_c = goc('ta.staff.agreement',
    [('staff_type', '=', 'guide'), ('staff_id', '=', b6_guide.id),
     ('state', 'in', ('draft', 'active'))],
    {'staff_type': 'guide', 'staff_id': b6_guide.id, 'tax_type': 'labor',
     'share_rate': 60.0, 'id_number': '****0006'})
if guide_agr.state == 'draft':
    guide_agr.action_active()
print(f"司陪导协议：导游 60% 劳务（{'新建' if ga_c else '复用'}）")

b6_agreement, ba_c = goc('ta.shop.agreement',
    [('shop_partner_id', '=', cost_partner.id), ('state', 'in', ('draft', 'active'))],
    {'shop_partner_id': cost_partner.id, 'begin_date': '2026-01-01',
     'end_date': '2026-12-31', 'base_rate': 20.0})
if b6_agreement.state == 'draft':
    b6_agreement.action_active()
print(f"购物协议：{b6_agreement.name} 基础 20%（{'新建' if ba_c else '复用'}）")

b6_shop, bs_c = goc('ta.shop',
    [('departure_id', '=', departure.id), ('shop_partner_id', '=', cost_partner.id),
     ('total_amount', '=', 8000.0)],
    {'departure_id': departure.id, 'shop_partner_id': cost_partner.id,
     'shop_date': '2026-10-15', 'guest_count': 10, 'total_amount': 8000.0,
     'guide_id': b6_guide.id, 'source': 'sys',
     'remark': f'{PREFIX} 退单红冲与个税抵扣'})
if bs_c:
    print(f"购物记录已创建：{b6_shop.name} 8000.00")
if b6_shop.state == 'draft':
    b6_shop.with_user(ADMIN).action_confirm()
    print(f"购物记录已确认：{b6_shop.name}")

b6_commission = env['ta.guide.commission'].search([
    ('departure_id', '=', departure.id), ('shop_partner_id', '=', cost_partner.id)], limit=1)
if b6_commission and b6_commission.state == 'draft':
    b6_commission.with_user(ADMIN).action_confirm()
    print(f"佣金单已确认：{b6_commission.name} 总额 {b6_commission.commission_total:.2f} "
          f"个税 {b6_commission.tax_amount:.2f}")
if b6_commission:
    guide_row = b6_commission.staff_line_ids.filtered(lambda r: r.staff_type == 'guide')
    print(f"  导游行：税前 {guide_row.share_before_tax:.2f} 个税 {guide_row.tax_amount:.2f} "
          f"实发 {guide_row.net_pay:.2f}")

b6_return, br_c = goc('ta.shop.return',
    [('shop_id', '=', b6_shop.id)],
    {'shop_id': b6_shop.id, 'return_date': '2026-10-15',
     'return_amount': 2000.0, 'reason': f'{PREFIX} 客户退货 2000（红冲演示）'})
if br_c:
    print(f"退单已创建：{b6_return.name} 2000.00")
if b6_return.state == 'draft':
    b6_return.with_user(ADMIN).action_confirm()
    print(f"退单已确认：{b6_return.name}")
    rev_moves = b6_commission.message_ids  # noqa 占位，实际红冲凭证在下
new_commission = env['ta.guide.commission'].search([
    ('departure_id', '=', departure.id), ('shop_partner_id', '=', cost_partner.id),
    ('state', '=', 'draft')], limit=1)
reversal = env['account.move'].search([('ref', 'like', f'退单红冲 {b6_return.name}%')], limit=1)
if reversal:
    deb = sum(l.debit for l in reversal.line_ids)
    cred = sum(l.credit for l in reversal.line_ids)
    print(f"红冲凭证：{reversal.name}（ref={reversal.ref}）借 {deb} 贷 {cred} "
          f"差 {round(deb - cred, 2)} 状态 {reversal.state}")
if new_commission:
    print(f"新草稿佣金单：{new_commission.name} 购物金额 {new_commission.shop_amount:.2f} "
          f"佣金总额 {new_commission.commission_total:.2f}")
deducts = env['ta.guide.commission.tax.deduct'].search([('return_id', '=', b6_return.id)])
for d in deducts:
    print(f"个税抵扣：{d.staff_id.name} 可抵 {d.amount:.2f}（{d.state}）")

# ---- 场景 C2：退单后新草稿佣金单再确认（重确认路径 + 对账视图含购物成本）----
if new_commission and new_commission.state == 'draft':
    new_commission.with_user(ADMIN).action_confirm()
    print(f"新佣金单已重新确认：{new_commission.name} 购物金额 "
          f"{new_commission.shop_amount:.2f} 佣金总额 {new_commission.commission_total:.2f} "
          f"个税 {new_commission.tax_amount:.2f}")
elif new_commission:
    print(f"新佣金单状态 {new_commission.state}（跳过确认）")

# ---- 场景 D：P0-6 收入确认复验（发团日口径，含补记存量）----
rr = env['ta.revenue.recognition'].sudo().search([])
moves = rr.mapped('move_id').filtered(lambda m: m.state == 'posted')
print(f"收入确认记录 {len(rr)} 条，凭证 posted {len(moves)} 张，"
      f"总净额 {sum(rr.mapped('net_amount')):.2f}，总税额 {sum(rr.mapped('tax_amount')):.2f}")

# ---- 不变量：全库 posted 借贷差 = 0 ----
env.flush_all()
env.cr.execute("""
    SELECT round(sum(aml.debit - aml.credit)::numeric, 2)
    FROM account_move_line aml JOIN account_move am ON am.id = aml.move_id
    WHERE am.state = 'posted'
""")
diff = env.cr.fetchone()[0]
print(f"全库 posted 借贷差：{diff}")

if DRY_RUN:
    print('DRY-RUN 结束（已回滚）')
else:
    env.cr.commit()
    print('正式执行完成，已提交')
print('=' * 60)
