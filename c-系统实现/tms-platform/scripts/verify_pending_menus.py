# 只读验证脚本：待实施功能占位菜单（通过 odoo shell 运行，不做任何写操作）
from odoo import SUPERUSER_ID

Menu = env['ir.ui.menu']

top = env.ref('tour_base.menu_tms_pending')
print('=== 顶级菜单 ===')
print('id=%s name=%r sequence=%s parent=%s' % (top.id, top.name, top.sequence, top.parent_id.id))
print('groups=%s' % [(g.id, g.name) for g in top.group_ids])
print('action=%r (应为 False)' % top.action)

print('=== 10 个子菜单（应为无 action、名带「（待实施）」）===')
for c in top.child_id.sorted('sequence'):
    print('%s | %r | action=%s | groups=%s' % (c.id, c.name, bool(c.action), c.group_ids.ids))

xmlids = [
    'menu_tms_pending', 'menu_tms_pending_ticket', 'menu_tms_pending_b2b',
    'menu_tms_pending_miniapp', 'menu_tms_pending_alipay', 'menu_tms_pending_oa',
    'menu_tms_pending_visa', 'menu_tms_pending_platform', 'menu_tms_pending_fleet',
    'menu_tms_pending_approval', 'menu_tms_pending_bi',
]
missing = [x for x in xmlids if not env.ref('tour_base.%s' % x, raise_if_not_found=False)]
print('=== xmlid 解析 === missing=%s' % missing)

print('=== 仅超管可见验证 ===')
group_system = env.ref('base.group_system')
print('group_system.id=%s' % group_system.id)
regulars = env['res.users'].search([('share', '=', False), ('id', '!=', SUPERUSER_ID)], limit=5)
for u in regulars:
    has = group_system.id in u.all_group_ids.ids
    print('用户 %r 有效组含 group_system? %s' % (u.login, has))
admin = env['res.users'].browse(SUPERUSER_ID)
print('superuser(admin) 有效组含 group_system? %s' % (group_system.id in admin.all_group_ids.ids))
