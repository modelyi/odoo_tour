# 补齐单团核算台账：为「有分析账户但无台账」的团建 1:1 台账，并物化收入/成本/利润
P = env['tour.plan']
M = env['tour.plan.account']

missing = P.search([('analytic_account_id', '!=', False), ('account_ids', '=', False)])
print("MISSING", len(missing))
for p in missing:
    p._ensure_plan_account()
env.cr.commit()

new_ids = M.search([('plan_id', 'in', missing.ids)]).ids
n = 0
for i in range(0, len(new_ids), 1000):
    recs = M.browse(new_ids[i:i + 1000])
    env.add_to_compute(M._fields['income_total'], recs)
    env.add_to_compute(M._fields['cost_total'], recs)
    env.add_to_compute(M._fields['profit'], recs)
    env.add_to_compute(M._fields['profit_no_shop'], recs)
    env.flush_all()
    env.cr.commit()
    n += len(recs)
    print("PROGRESS", n, "/", len(new_ids))
print("DONE", len(missing), n)
