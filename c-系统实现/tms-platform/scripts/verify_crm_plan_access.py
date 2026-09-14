# -*- coding: utf-8 -*-
"""验证：非 CRM 角色（计调）读 tour.plan 不因 lead_id 字段报 AccessError。"""
import datetime

# 1. 造一条带 lead_id 的团 + 关联线索（模拟转团结果）
line = env['tour.line'].search([('active', '=', True)], limit=1)
partner = env['res.partner'].search([], limit=1) or env['res.partner'].create({'name': '测试客户'})
lead = env['crm.lead'].create({
    'name': '访问测试-%s' % datetime.datetime.now().strftime('%H%M%S'),
    'type': 'opportunity', 'line_id': line.id, 'biz_mode': '21',
    'begin_date': '2026-10-01', 'partner_id': partner.id,
})
lead.action_convert_to_plan()
plan = lead.plan_id
assert plan.lead_id.id == lead.id

# 2. 造一个纯计调用户（无 CRM 组）
op_group = env.ref('tour_base.group_tour_operator')
existing = env['res.users'].search([('login', '=', 'tms_op_test_p2')])
if existing:
    op_user = existing
else:
    op_user = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'P2计调测试', 'login': 'tms_op_test_p2',
        'group_ids': [(6, 0, [op_group.id])],
    })
print('op_user groups has crm?', bool(op_user.has_group('crm.group_use_lead')))

# 3. 计调读 tour.plan（含 lead_id 字段值）：不应抛 AccessError
vals = plan.with_user(op_user).read(['plan_name', 'plan_code', 'sales_name', 'lead_id'])
print('OP READ plan ok:', vals[0]['plan_code'], 'lead_id=', vals[0]['lead_id'])

# 4. 确认计调读 crm.lead 确实受限（说明 gate 是必要的）
try:
    lead.with_user(op_user).read(['name'])
    print('OP can read crm.lead: UNEXPECTED')
except Exception as e:
    print('OP crm.lead read blocked (expected):', type(e).__name__)

# 清理
plan.unlink()
lead.unlink()
print('ACCESS CHECK PASSED')
