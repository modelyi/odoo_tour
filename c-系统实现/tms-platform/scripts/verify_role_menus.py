# 角色菜单可见性验证：用 Odoo 自身 _visible_menu_ids() 实测每个角色的可见顶级菜单
# 只读验证 + 临时用户，跑完即删；不改动业务数据，不动运行中的 O2C 过账。
import time

Menu = env['ir.ui.menu']
Users = env['res.users']

root = env.ref('tour_base.menu_tms_root')
# 7 个顶级菜单（parent = 旅行社管理 root）
top = Menu.search([('parent_id', '=', root.id)])
top_ids = {m.id: m.name for m in top}

roles = [
    ('计调',     'tour_base.group_tour_operator'),
    ('财务',     'tour_base.group_tour_finance'),
    ('销售',     'tour_base.group_tour_sales'),
    ('导游管理', 'tour_base.group_tour_guide_manager'),
    ('经理',     'tour_base.group_tour_manager'),
]

suffix = str(int(time.time()))
created = []

def user_closure(gid):
    """组 gid 的完整隐含闭包（直接 + 传递 implied_ids）"""
    seen = {gid}
    stack = [gid]
    while stack:
        cur = stack.pop()
        for h in env['res.groups'].browse(cur).implied_ids.ids:
            if h not in seen:
                seen.add(h)
                stack.append(h)
    return seen

print('=== 1) 各组隐含闭包 ===')
for label, xmlid in roles:
    g = env.ref(xmlid)
    closure = user_closure(g.id)
    names = [env['res.groups'].browse(i).name for i in sorted(closure)]
    print('%s(%s): %s' % (label, g.id, names))

print()
print('=== 2) 菜单 groups 映射（ir.ui.menu.group_ids）===')
for m in top:
    gids = m.group_ids
    print('%s(%s): %s' % (m.name, m.id, [g.name for g in gids] or '(无 groups，人人可见)'))

print()
print('=== 3) 实测 _visible_menu_ids() 各角色可见顶级菜单 ===')
for label, xmlid in roles:
    gid = env.ref(xmlid).id
    login = 'role_verify_%s_%s' % (label, suffix)
    u = Users.create({
        'name': '角色验证-' + label,
        'login': login,
        'group_ids': [(6, 0, [gid])],
    })
    created.append(u.id)
    u.flush_recordset()
    visible = set(Menu.with_user(u)._visible_menu_ids())
    shown = sorted(top_ids[mid] for mid in top_ids if mid in visible)
    print('%s => %s' % (label, shown))

# 清理临时用户
if created:
    Users.browse(created).unlink()
    env.cr.commit()
print()
print('已清理临时用户: %s' % created)
