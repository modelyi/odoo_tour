#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 admin 用户分配 CFO 角色
"""
import subprocess

# 通过 psql 直接操作数据库
sql_commands = """
-- 查找 CFO 用户组 ID
SELECT id, name FROM res_groups WHERE name = 'CFO 门户用户';

-- 给 admin 用户添加 CFO 角色
INSERT INTO res_groups_users_rel (gid, uid)
SELECT g.id, u.id
FROM res_groups g, res_users u
WHERE g.name = 'CFO 门户用户' AND u.login = 'admin'
AND NOT EXISTS (
    SELECT 1 FROM res_groups_users_rel r
    WHERE r.gid = g.id AND r.uid = u.id
);

-- 验证
SELECT u.login, g.name as group_name
FROM res_users u
JOIN res_groups_users_rel rel ON u.id = rel.uid
JOIN res_groups g ON rel.gid = g.id
WHERE u.login = 'admin' AND g.name = 'CFO 门户用户';
"""

try:
    result = subprocess.run(
        ['docker', 'exec', '-i', 'tms-db', 'psql', '-U', 'odoo', '-d', 'tms'],
        input=sql_commands,
        text=True,
        capture_output=True
    )

    print("=" * 60)
    print("给 admin 用户分配 CFO 角色")
    print("=" * 60)
    print(result.stdout)

    if result.returncode != 0:
        print("错误:")
        print(result.stderr)
    else:
        print("\n✓ CFO 角色分配成功！")
        print("\n现在可以使用 admin 账号访问 CFO 门户")
        print("访问地址: http://tms.solepro.cloud/my/cfo")

except Exception as e:
    print(f"错误: {e}")
