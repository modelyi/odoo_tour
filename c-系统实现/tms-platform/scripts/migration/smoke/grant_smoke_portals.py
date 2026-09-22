"""门户冒烟夹具：把各门户自己的准入组**显式**加给冒烟账号，
并给它建一条导游档案（导游门户按 partner 关联，不看组）。

关键事实（也是 B2 的判据）：`_is_*_user()` 判的是 `group in user.group_ids`，
**只认显式成员** —— 靠 implied 继承拿到的组不算。所以搬 19 数据时必须把
`res_groups_users_rel` / `res_groups_implied_rel` 一起搬过去，否则门户页全员 403。

跑法：`... odoo-bin shell -d b1gate8 ... < smoke/grant_smoke_portals.py`
前置：先跑 mk_smoke_user.py（账号 login = smoke_bot_admin）。
"""
env = env  # noqa: F821  (odoo-bin shell 注入)
U = env['res.users']
u = U.search([('login', '=', 'smoke_bot_admin')], limit=1)
if not u:
    raise SystemExit('没有 smoke_bot_admin，先跑 mk_smoke_user.py')
X = env.ref
groups = []
for x in ('tour_cfo_portal.group_cfo_portal', 'tour_coo_portal.group_coo_portal',
          'tour_cmo_portal.group_cmo_portal', 'tour_pm_portal.group_pm_portal',
          'tour_tourist_portal.group_tourist_portal'):
    g = X(x, raise_if_not_found=False)
    if g:
        groups.append(g.id)
    else:
        print('MISSING %s' % x)
u.write({'group_ids': [(4, g) for g in groups]})
print('PORTAL_GROUPS held=%d/%d' % (len([g for g in groups if g in u.group_ids.ids]), len(groups)))

Guide = env['tour.guide']
g = Guide.search([('partner_id', '=', u.partner_id.id)], limit=1)
if not g:
    g = Guide.create({'name': '冒烟导游', 'guide_code': 'GD_SMOKE',
                      'partner_id': u.partner_id.id,
                      # 一眼假占位：这列在 tour_base 里是 AES-256-GCM 加密字段，
                      # 用真值格式的假号容易被误当成现网数据。
                      'id_num': 'SMOKE-ID-0001'})
if not g.audit_chk:
    g.action_audit_approve()
print('GUIDE %s partner=%s audit=%s' % (g.id, g.partner_id.id, g.audit_chk))
env.cr.commit()
