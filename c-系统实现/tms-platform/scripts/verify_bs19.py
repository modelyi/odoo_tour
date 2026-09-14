# BS-19 验收实测（odoo shell，只读 + 一个开关回归后 rollback）
M = env['tour.plan.account']

print("=== AC-01/AC-04 _read_group 全量聚合 ===")
print(M._read_group([], [], ['income_total:sum', 'cost_total:sum', 'cost_net_total:sum',
                             'profit:sum', 'profit_no_shop:sum', 'profit_tax_incl:sum']))

print("=== AC-07 按业务模式聚合（pivot 可用性） ===")
for row in M._read_group([], ['biz_mode'], ['income_total:sum', 'cost_total:sum',
                                           'profit:sum', 'profit_tax_incl:sum']):
    print(row[0], "inc=%.2f cost=%.2f profit=%.2f ptin=%.2f" % (row[1], row[2], row[3], row[4]))

print("=== AC-07b 按部门 × 渠道聚合 ===")
grp = M._read_group([], ['department_id', 'report_channel_name'],
                    ['profit:sum', 'cost_net_total:sum'])
print("groups:", len(grp), "sample:", grp[:2])

print("=== AC-03 净额法 biz_mode 41：cost_total=0 → profit=income ===")
net = M.search([('biz_mode', '=', 41)])
print("rows", len(net), "Σcost=%.2f" % sum(net.mapped('cost_total')),
      "Σprofit=%.2f" % sum(net.mapped('profit')), "Σincome=%.2f" % sum(net.mapped('income_total')))
print("bad_rows", len(net.filtered(lambda r: abs(r.profit - r.income_total) > 0.011)))

print("=== AC-02 抽样复核（团 7372 / 前 3 行） ===")
for r in M.search([], limit=3) + M.search([('plan_code', '=', 'AQL-210507T-1')], limit=1):
    print(r.plan_code, "mode", r.biz_mode, "inc=%.2f" % r.income_total,
          "cost=%.2f" % r.cost_total, "cost_net=%.2f" % r.cost_net_total,
          "profit=%.2f" % r.profit, "check=%.2f" % round(r.income_total - r.cost_total / 1.06, 2))

print("=== AC-05 开关回归：tour_cost_tax_split=True → cost_net=cost_total（rollback） ===")
co = env.company
before = (co.tour_cost_tax_split, M.search([], limit=1).cost_net_total)
co.tour_cost_tax_split = True
sample = M.search([], limit=5)
print("sample_after:", [(round(r.cost_total, 2), round(r.cost_net_total, 2), round(r.profit, 2))
                        for r in sample])
print("switch_on_sum:", M._read_group([], [], ['cost_net_total:sum', 'profit:sum']))
env.cr.rollback()
print("rolled_back:", env.company.tour_cost_tax_split, "before_was:", before)
