# -*- coding: utf-8 -*-
"""P2 验证脚本：crm.lead 转团 → tour.plan draft + lead_id 回链 + 幂等 + 手工建团。"""
import datetime

CrmLead = env['crm.lead']
TourPlan = env['tour.plan']

# 1. 取一个线路 + 客户
line = env['tour.line'].search([('active', '=', True)], limit=1)
assert line, '无 tour.line 数据'
partner = env['res.partner'].search([], limit=1)
if not partner:
    partner = env['res.partner'].create({'name': '测试客户CRM'})

# 2. 创建 lead（含 line_id + biz_mode + partner）
lead = CrmLead.create({
    'name': '测试线索-转团-%s' % datetime.datetime.now().strftime('%H%M%S'),
    'type': 'opportunity',
    'line_id': line.id,
    'biz_mode': '21',
    'begin_date': '2026-10-01',
    'from_type': '5',
    'partner_id': partner.id,
})
print('LEAD id=%s line=%s biz_mode=%s begin=%s from_type=%s partner=%s' % (
    lead.id, lead.line_id.id, lead.biz_mode, lead.begin_date, lead.from_type, lead.partner_id.id))

# 3. 转团
lead.action_convert_to_plan()
plan = lead.plan_id
assert plan, '转团未生成 tour.plan'
print('PLAN id=%s code=%s name=%s state=%s' % (plan.id, plan.plan_code, plan.plan_name, plan.state))
print('  MAP line=%s biz_mode=%s supplier=%s sales_name=%r from_type=%s begin=%s lead_id=%s' % (
    plan.line_id.id, plan.biz_mode, plan.supplier_id.id, plan.sales_name,
    plan.from_type, plan.begin_date, plan.lead_id.id))
assert plan.state == 'draft'
assert plan.line_id.id == line.id
assert plan.biz_mode == '21'
assert plan.supplier_id.id == partner.id
assert plan.sales_name == (lead.user_id.name if lead.user_id else False)
assert plan.from_type == '5'
assert str(plan.begin_date) == '2026-10-01'
assert plan.lead_id.id == lead.id

# 4. 幂等：再点转团不重复建团
before = TourPlan.search_count([('lead_id', '=', lead.id)])
lead.action_convert_to_plan()
after = TourPlan.search_count([('lead_id', '=', lead.id)])
print('IDEMPOTENT before=%s after=%s' % (before, after))
assert before == after == 1

# 5. 手工直接建团路径不受影响（lead_id 可空）
manual_code = 'MAN-%s' % datetime.datetime.now().strftime('%Y%m%d%H%M%S')
manual = TourPlan.create({
    'plan_code': manual_code,
    'plan_name': '手工建团测试',
    'line_id': line.id,
    'biz_mode': '12',
    'begin_date': '2026-11-01',
    'end_date': '2026-11-03',
    'state': 'draft',
})
print('MANUAL plan id=%s code=%s lead_id=%s' % (manual.id, manual.plan_code, manual.lead_id.id))
assert not manual.lead_id

# 清理测试数据
plan.unlink()
manual.unlink()
lead.unlink()
print('ALL CHECKS PASSED')
