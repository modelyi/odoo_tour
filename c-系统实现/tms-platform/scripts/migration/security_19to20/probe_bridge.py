# -*- coding: utf-8 -*-
"""桥接层行为验收：证明 v3 生成的 ir.access 行带 domain 时，20 在查询期真的按 domain 收窄。

判据（预期）：
  tour.guide      portal 用户 total=2 可见=1（只有 partner_id = 自己 partner 的那条）
  res.partner.bank internal 用户 total=2 可见=1（只有无 employee 关联的那条）
  对照组：superuser 两条都可见（排除"数据本身没建出来"的假阳性）
"""
portal = env.ref('base.group_portal')
internal = env.ref('base.group_user')

u1 = env['res.users'].create({
    'name': 'SEC-TEST portal', 'login': 'sec_test_portal', 'email': 'sec1@example.invalid',
    'group_ids': [(6, 0, [portal.id])],
})
u2 = env['res.users'].create({
    'name': 'SEC-TEST internal', 'login': 'sec_test_internal', 'email': 'sec2@example.invalid',
    'group_ids': [(6, 0, [internal.id])],
})
other = env['res.partner'].create({'name': 'SEC-TEST other'})

Guide = env['tour.guide'].sudo()
g1 = Guide.create({'name': 'SEC-TEST mine', 'guide_code': 'SEC-MINE', 'partner_id': u1.partner_id.id})
g2 = Guide.create({'name': 'SEC-TEST theirs', 'guide_code': 'SEC-THEIRS', 'partner_id': other.id})

Bank = env['res.partner.bank'].sudo()
emp = env['hr.employee'].create({'name': 'SEC-TEST emp', 'user_id': u2.id})
b1 = Bank.create({'partner_id': emp.work_contact_id.id, 'account_number': 'SEC-TEST-EMP-0001'})
b2 = Bank.create({'partner_id': other.id, 'account_number': 'SEC-TEST-OTH-0002'})
env.cr.flush()


def probe(model, uid, ids):
    M = env[model].with_user(uid)
    visible = set(M.search([('id', 'in', ids)]).ids)
    return len(ids), len(visible), sorted(visible - set(ids))


r = {}
r['tour.guide superuser'] = probe('tour.guide', env.ref('base.user_root'), [g1.id, g2.id])
r['tour.guide portal'] = probe('tour.guide', u1.id, [g1.id, g2.id])
r['res.partner.bank superuser'] = probe('res.partner.bank', env.ref('base.user_root'), [b1.id, b2.id])
r['res.partner.bank internal'] = probe('res.partner.bank', u2.id, [b1.id, b2.id])
# 读权限：被 domain 挡掉的那条，read() 应报 AccessError
try:
    env['tour.guide'].with_user(u1.id).browse(g2.id).read(['name'])
    r['tour.guide 读他人'] = '未拦截（FAIL）'
except Exception as e:                                    # noqa: BLE001
    r['tour.guide 读他人'] = type(e).__name__
try:
    env['tour.guide'].with_user(u1.id).browse(g1.id).read(['name'])
    r['tour.guide 读自己'] = 'OK'
except Exception as e:                                    # noqa: BLE001
    r['tour.guide 读自己'] = type(e).__name__ + ': ' + str(e)[:80]

for k, v in r.items():
    print(f'{k:32s} {v}')
