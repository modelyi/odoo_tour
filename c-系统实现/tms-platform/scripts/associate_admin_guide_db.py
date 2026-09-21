#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 admin 用户关联导游档案 - 直接数据库操作
"""
import os
import sys

import psycopg2

# 数据库连接参数：口令不写进代码（历史值已随 A0-3 轮换）。
# 本机跑：PGPASSWORD=xxx python3 scripts/…；容器内跑会自动读 Odoo 的 PG* 环境变量。
conn_params = {
    'host': os.environ.get('PGHOST', 'localhost'),
    'port': int(os.environ.get('PGPORT', '5432')),
    'dbname': os.environ.get('PGDATABASE', 'tms'),
    'user': os.environ.get('PGUSER', 'odoo'),
    'password': os.environ.get('PGPASSWORD') or sys.exit('缺少 PGPASSWORD 环境变量（口令在 .env 的 POSTGRES_PASSWORD）'),
}

try:
    # 连接数据库
    conn = psycopg2.connect(**conn_params)
    cur = conn.cursor()

    print("=" * 60)
    print("给 admin 用户关联导游档案")
    print("=" * 60)

    # 获取 admin 用户信息
    cur.execute("""
        SELECT id, name, login, partner_id
        FROM res_users
        WHERE id = 1
    """)
    admin = cur.fetchone()
    print(f"\nAdmin用户:")
    print(f"  ID: {admin[0]}")
    print(f"  姓名: {admin[1]}")
    print(f"  登录: {admin[2]}")
    print(f"  Partner ID: {admin[3]}")

    # 获取导游列表
    cur.execute("""
        SELECT id, name, partner_id
        FROM tour_guide
        ORDER BY id
        LIMIT 5
    """)
    guides = cur.fetchall()

    print(f"\n可用导游数量: {len(guides)}")
    for guide in guides:
        partner_info = guide[2] if guide[2] else 'None'
        print(f"  - ID: {guide[0]}, 姓名: {guide[1]}, Partner: {partner_info}")

    # 选择第一个导游进行关联
    if guides:
        guide = guides[0]
        print(f"\n将导游 {guide[1]} (ID: {guide[0]}) 关联到 admin")

        # 更新导游的 partner_id
        cur.execute("""
            UPDATE tour_guide
            SET partner_id = %s,
                write_date = NOW(),
                write_uid = 1
            WHERE id = %s
        """, (admin[3], guide[0]))

        conn.commit()

        print(f"\n✓ 关联成功！")
        print(f"  导游: {guide[1]} (ID: {guide[0]})")
        print(f"  Partner: {admin[1]} (ID: {admin[3]})")
        print(f"\n现在可以使用 admin 账号访问导游门户了")
        print(f"访问地址: http://tms.solepro.cloud/my/guide")

        # 验证更新
        cur.execute("""
            SELECT id, name, partner_id
            FROM tour_guide
            WHERE id = %s
        """, (guide[0],))
        updated_guide = cur.fetchone()
        print(f"\n验证结果:")
        print(f"  导游: {updated_guide[1]}")
        print(f"  Partner ID: {updated_guide[2]}")
    else:
        print("\n✗ 没有可用的导游档案")

    cur.close()
    conn.close()

    print("\n" + "=" * 60)

except psycopg2.Error as e:
    print(f"\n✗ 数据库错误: {e}")
    if conn:
        conn.rollback()
        conn.close()
except Exception as e:
    print(f"\n✗ 错误: {e}")
    import traceback
    traceback.print_exc()
