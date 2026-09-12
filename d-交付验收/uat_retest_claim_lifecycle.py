# -*- coding: utf-8 -*-
# UAT 复测：收款认领闭环 0->1->2->3 + 清理泄漏测试数据
print("=== 收款认领闭环验证 ===")

Claim = env['tour.payment.claim']
plan = env['tour.plan'].browse(420)
cust = env['res.partner'].search([('sup_type', '=', 'customer')], limit=1)
pay_way = env['tour.pay.way'].search([], limit=1)

c = Claim.create({
    'plan_id': plan.id,
    'supplier_id': cust.id,
    'pay_date': '2026-09-12',
    'pay_money': 9999.0,
    'pay_way_id': pay_way.id,
    'brief': 'UAT-复测-认领闭环-临时',
})
print('创建收款:', c.name, '状态=', c.claim_state, '(期望 0 待认领)')
assert c.claim_state == '0', '初始状态应为 0'

# 0 -> 1 认领
c.action_claim()
print('认领后状态=', c.claim_state, '(期望 1 待审核)')
assert c.claim_state == '1', '认领后应为 1'

# 1 -> 2 审核
c.action_audit()
print('审核后状态=', c.claim_state, '(期望 2 已审核)')
assert c.claim_state == '2', '审核后应为 2'

# 2 -> 3 平账
c.action_settle()
print('平账后状态=', c.claim_state, '(期望 3 已平账)')
assert c.claim_state == '3', '平账后应为 3'

print('收款认领闭环 0->1->2->3 OK, 编号=', c.name, '团号=', c.plan_code)
claim_id = c.id
print()

# ============ 清理泄漏测试数据 ============
print("=== 清理测试数据 ===")

# e2e 泄漏
to_clean = []
for m, ids in [
    ('tour.payment.claim', [8]),
    ('tour.commission', [6]),
    ('tour.booking', [31, 32]),
    ('tour.plan.account', [4]),
]:
    recs = env[m].browse(ids).exists()
    if recs:
        names = [getattr(r, 'name', str(r.id)) for r in recs]
        recs.unlink()
        print(f'已删除 {m}: {names}')
    else:
        print(f'{m}: 无记录可删 (ids={ids})')

# 本次闭环测试的收款
env['tour.payment.claim'].browse(claim_id).exists().unlink()
print('已删除闭环测试收款 id=', claim_id)

print()
print("=== 清理后数据核对 ===")
for m in ['tour.line', 'tour.plan', 'tour.plan.reg', 'tour.guide',
          'tour.vehicle', 'tour.bank.account']:
    print(m, '=', env[m].search_count([]))

print('SK-收款残留 =', Claim.search_count([('name', 'like', 'SK-%')]))
print('YJ-佣金残留 =', env['tour.commission'].search_count([('name', 'like', 'YJ-%')]))
print('DZ-对账残留 =', env['tour.reconciliation'].search_count([('name', 'like', 'DZ-%')]))
print('BK-计调残留 =', env['tour.booking'].search_count([('name', 'like', 'BK-%')]))
print('单团核算残留 =', env['tour.plan.account'].search_count([]))
print('=== 完成 ===')
