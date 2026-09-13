# -*- coding: utf-8 -*-
"""
发团计划补迁：tour.plan 的 (line_id, begin_date) 去重 -> tour.departure
修复 UAT S1.3「发团计划关联线路」。

运行方式（宿主机，addons 已挂载 /mnt/extra-addons）：
    docker exec -i tms-odoo odoo shell -d tms \
      --config /etc/odoo/odoo.conf --no-http --dev '' < migrate_departure.py

派生规则（按 tour.plan 分组 line_id + begin_date，排除 void 作废单）：
    start_date   = begin_date
    end_date     = MAX(end_date)
    seats        = SUM(成人数 + 儿童数) = SUM(adult_num + child_num)
    booked_seats = SUM(已报人数) = SUM(guest_count)（0 时回退 成人+儿童）
    state        = 源已出团(operating/completed) 则 ended，否则 published
    price_adult / price_child = tour.line 对应价格字段（源数据全 0，后续 f5 回填）

幂等：自然键 (line_id, start_date) 判重，重跑 created=0。
"""
from collections import defaultdict

BATCH = 500
MIGRATE_CTX = dict(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)


def _gc():
    """提交并释放 ORM 缓存，防止大规模迁移 OOM。"""
    env.cr.commit()
    env.invalidate_all()


def import_departures():
    Dep = env['tour.departure']

    # 幂等：现有自然键 (line_id, start_date)
    existing = set()
    for r in Dep.search_read([], ['line_id', 'start_date']):
        existing.add((r['line_id'][0], str(r['start_date'])))

    # 线路价格（源数据全 0，取 line 字段；后续 f5 成交均价回填）
    line_price = {}
    for l in env['tour.line'].search_read([], ['adult_price', 'child_price']):
        line_price[l['id']] = (l['adult_price'] or 0.0, l['child_price'] or 0.0)

    # 聚合 tour.plan（SQL GROUP BY，避免 8.6 万行进 ORM）
    # seats=Σ成人数+儿童数（含老人/婴儿/学生/导游，保证容量），booked_seats=Σ已报人数(guest_count)。
    # GREATEST 兜底保证 seats>=booked，满足 tour.departure「不超卖」约束。
    env.cr.execute("""
        SELECT line_id, begin_date, MAX(end_date),
               GREATEST(
                 SUM(COALESCE(adult_num, 0) + COALESCE(child_num, 0)
                     + COALESCE(old_man_num, 0) + COALESCE(baby_num, 0)
                     + COALESCE(student_num, 0) + COALESCE(guide_num, 0)),
                 SUM(COALESCE(NULLIF(guest_count, 0),
                              COALESCE(adult_num, 0) + COALESCE(child_num, 0)))
               ) AS seats,
               SUM(COALESCE(NULLIF(guest_count, 0),
                            COALESCE(adult_num, 0) + COALESCE(child_num, 0))) AS booked,
               SUM(CASE WHEN state IN ('operating', 'completed') THEN 1 ELSE 0 END) AS departed
        FROM tour_plan
        WHERE line_id IS NOT NULL
          AND begin_date IS NOT NULL
          AND state != 'void'
        GROUP BY line_id, begin_date
        ORDER BY line_id, begin_date
    """)
    rows = env.cr.fetchall()

    created = skipped = 0
    create_buf = []
    for line_id, begin, end, seats, booked, departed in rows:
        key = (line_id, str(begin))
        if key in existing:
            skipped += 1
            continue
        ap, cp = line_price.get(line_id, (0.0, 0.0))
        create_buf.append({
            'line_id': line_id,
            'start_date': begin,
            'end_date': end,
            'seats': int(seats or 0),
            'booked_seats': int(booked or 0),
            'price_adult': ap,
            'price_child': cp,
            'state': 'ended' if departed else 'published',
            'active': True,
        })
        existing.add(key)
        if len(create_buf) >= BATCH:
            Dep.with_context(**MIGRATE_CTX).create(create_buf)
            created += len(create_buf)
            create_buf.clear()
            _gc()
    if create_buf:
        Dep.with_context(**MIGRATE_CTX).create(create_buf)
        created += len(create_buf)
        create_buf.clear()
        _gc()

    print('[departure] created=%d skipped=%d total=%d' % (created, skipped, created + skipped))
    print('  tour.departure 总数 = %d' % Dep.search_count([]))
    env.cr.execute("SELECT state, COUNT(*) FROM tour_departure GROUP BY state ORDER BY 2 DESC")
    print('  tour.departure 状态分布 = %s' % env.cr.fetchall())


def main():
    import_departures()


if __name__ == '__main__':
    main()
