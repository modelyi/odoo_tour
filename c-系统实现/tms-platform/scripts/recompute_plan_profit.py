# BS-19 存量重算：单团毛利口径（不含税）——一次性回填 store 字段
# 运行：
#   docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < scripts/recompute_plan_profit.py
#
# 背景：profit / profit_no_shop 改公式 + 新增 cost_net_total / profit_tax_incl（均 store=True），
#      存量 82,479 行不会自动回填，须 add_to_compute + flush_all 分批 commit [BS-19 §3.1]。
M = env['tour.plan.account']
FIELDS = ['cost_net_total', 'profit', 'profit_no_shop', 'profit_tax_incl']

ids = M.search([], order='id').ids
total = len(ids)
print("TOTAL", total)

co = env.company
print("RATE_PARAMS", co.tour_taxpayer_type, co.tour_vat_rate, co.tour_vat_levy_rate,
      "COST_TAX_SPLIT", co.tour_cost_tax_split)

BATCH = 2000
done = 0
for i in range(0, total, BATCH):
    recs = M.browse(ids[i:i + BATCH])
    for fname in FIELDS:
        env.add_to_compute(M._fields[fname], recs)
    env.flush_all()
    env.cr.commit()
    done += len(recs)
    print("PROGRESS", done, "/", total, flush=True)

env.flush_all()
print("DONE", done)
print("SUM", env['tour.plan.account']._read_group(
    [], [], ['income_total:sum', 'cost_total:sum', 'cost_net_total:sum',
             'profit:sum', 'profit_no_shop:sum', 'profit_tax_incl:sum']))
