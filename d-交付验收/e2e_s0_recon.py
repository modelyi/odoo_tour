# -*- coding: utf-8 -*-
"""E2E 场景0：数据地貌侦察（只读，不落库）"""

def hdr(t):
    print('\n===== %s =====' % t)

hdr('公司配置')
co = env.company
print('company=%s taxpayer=%s vat=%s levy=%s diff_enabled=%s' % (
    co.name, co.tour_taxpayer_type, co.tour_vat_rate, co.tour_vat_levy_rate, co.tour_diff_tax_enabled))

hdr('已装业务模块')
for m in ('project', 'tour_operation', 'tour_accounting', 'tour_website', 'tour_website_sale',
          'sale', 'website_sale', 'account', 'crm', 'hr'):
    rec = env['ir.module.module'].search([('name', '=', m)], limit=1)
    print('  %-20s %s' % (m, rec.state if rec else 'N/A'))

hdr('tour.plan 状态分布')
env.cr.execute("SELECT state, count(*) FROM tour_plan GROUP BY state ORDER BY 2 DESC")
for r in env.cr.fetchall():
    print('  %-12s %s' % r)

hdr('tour.plan 关键字段覆盖')
env.cr.execute("""
SELECT count(*) total,
  count(analytic_account_id) has_analytic,
  count(*) FILTER (WHERE in_com_quo_sum > 0) quote_gt0,
  count(*) FILTER (WHERE out_sum > 0) cost_gt0,
  count(*) FILTER (WHERE income_move_id IS NOT NULL) income_move,
  count(*) FILTER (WHERE cost_bill_id IS NOT NULL) cost_bill,
  count(*) FILTER (WHERE vat_deduct_move_id IS NOT NULL) vat_deduct,
  count(*) FILTER (WHERE departure_id IS NOT NULL) with_departure
FROM tour_plan""")
print('  ', env.cr.fetchone())

hdr('真实候选团（confirmed/completed，金额完整，有客户）')
env.cr.execute("""
SELECT id, plan_code, plan_name, state, biz_mode, plan_type, guest_count,
       in_com_quo_sum, out_sum, sum_pay_normal, sum_un_pay, sum_pay,
       analytic_account_id, supplier_id, line_id, begin_date, end_date
FROM tour_plan
WHERE in_com_quo_sum > 0 AND out_sum > 0 AND supplier_id IS NOT NULL AND line_id IS NOT NULL
ORDER BY id DESC LIMIT 6""")
rows = env.cr.fetchall()
for r in rows:
    print('  ', r)

hdr('tour.plan.reg 覆盖')
env.cr.execute("""SELECT count(*), count(plan_id), count(first_plan_id),
  count(*) FILTER (WHERE in_com_quo_sum>0), count(*) FILTER (WHERE sale_order_id IS NOT NULL)
FROM tour_plan_reg""")
print('  total/plan/firstplan/quote>0/saleorder =', env.cr.fetchone())

hdr('tour.payment.claim 状态分布 + 有团关联')
env.cr.execute("SELECT claim_state, count(*), round(sum(pay_money)::numeric,2) FROM tour_payment_claim GROUP BY claim_state ORDER BY 1")
for r in env.cr.fetchall():
    print('  ', r)
env.cr.execute("SELECT count(*) FROM tour_payment_claim WHERE plan_id IS NOT NULL")
print('  有 plan_id 的 claim 数 =', env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM tour_payment_claim WHERE move_id IS NOT NULL")
print('  已生成凭证的 claim 数 =', env.cr.fetchone()[0])

hdr('旅行社科目表（含差额扣除标记）')
env.cr.execute("""SELECT code_store::text, id, account_type, tour_vat_deductible
FROM account_account
WHERE code_store::text ~ '^(1001|1002|1012|1122\\.01|1221\\.01|2202|2203|2203\\.01|2221|2241|6001|6401|6603)'
ORDER BY code_store::text""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('日记账')
env.cr.execute("SELECT id, code, name->>'en_US', type, default_account_id FROM account_journal ORDER BY type, id")
for r in env.cr.fetchall():
    print('  ', r)

hdr('支付渠道')
env.cr.execute("SELECT id, name, channel_type, fund_account_code, fund_account_id, journal_id FROM tour_pay_channel ORDER BY id")
for r in env.cr.fetchall():
    print('  ', r)

hdr('收付场景 tour.pay.way')
env.cr.execute("SELECT id, name, is_credit FROM tour_pay_way ORDER BY id")
for r in env.cr.fetchall():
    print('  ', r)

hdr('网站/电商')
env.cr.execute("SELECT count(*) FROM sale_order")
print('  sale_order =', env.cr.fetchone()[0])
env.cr.execute("SELECT state, count(*) FROM sale_order GROUP BY state")
print('  sale_order state =', env.cr.fetchall())
env.cr.execute("SELECT count(*) FROM tour_departure")
print('  tour_departure =', env.cr.fetchone()[0])
env.cr.execute("SELECT state, count(*) FROM tour_departure GROUP BY state")
print('  departure state =', env.cr.fetchall())
env.cr.execute("SELECT count(*) FROM tour_departure WHERE state='published' AND start_date >= CURRENT_DATE")
print('  可售班期(published,未来) =', env.cr.fetchone()[0])

hdr('真实资源：导游/车辆/供应商')
env.cr.execute("SELECT count(*) FILTER (WHERE audit_chk) audited, count(*) total FROM tour_guide")
print('  tour.guide =', env.cr.fetchone())
env.cr.execute("SELECT count(*) FILTER (WHERE audit_chk) audited, count(*) total FROM tour_vehicle")
print('  tour.vehicle =', env.cr.fetchone())
env.cr.execute("SELECT sup_type, count(*) FROM res_partner WHERE sup_type IS NOT NULL GROUP BY sup_type ORDER BY 2 DESC")
print('  供应商类型 =', env.cr.fetchall())

hdr('分佣相关模型数据量')
for t in ('tour_commission', 'tour_shop_agreement', 'tour_shop_record', 'tour_invoice_deduct_line',
          'tour_merge', 'tour_plan_change', 'tour_guide_loan', 'tour_guide_real_pay', 'tour_dunning'):
    env.cr.execute("SELECT count(*) FROM %s" % t)
    print('  %-28s %s' % (t, env.cr.fetchone()[0]))

hdr('已有会计凭证概况')
env.cr.execute("""SELECT move_type, state, count(*) FROM account_move GROUP BY move_type, state ORDER BY 3 DESC""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('全库借贷平衡')
env.cr.execute("SELECT COALESCE(SUM(debit),0)-COALESCE(SUM(credit),0) FROM account_move_line WHERE parent_state='posted'")
print('  diff =', env.cr.fetchone()[0])

hdr('commission 序号')
env.cr.execute("SELECT code, prefix, padding FROM ir_sequence WHERE code LIKE 'tour%' ORDER BY code")
for r in env.cr.fetchall():
    print('  ', r)

print('\n[DONE]')
