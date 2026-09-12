# -*- coding: utf-8 -*-
# UAT 复测清理：删除 e2e 泄漏测试数据，显式 commit 确保落库
env.cr.commit()  # 确保干净起点
print("=== 清理 e2e 泄漏数据（显式 commit）===")

targets = [
    ('tour.payment.claim', [8]),
    ('tour.commission', [6]),
    ('tour.booking', [31, 32]),
    ('tour.plan.account', [4]),
]

for m, ids in targets:
    recs = env[m].browse(ids).exists()
    if recs:
        info = [f"{getattr(r, 'name', 'id='+str(r.id))}" for r in recs]
        recs.unlink()
        print(f'已删除 {m}: {info}')
    else:
        print(f'{m}: 无记录 (ids={ids})')

env.cr.commit()
print('已 commit')

print()
print('=== 提交后残留核对 ===')
for m in ['tour.payment.claim', 'tour.commission', 'tour.booking', 'tour.plan.account']:
    print(m, '总数 =', env[m].search_count([]))

print('SK 残留 =', env['tour.payment.claim'].search_count([('name', 'like', 'SK-%')]))
print('YJ 残留 =', env['tour.commission'].search_count([('name', 'like', 'YJ-%')]))
print('DZ 残留 =', env['tour.reconciliation'].search_count([('name', 'like', 'DZ-%')]))
print('BK 残留 =', env['tour.booking'].search_count([('name', 'like', 'BK-%')]))
print('单团核算残留 =', env['tour.plan.account'].search_count([]))
print('=== 完成 ===')
