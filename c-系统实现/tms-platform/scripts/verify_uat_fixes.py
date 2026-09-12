# -*- coding: utf-8 -*-
print("=== UAT 修复验证 ===")

# --- P0: 收款编号自动递增 ---
Claim = env['tour.payment.claim']
c1 = Claim.create({'pay_date': '2026-09-12', 'pay_money': 100.0})
c2 = Claim.create({'pay_date': '2026-09-12', 'pay_money': 200.0})
print('收款1 name =', c1.name)
print('收款2 name =', c2.name)
assert c1.name.startswith('SK-'), '收款1 未用 SK- 前缀'
assert c2.name.startswith('SK-'), '收款2 未用 SK- 前缀'
assert c1.name != c2.name, '两条收款编号相同'
# 清理测试数据
c1.unlink(); c2.unlink()
print('P0 收款编号递增 OK')

# --- P1: 佣金 / 对账单号 ---
Comm = env['tour.commission']
plan = env['tour.plan'].search([], limit=1)
cm = Comm.create({'plan_id': plan.id, 'commission_total': 50.0})
print('佣金 name =', cm.name)
assert cm.name.startswith('YJ-'), '佣金未用 YJ- 前缀'
cm.unlink()

Rec = env['tour.reconciliation']
rc = Rec.create({'verify_type': 'group_tour'})
print('对账 name =', rc.name)
assert rc.name.startswith('DZ-'), '对账未用 DZ- 前缀'
rc.unlink()
print('P1 佣金/对账编号 OK')

# --- P1: 车辆 audit_chk 默认 True + 派车不再拦截 ---
veh = env['tour.vehicle'].search([], limit=1)
print('车辆 audit_chk =', veh.audit_chk, '(licence=%s)' % veh.licence)
assert veh.audit_chk, '车辆 audit_chk 应为 True'

# 新建车辆走模型默认值
new_veh = env['tour.vehicle'].create({
    'name': '川A-TEST99', 'licence': '川A-TEST99', 'driver_name': '测试司机',
    'seat_num': 50,
})
print('新建车辆默认 audit_chk =', new_veh.audit_chk)
assert new_veh.audit_chk, '新建车辆默认 audit_chk 应为 True'
new_veh.unlink()

# 派车 booking 创建（绕过冲突检测，仅验证审核拦截已解除）
Book = env['tour.booking']
bk = Book.with_context(bypass_conflict_check=True).create({
    'plan_id': plan.id,
    'resource_type': 'vehicle',
    'vehicle_id': veh.id,
    'begin_date': '2026-09-13',
    'end_date': '2026-09-15',
})
print('派车 booking 创建成功, id =', bk.id, 'vehicle =', bk.vehicle_id.licence)
bk.unlink()
print('P1 车辆审核/派车 OK')

print('=== 全部验证通过 ===')
