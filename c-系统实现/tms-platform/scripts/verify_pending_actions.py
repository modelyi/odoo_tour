# 只读验证（除临时用户创建/删除外无业务写操作）：
# 待实施功能虚菜单 → 占位 action 挂载结果 + _visible_menu_ids 可见性
from odoo import SUPERUSER_ID

Menu = env['ir.ui.menu']
Users = env['res.users']

PENDING = [
    'menu_tms_pending', 'menu_tms_pending_ticket', 'menu_tms_pending_b2b',
    'menu_tms_pending_miniapp', 'menu_tms_pending_alipay', 'menu_tms_pending_oa',
    'menu_tms_pending_visa', 'menu_tms_pending_platform', 'menu_tms_pending_fleet',
    'menu_tms_pending_approval', 'menu_tms_pending_bi',
]

menus = env['ir.ui.menu']
ids = []
for x in PENDING:
    m = env.ref('tour_base.%s' % x, raise_if_not_found=False)
    if m:
        ids.append(m.id)
        menus |= m

print('=== 1) action 挂载（11 个菜单，应全部非空且为 act_url → /tutor/pending）===')
for m in menus.sorted('id'):
    a = m.action
    if a:
        info = (a.id, a._name, getattr(a, 'url', ''))
    else:
        info = None
    print('%s | %r | action=%r | groups=%s' % (m.id, m.name, info, m.group_ids.ids))

print()
print('=== 2) 超管 _visible_menu_ids 可见性 ===')
visible = set(Menu._visible_menu_ids())
targets = set(ids)
print('target ids=%s' % sorted(targets))
print('visible 中含全部 target? %s (缺失: %s)' % (targets <= visible, sorted(targets - visible)))

print()
print('=== 3) 普通角色用户不可见（无 group_system）===')
group_system = env.ref('base.group_system').id
regular = Users.search([('share', '=', False), ('id', '!=', SUPERUSER_ID)], limit=1)
if regular:
    has_gs = group_system in regular.all_group_ids.ids
    vis = set(Menu.with_user(regular)._visible_menu_ids())
    overlap = targets & vis
    print('user=%r login=%r 含 group_system=%s' % (regular.name, regular.login, has_gs))
    print('该用户可见的待实施菜单 ids: %s' % sorted(overlap))
    print('结果: 普通用户不可见 = %s' % (not overlap))
else:
    print('无普通用户，跳过普通角色校验')

print()
print('=== 4) 临时用户（仅 base.group_user，无 group_system）复核 ===')
import time
suffix = str(int(time.time()))
tmp_login = 'pending_verify_%s' % suffix
tmp = Users.create({
    'name': '待实施菜单可见性验证',
    'login': tmp_login,
    'group_ids': [(6, 0, [env.ref('base.group_user').id])],
})
tmp.flush_recordset()
try:
    vis_tmp = set(Menu.with_user(tmp)._visible_menu_ids())
    overlap_tmp = targets & vis_tmp
    print('临时用户 %r 可见待实施菜单 ids: %s' % (tmp_login, sorted(overlap_tmp)))
    print('结果: 普通用户不可见 = %s' % (not overlap_tmp))
finally:
    tmp.unlink()
    env.cr.commit()
    print('已清理临时用户 id=%s' % tmp.id)
