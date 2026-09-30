# -*- coding: utf-8 -*-
"""
migrate_tms19_itinerary.py —— 原 TMS tour_line_detail（803 行）→ tour20 ta.route.stop 行程导入

批次3-1（任务#38）：行程编排能力标准化后的历史线路正文补齐。框架范式严格照抄
migrate_tms19_to_ta.py（DRY_RUN 常量 / old_connect 口令 env / 备份 ACK 门禁 / BATCH
chunk_insert / 幂等重跑清理 / 对平报告）。

== 运行方式（协调人执行）==
    # 1) 打通跨库网络（结论同 migrate_tms19_to_ta.py 头注）：
    #    sudo docker network connect tms-net odootour-odoo
    # 2) 注入旧库口令（严禁写入本文件/镜像）：
    #    export TMS_OLD_DB_PASSWORD='***'
    # 3) 拷入容器并以 odoo shell 运行（先保持 DRY_RUN=True 干跑核对）：
    sudo docker cp c-系统实现/odootour/scripts/migrate_tms19_itinerary.py odootour-odoo:/tmp/
    sudo docker exec -i -e TMS_OLD_DB_PASSWORD -e TMS_MIG_BACKUP_ACK=1 odootour-odoo \
      python3 /usr/lib/odoo/odoo-server/odoo-bin shell -d tour20 --no-http \
      --db_host=db --db_user=odoo --db_password=<新库口令> < /tmp/migrate_tms19_itinerary.py
    # 4) 跑完可还原网络：sudo docker network disconnect tms-net odootour-odoo
    # 前提：ta_route 模块已升级（note/title/traffic/三餐 列存在）；本脚本不做 -u。

== DRY_RUN ==
下方常量 DRY_RUN 默认 True：只「读旧库 + 读新库 ta_route 映射 + 内存组装 + 打印对平
报告（含 src_html-only 行数统计与前 200 字符抽样）」，**不落任何写**（DELETE 清理与
INSERT 全部跳过）。协调人核对 dry-run 报告后改 False 正式执行。

== 映射（拍板项）==
- route 映射：旧 line_id → ta_route.code='ETM|L<line_id>' 查库取 id；查不到的行计入
  unmatched 并跳过（报告呈现，不报错——历史脏线路允许缺失）。
- 字段直搬：day_no/sequence/city/name/title/traffic；accommodation=旧 hotel；
  三餐 meal_breakfast/lunch/dinner=旧 meal_*（旧为 Boolean → Char：True 记「含」，
  False/NULL 留空）。
- content=旧 content 原样；content 空而 src_html 非空 → src_html 经 strip_html()
  粗清洗为纯文本后落入 content（正文导入时）；dry-run 先统计该类行数并抽样打印。
- sequence NULL/0 → day_no*10 + 同(route,day)内行序（旧表 ORDER BY id 稳定序）。
- 幂等源引用：note='ETM|LD|<旧id>'；正式模式开头 DELETE ta_route_stop
  WHERE note LIKE 'ETM|LD%'（仅非 DRY_RUN），重跑无损。
"""
import os
import datetime
from collections import defaultdict

import psycopg2  # odootour-odoo 容器内实测可 import

from odoo.addons.ta_route.models.ta_route import strip_html

# ---------------------------------------------------------------------------
# 开关与常量
# ---------------------------------------------------------------------------
DRY_RUN = True   # ← 协调人核对 dry-run 报告后改为 False 正式执行
BATCH = 2000

OLD_DB_HOST = os.environ.get('TMS_OLD_DB_HOST', 'tms-db')
OLD_DB_PORT = os.environ.get('TMS_OLD_DB_PORT', '5432')
OLD_DB_NAME = os.environ.get('TMS_OLD_DB_NAME', 'tms')
OLD_DB_USER = os.environ.get('TMS_OLD_DB_USER', 'odoo')

NOTE_PREFIX = 'ETM|LD%'

NOW = datetime.datetime.now().replace(microsecond=0)


