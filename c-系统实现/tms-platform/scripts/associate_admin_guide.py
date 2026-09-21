#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 admin 用户关联导游档案
"""
import xmlrpc.client

import os
import sys

url = 'http://localhost:8070'
db = 'tms'
username = 'admin'
# 用户口令不写死；跑之前 TMS_ADMIN_PASSWORD=… python3 scripts/…
password = os.environ.get('TMS_ADMIN_PASSWORD') or sys.exit('缺少 TMS_ADMIN_PASSWORD 环境变量')

# 认证
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})
print(f"认证成功，用户ID: {uid}")

models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

# 获取 admin 用户信息
admin_user = models.execute_kw(db, uid, password,
    'res.users', 'read', [uid], {'fields': ['name', 'partner_id']})
print(f"\nAdmin用户: {admin_user[0]['name']}")
print(f"Admin partner_id: {admin_user[0]['partner_id'][0]}")

# 获取导游列表
guides = models.execute_kw(db, uid, password,
    'tour.guide', 'search_read',
    [[]],
    {'fields': ['name', 'partner_id'], 'limit': 5})

print(f"\n可用导游数量: {len(guides)}")
for guide in guides:
    partner_info = guide['partner_id'][1] if guide['partner_id'] else 'None'
    print(f"  - {guide['id']}: {guide['name']} (partner: {partner_info})")

# 选择第一个导游进行关联
if guides:
    guide = guides[0]
    print(f"\n将导游 {guide['name']} (ID: {guide['id']}) 关联到 admin")

    # 更新导游的 partner_id
    result = models.execute_kw(db, uid, password,
        'tour.guide', 'write',
        [[guide['id']], {'partner_id': admin_user[0]['partner_id'][0]}])

    if result:
        print(f"✓ 关联成功！")
        print(f"  导游: {guide['name']}")
        print(f"  Partner: {admin_user[0]['partner_id'][1]} (ID: {admin_user[0]['partner_id'][0]})")
        print(f"\n现在可以使用 admin 账号访问导游门户了")
        print(f"访问地址: {url}/my/guide")
    else:
        print("✗ 关联失败")
else:
    print("\n没有可用的导游档案")
