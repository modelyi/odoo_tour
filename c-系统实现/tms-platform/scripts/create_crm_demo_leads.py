# -*- coding: utf-8 -*-
"""生成 80 条 CRM 线索示例数据，填充 CMO 门户。

分布策略：
- 阶段：New 35% / Qualified 25% / Proposition 20% / Won 12% / Lost 8%
- 来源：官网咨询 / 电话咨询 / 门店来访 / 渠道推荐 / 社交媒体 / 搜索引擎
- 类型：lead 60% / opportunity 40%
- 时间：近 6 个月均匀分布（覆盖 month/quarter/year 报表）
- 省份：覆盖 20+ 省份
- 部分线索关联 tour.plan（lead_id 回链）
"""
import random
import json
import datetime

import psycopg2

DB = 'tms'
DSN = f"dbname={DB} user=odoo password=odoo19dev host=tms-db"

random.seed(20260917)

STAGES = {
    'new': 1,
    'qualified': 2,
    'proposition': 3,
    'won': 4,
}

SOURCES = {
    '官网咨询': None,
    '电话咨询': None,
    '门店来访': None,
    '渠道推荐': 10,
    '社交媒体': 4,
    '搜索引擎': 1,
    '直播推广': None,
    '老客转介': 10,
}

PROVINCES = list(range(875, 909))

NAMES = [
    ('张先生', '13800001%02d' % i) for i in range(1, 30)
] + [
    ('李女士', '13900002%02d' % i) for i in range(1, 20)
] + [
    ('王先生', '15000003%02d' % i) for i in range(1, 15)
] + [
    ('赵女士', '15100004%02d' % i) for i in range(1, 10)
] + [
    ('陈先生', '18600005%02d' % i) for i in range(1, 10)
]

TOUR_NAMES = [
    '丽江大理双飞6日游', '北京故宫长城5日', '成都九寨沟4日',
    '桂林阳朔纯玩5日', '西安兵马俑华清池4日', '厦门鼓浪屿3日',
    '海南三亚自由行5日', '张家界凤凰古城5日', '苏杭上海6日',
    '云南香格里拉梅里8日', '甘青大环线7日', '西藏拉萨林芝8日',
    '新疆喀纳斯禾木7日', '福建土楼厦门4日', '贵州黄果树荔波5日',
]

LEAD_TITLES = [
    '%s咨询%s', '%s想了解%s', '%s预订%s',
    '%s询问%s价格', '%s%s行程', '%s定制%s',
]

COMPANY_NAMES = [
    '阳光旅行社', '畅游天下', '乐途旅游', '飞猪旅行',
    '携程旅游', '同程旅行', '途牛旅游网', '马蜂窝旅游',
    None, None, None, None, None,
]


def random_date(days_back=180):
    start = datetime.datetime.now() - datetime.timedelta(days=days_back)
    delta = datetime.timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return start + delta


def pick_stage():
    r = random.random()
    if r < 0.35:
        return STAGES['new']
    elif r < 0.60:
        return STAGES['qualified']
    elif r < 0.80:
        return STAGES['proposition']
    elif r < 0.92:
        return STAGES['won']
    else:
        return None


def pick_source(cur):
    source_names = list(SOURCES.keys())
    name = random.choice(source_names)
    sid = SOURCES[name]
    if sid is not None:
        return sid
    cur.execute("SELECT id FROM utm_source WHERE name = %s LIMIT 1", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO utm_source (name, create_uid, write_uid, create_date, write_date) "
        "VALUES (%s, 1, 1, now(), now()) RETURNING id",
        (name,),
    )
    return cur.fetchone()[0]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id FROM tour_plan WHERE state IN ('confirmed','operating','completed') ORDER BY RANDOM() LIMIT 20")
    plan_ids = [r[0] for r in cur.fetchall()]

    lead_ids = []
    now = datetime.datetime.now()

    for i in range(80):
        contact, phone = random.choice(NAMES)
        tour = random.choice(TOUR_NAMES)
        title_tpl = random.choice(LEAD_TITLES)
        title = title_tpl % (contact, tour)
        stage_id = pick_stage()
        is_lost = stage_id is None
        source_id = pick_source(cur)
        state_id = random.choice(PROVINCES)
        lead_type = 'opportunity' if random.random() < 0.4 else 'lead'
        create_dt = random_date(180)
        revenue = random.choice([0, 0, random.randint(2, 15) * 1000, random.randint(5, 30) * 1000])
        company = random.choice(COMPANY_NAMES)
        partner_name = company if company else None

        cur.execute(
            """INSERT INTO crm_lead
               (name, type, stage_id, source_id, state_id, active,
                contact_name, partner_name, phone, expected_revenue,
                priority, description,
                create_date, write_date, create_uid, write_uid, company_id)
               VALUES (%s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s,
                       %s, %s,
                       %s, %s, 1, 1, 1)
               RETURNING id""",
            (
                title, lead_type, stage_id if not is_lost else 1, source_id, state_id,
                not is_lost,
                contact, partner_name, phone, revenue if revenue else None,
                str(random.randint(0, 3)),
                f'客户咨询：{tour}\n人数：{random.randint(1,8)}人\n预算：{"待定" if not revenue else f"{revenue}元"}',
                create_dt, create_dt,
            ),
        )
        lead_id = cur.fetchone()[0]
        lead_ids.append(lead_id)

        if is_lost:
            cur.execute(
                "UPDATE crm_lead SET date_closed = %s WHERE id = %s",
                (create_dt + datetime.timedelta(days=random.randint(3, 30)), lead_id),
            )

        if stage_id == STAGES['won']:
            cur.execute(
                "UPDATE crm_lead SET date_closed = %s, won_status = 'won', date_conversion = %s WHERE id = %s",
                (create_dt + datetime.timedelta(days=random.randint(5, 45)), create_dt + datetime.timedelta(days=random.randint(5, 45)), lead_id),
            )

        if stage_id == STAGES['qualified']:
            cur.execute(
                "UPDATE crm_lead SET date_open = %s, date_last_stage_update = %s WHERE id = %s",
                (create_dt + datetime.timedelta(days=random.randint(1, 7)), create_dt + datetime.timedelta(days=random.randint(1, 7)), lead_id),
            )

    if plan_ids:
        linked = random.sample(lead_ids, min(15, len(lead_ids)))
        for lid, pid in zip(linked, plan_ids[:len(linked)]):
            cur.execute("UPDATE tour_plan SET lead_id = %s WHERE id = %s", (lid, pid))

    conn.commit()

    cur.execute("SELECT stage_id, COUNT(*) FROM crm_lead GROUP BY stage_id ORDER BY stage_id")
    print("=== 线索阶段分布 ===")
    stage_names = {1: 'New', 2: 'Qualified', 3: 'Proposition', 4: 'Won'}
    for sid, cnt in cur.fetchall():
        print(f"  {stage_names.get(sid, f'stage_{sid}')}: {cnt}")

    cur.execute("SELECT COUNT(*) FROM crm_lead WHERE active = false")
    print(f"  Lost (inactive): {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM crm_lead")
    print(f"  Total: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM tour_plan WHERE lead_id IS NOT NULL")
    print(f"  Plans linked to leads: {cur.fetchone()[0]}")

    cur.close()
    conn.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