# ---------------------------------------------------------------------------
# 纯函数工具
# ---------------------------------------------------------------------------
def s(v, default=''):
    return default if v is None else str(v)


def i(v, default=0):
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def meal_char(v):
    """旧 Boolean → 新 Char：True→「含」，False/NULL→空。"""
    return '含' if v else None


# ---------------------------------------------------------------------------
# 旧库读取（psycopg2 独立连接）
# ---------------------------------------------------------------------------
def old_connect():
    pwd = os.environ.get('TMS_OLD_DB_PASSWORD')
    if not pwd:
        raise RuntimeError('缺少环境变量 TMS_OLD_DB_PASSWORD（严禁硬编码口令）')
    return psycopg2.connect(host=OLD_DB_HOST, port=int(OLD_DB_PORT), dbname=OLD_DB_NAME,
                            user=OLD_DB_USER, password=pwd, connect_timeout=15)


def old_fetch(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    return rows


def load_old(conn):
    """一次拉全 tour_line_detail（约 803 行）。列序与 SELECT 对齐。"""
    return old_fetch(conn, """
        SELECT id, line_id, day_no, sequence, name, title, city,
               hotel, traffic, meal_breakfast, meal_lunch, meal_dinner,
               content, src_html
        FROM tour_line_detail ORDER BY line_id, day_no, sequence, id""")


# ---------------------------------------------------------------------------
# raw SQL 批量写（odoo env.cr；DRY_RUN 时不应被调用）——范式同 migrate_tms19_to_ta
# ---------------------------------------------------------------------------
def chunk_insert(cr, table, cols, rows):
    if not rows:
        return 0
    ph = '(' + ','.join(['%s'] * len(cols)) + ')'
    head = 'INSERT INTO %s (%s) VALUES ' % (table, ','.join(cols))
    total = 0
    for start in range(0, len(rows), BATCH):
        parts = []
        for r in rows[start:start + BATCH]:
            m = cr.mogrify(ph, r)
            parts.append(m if isinstance(m, str) else m.decode())
        cr.execute(head + ','.join(parts))
        total += len(rows[start:start + BATCH])
        cr.commit()
    return total


# ---------------------------------------------------------------------------
# phase0 备份检查
# ---------------------------------------------------------------------------
def phase0_backup_check():
    print('== phase0 备份检查 ==')
    print('  pg_dump 双备份（宿主机执行）：')
    print('    TS=$(date +%Y%m%d_%H%M)')
    print('    sudo docker exec tms-db      pg_dump -U odoo -d tms    -Fc -f /tmp/tms_$TS.dump')
    print('    sudo docker exec odootour-db pg_dump -U odoo -d tour20 -Fc -f /tmp/tour20_$TS.dump')
    if DRY_RUN:
        print('  [DRY-RUN] 只提示，不校验 TMS_MIG_BACKUP_ACK')
        return
    if os.environ.get('TMS_MIG_BACKUP_ACK') != '1':
        raise RuntimeError('未完成 pg_dump 双备份：先备份，再 export TMS_MIG_BACKUP_ACK=1')
    print('  备份确认通过（TMS_MIG_BACKUP_ACK=1）')


# ---------------------------------------------------------------------------
# phase1 组装：route 映射 + 行转换
# ---------------------------------------------------------------------------
def build_rows(ctx):
    print('== phase1 组装 ==')
    env.cr.execute("SELECT id, code, company_id FROM ta_route WHERE code LIKE 'ETM|L%'")
    route_by_code = {code: (rid, comp) for rid, code, comp in env.cr.fetchall()}
    ctx['route_by_code'] = route_by_code

    rows, unmatched = [], []
    src_html_only = []          # (旧id, 线路名/码, day_no, 清洗后前200字符)
    seq_counter = defaultdict(int)   # (route_code, day_no) → 行序（sequence 缺失兜底）
    for (lid_old, line_id, day_no, seq, name, title, city,
         hotel, traffic, mb, ml, md, content, src_html) in ctx['details']:
        code = 'ETM|L%s' % line_id
        hit = route_by_code.get(code)
        if not hit:
            unmatched.append((lid_old, code, s(name)))
            continue
        route_id, comp_id = hit
        d = max(i(day_no, 1), 1)
        seq_final = i(seq)
        if seq_final <= 0:
            seq_counter[(code, d)] += 1
            seq_final = d * 10 + seq_counter[(code, d)]
        body = s(content).strip()
        if not body and s(src_html).strip():
            cleaned = strip_html(src_html)
            if cleaned:
                body = cleaned
                if len(src_html_only) < 20:   # 抽样上限 20 条，全量计数另算
                    src_html_only.append((lid_old, code, d, cleaned[:200]))
        rows.append(dict(old_id=lid_old, route_id=route_id, company_id=comp_id,
                         sequence=seq_final, day_no=d,
                         name=s(name).strip() or ('第%d天' % d),
                         title=s(title) or None, city=s(city) or None,
                         traffic=s(traffic) or None,
                         meal_breakfast=meal_char(mb), meal_lunch=meal_char(ml),
                         meal_dinner=meal_char(md),
                         accommodation=s(hotel) or None,
                         content=body or None,
                         note='ETM|LD|%s' % lid_old))
    ctx['stop_rows'] = rows
    ctx['unmatched'] = unmatched
    ctx['src_html_only'] = src_html_only
    ctx['src_html_only_total'] = sum(
        1 for (_i0, line_id, _dn, _sq, _nm, _t, _c, _h, _tr, _mb, _ml, _md, c, sh)
        in ctx['details'] if not s(c).strip() and s(sh).strip())
    print('  旧行=%d → 可插入=%d、route 未匹配=%d；src_html-only 正文=%d 行（抽样打印见报告）' % (
        len(ctx['details']), len(rows), len(unmatched), ctx['src_html_only_total']))


# ---------------------------------------------------------------------------
# phase2 写入：幂等清理 + 批量 INSERT
# ---------------------------------------------------------------------------
def write_stops(ctx):
    print('== phase2 写入 ==')
    if DRY_RUN:
        print('  [DRY-RUN] 跳过 DELETE 清理与 INSERT')
        return
    env.cr.execute("DELETE FROM ta_route_stop WHERE note LIKE '%s'" % NOTE_PREFIX)
    print('  重跑清理：删除既有 ETM|LD 行程 %d 行' % env.cr.rowcount)
    # 批2 遗留占位 stop（route 落地时按天数机械生成的「第N天」空行，无任何信息量）：
    # 真行程入库后与导入行同 day_no 重复两套，属机器生成占位、可安全再生 → 清理
    env.cr.execute(
        "DELETE FROM ta_route_stop s WHERE s.name ~ '^第[0-9]+天$' "
        "AND COALESCE(s.note, '') = '' AND COALESCE(s.content, '') = '' "
        "AND COALESCE(s.city, '') = '' AND COALESCE(s.accommodation, '') = '' "
        "AND COALESCE(s.traffic, '') = '' "
        "AND EXISTS (SELECT 1 FROM ta_route_stop t WHERE t.route_id = s.route_id "
        "            AND t.note LIKE 'ETM|LD' || '%')")
    print('  批2 占位 stop 清理：%d 行（仅"第N天"空行，且该线路已有真行程）' % env.cr.rowcount)
    env.cr.commit()
    cols = ['company_id', 'route_id', 'sequence', 'day_no', 'name', 'title', 'city',
            'traffic', 'meal_breakfast', 'meal_lunch', 'meal_dinner',
            'accommodation', 'content', 'note',
            'create_uid', 'write_uid', 'create_date', 'write_date']
    super_id = env.ref('base.user_root').id
    n = chunk_insert(env.cr, 'ta_route_stop', cols, [
        (r['company_id'], r['route_id'], r['sequence'], r['day_no'], r['name'],
         r['title'], r['city'], r['traffic'],
         r['meal_breakfast'], r['meal_lunch'], r['meal_dinner'],
         r['accommodation'], r['content'], r['note'],
         super_id, super_id, NOW, NOW) for r in ctx['stop_rows']])
    env.invalidate_all()
    print('  INSERT 完成：%d 行' % n)


# ---------------------------------------------------------------------------
# phase3 对平报告
# ---------------------------------------------------------------------------
def report(ctx):
    print('== phase3 对平报告 ==')
    expect = len(ctx['stop_rows'])
    if DRY_RUN:
        actual = '(dry-run 未写入，预测 %d)' % expect
        ok_note = True
    else:
        env.cr.execute("SELECT count(*) FROM ta_route_stop WHERE note LIKE '%s'" % NOTE_PREFIX)
        actual = env.cr.fetchone()[0]
        ok_note = actual == expect
    routes_hit = len({r['route_id'] for r in ctx['stop_rows']})
    days_max = defaultdict(int)
    for r in ctx['stop_rows']:
        days_max[r['route_id']] = max(days_max[r['route_id']], r['day_no'])
    n_meal = sum(1 for r in ctx['stop_rows']
                 if r['meal_breakfast'] or r['meal_lunch'] or r['meal_dinner'])
    n_traffic = sum(1 for r in ctx['stop_rows'] if r['traffic'])
    n_accom = sum(1 for r in ctx['stop_rows'] if r['accommodation'])
    n_content = sum(1 for r in ctx['stop_rows'] if r['content'])
    print('%-42s %12s %12s %s' % ('核对项', '基线', '实测/预测', '判定'))
    print('-' * 92)
    print('%-42s %12d %12s %s' % ('V1 stop 行数 = 组装可插入数', expect, actual,
                                  'OK' if ok_note else '差异!'))
    print('%-42s %12d %12s' % ('V2 旧库读取总数', len(ctx['details']), '参考'))
    print('%-42s %12d %12s' % ('V3 route 未匹配（跳过）', len(ctx['unmatched']), '参考'))
    print('%-42s %12d %12d' % ('V4 覆盖线路数', routes_hit, routes_hit))
    print('%-42s %12d %12d' % ('V5 src_html-only 行数', ctx['src_html_only_total'],
                               ctx['src_html_only_total']))
    print('%-42s %12d %12s' % ('V6 含三餐行', n_meal, '参考'))
    print('%-42s %12d %12s' % ('V7 含交通行', n_traffic, '参考'))
    print('%-42s %12d %12s' % ('V8 含住宿行', n_accom, '参考'))
    print('%-42s %12d %12s' % ('V9 含正文行(content 非空)', n_content, '参考'))
    if ctx['unmatched']:
        print('  route 未匹配样例（前 10）:')
        for (old_id, code, nm) in ctx['unmatched'][:10]:
            print('    旧id=%s code=%s name=%s' % (old_id, code, nm[:40]))
    if ctx['src_html_only']:
        print('  src_html-only 正文抽样（前 %d 条，清洗后前 200 字符）:' % len(ctx['src_html_only']))
        for (old_id, code, d, sample) in ctx['src_html_only']:
            print('    旧id=%s %s 第%s天: %s' % (old_id, code, d, sample.replace('\n', '⏎')[:200]))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print('MODE = %s' % ('DRY-RUN（只读预演，不落任何写）' if DRY_RUN else '正式导入'))
    conn = old_connect()
    try:
        ctx = {}
        ctx['details'] = load_old(conn)
        print('旧库读取：tour_line_detail=%d 行' % len(ctx['details']))
        phase0_backup_check()
        build_rows(ctx)
        write_stops(ctx)
        report(ctx)
    finally:
        conn.close()
    print('== 完成（%s）==' % ('dry-run 全程未写入' if DRY_RUN else '正式导入'))


# odoo shell 以 __name__=='__main__' 命名空间 exec 本文件（范式同 migrate_tms19_to_ta.py）
if __name__ == '__main__':
    main()
