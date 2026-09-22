"""在 gate 库里建**一次性**冒烟用户（后台 + 门户各一个），口令随机、只落到 PWFILE
（默认 `/tmp/b0/.smoke_pw`，权限 600），**不落进仓库、不回显**。
跑完由 teardown（teardown_smoke_fixtures.py）删除，不留在库里。

目的：不碰 admin 口令也能真跑一遍控制器（HTTP 路由 + 服务端 QWeb 渲染）。
20 的 `res.users` 有互斥组校验：portal 用户**不能**再叠 `tour_base.group_tour_user`
（`cannot be at the same time in exclusive groups 'Role / Portal', 'Role / User'`）。

跑法（口令来自 shell 注入，不需要 stdin）：
  ... odoo-bin shell -d b1gate8 ... < smoke/mk_smoke_user.py
"""
import os
import secrets

env = env  # noqa: F821  (odoo-bin shell 注入)
U = env['res.users']
G = env.ref
out = []
for login, xml_ids in (
        ('smoke_bot_admin', ['base.group_user', 'base.group_system']),
        ('smoke_bot_portal', ['base.group_portal']),
):
    pw = secrets.token_urlsafe(18)
    old = U.search([('login', '=', login)])
    if old:
        old.unlink()
    gids = []
    for x in xml_ids:
        try:
            gids.append(G(x).id)
        except ValueError:
            print('MISSING_GROUP %s' % x)
    u = U.create({'name': login, 'login': login, 'password': pw,
                  'email': '%s@example.invalid' % login,
                  'group_ids': [(6, 0, gids)]})
    out.append('%s %s %s' % (u.login, pw, ','.join(u.group_ids.mapped('name'))))
path = os.environ.get('PWFILE', '/tmp/b0/.smoke_pw')
with open(path, 'w') as f:
    f.write('\n'.join(out) + '\n')
os.chmod(path, 0o600)
env.cr.commit()
print('SMOKE_USERS_READY %d -> %s' % (len(out), path))
