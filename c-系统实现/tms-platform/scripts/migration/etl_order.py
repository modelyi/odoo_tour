#!/usr/bin/env python3
"""按外键拓扑生成 ETL 清单（`etl_slice.sh` 的输入）。

为什么必须自动生成而不是手抄：手抄的清单靠人记外键方向，一次跑错顺序就要重建库重来；
而"哪些表在 20 已经不存在"这类事，人眼看 diff 会漏（本次就漏了 `res_bank` 60 行、
`tour_line_type` 85 行 —— 两张 19 有数据、20 模型已删的表）。

  python3 etl_order.py --seeds seeds_s0.txt --out slices/s0_full.txt
"""
import argparse
import os
import subprocess
import sys

SRC = ('tms-db', 'tms')
DST = ('odoo20-db', os.environ.get('ETL_DST_DB', 's0tour'))

# 20 侧自己拥有、**绝对不能被 19 覆盖**的元数据表（注册表、视图、动作、模块状态）。
# 闭包碰到它们时必须剪掉，否则 upsert 会把 20 的界面定义改回 19 的样子 —— 那是整站白屏级别的事故。
DENY_PREFIX = ('ir_model', 'ir_ui_view', 'ir_actions', 'ir_act_', 'ir_module', 'ir_logging',
               'ir_http', 'ir_rule', 'ir_model_access', 'ir_model_constraint',
               'ir_model_relation', 'ir_translation', 'ir_attachment_backup')
DENY = {'ir_config_parameter', 'ir_cron', 'ir_sequence', 'ir_property', 'ir_qweb_field',
        'bus_bus', 'decimal_precision', 'ir_demo', 'ir_demo_failure',
        # 权限组与邮件别名同样是"20 装载模块时自己生成"的基数据：res_groups.privilege_id /
        # res_groups_privilege.category_id 指向 ir_module_category，两侧 id 不同 → 整表必炸。
        # 门户组在 20 侧由模块自己建好，S0 冒烟靠 grant_smoke_portals.py 显式授予（TDS-30 §5.8）。
        'res_groups', 'res_groups_privilege', 'mail_alias'}
# 明确排除的"19 遗留备份表"（一次性修复脚本留下的 2×86,927 行死重，也是 tms 体积偏大的原因之一）
DENY_EXACT = {'bak_tour_plan_channel', 'bak_tour_plan_income_move'}


def q(container, db, sql):
    r = subprocess.run(['docker', 'exec', container, 'psql', '-U', 'odoo', '-d', db,
                        '-At', '-F', '|', '-c', sql], capture_output=True, text=True, check=True)
    return [l.split('|') for l in r.stdout.splitlines() if l.strip()]


def tables(side):
    rows = q(side[0], side[1],
             "select table_name from information_schema.tables "
             "where table_schema='public' and table_type='BASE TABLE'")
    return {r[0] for r in rows}


AUDIT_COLS = {'create_uid', 'write_uid'}


def fks(side):
    """→ {child: {parent: {列名…}}}（同一对表可能有多条外键，列名都要留着）"""
    rows = q(side[0], side[1], """
select conrelid::regclass::text, confrelid::regclass::text,
       string_agg(att.attname, ',' order by att.attname)
  from pg_constraint c
  join lateral unnest(c.conkey) with ordinality as k(attnum, ord) on true
  join pg_attribute att on att.attrelid = c.conrelid and att.attnum = k.attnum
 where c.contype='f' and c.connamespace='public'::regnamespace
 group by 1,2""")
    m = {}
    for child, parent, cols in rows:
        if child != parent:
            m.setdefault(child, {}).setdefault(parent, set()).update(cols.split(','))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--mode-file', default=None,
                    help='可选：`表名 模式` 覆盖默认 upsert（违约表填 insertignore）')
    ap.add_argument('--cycles-out', default=None,
                    help='回边清单输出路径，默认与 --out 同目录的 cycles.txt（etl_cycle.sh 的输入）')
    ap.add_argument('--exclude-file', default=None,
                    help='可选：`表名 列1,列2` —— 这些列进不了搬运列表（20 有、19 无落点的列）')
    a = ap.parse_args()
    if a.cycles_out is None:
        a.cycles_out = os.path.join(os.path.dirname(a.out) or '.', 'cycles.txt')

    t19, t20 = tables(SRC), tables(DST)
    both = t19 & t20
    only19 = t19 - t20
    seeds = [l.split('#')[0].strip() for l in open(a.seeds, encoding='utf-8') if l.strip()]
    all_seeds = seeds
    seeds = [s for s in all_seeds if s in both]
    dropped = [s for s in all_seeds if s in only19]

    modes = {}
    if a.mode_file:
        for l in open(a.mode_file, encoding='utf-8'):
            p = l.split()
            if len(p) >= 2 and not l.startswith('#'):
                modes[p[0]] = p[1]
    excludes = {}
    if a.exclude_file:
        for l in open(a.exclude_file, encoding='utf-8'):
            p = l.split()
            if len(p) >= 2 and not l.startswith('#'):
                excludes[p[0]] = p[1]

    fk = fks(SRC)
    # 1) 从种子出发取"父表闭包"（这些表必须先于种子存在）
    need, stack = set(), list(seeds)
    while stack:
        t = stack.pop()
        if t in need or t not in both:
            continue
        need.add(t)
        for p in fk.get(t, ()):
            if p in both and p not in DENY and not p.startswith(DENY_PREFIX):
                stack.append(p)

    # 2) 拓扑排序：父在前。**环必须显式记下来，不能"剪掉就完事"**：
    #    剪断回边只解决"谁先插入"，解决不了"一整条 INSERT 是原子的"——
    #    实测 account_move 因为 account_move.origin_payment_id ↔ account_payment.move_id 互为依赖，
    #    27.6 万行里只要有一条指向还没搬的付款，**整表 0 行进不去**，跑三轮也不会收敛。
    #    所以正确做法是：搬这对表之前把回边上的外键约束临时 DROP，全部搬完再 ADD 回去
    #    （ADD 会顺带做引用完整性校验，校验不过的那条就是真正的脏数据）。
    #    见 etl_cycle.sh。
    order, state, cycles = [], {}, set()

    def visit(n):
        if state.get(n) == 'done' or n in DENY or n.startswith(DENY_PREFIX) or n in DENY_EXACT:
            return
        if state.get(n) == 'visiting':
            return
        state[n] = 'visiting'
        for p in sorted(fk.get(n, ())):
            if p not in need:
                continue
            if state.get(p) == 'visiting':
                # 只有**非审计列**的回边才算真环。Odoo 每张表都有 create_uid/write_uid → res_users，
                # 而 res_users 又能从几乎任何表走到（父表闭包），于是 DFS 里"到处都在栈上"，
                # 第一版因此报了 202 条回边 —— 全去 DROP 外键既没意义又把约束校验整个废掉。
                cols = fk.get(n, {}).get(p, set())
                if not cols <= AUDIT_COLS:
                    cycles.add((n, p))
                continue
            visit(p)
        state[n] = 'done'
        order.append(n)

    for n in sorted(need):
        visit(n)

    with open(a.cycles_out, 'w', encoding='utf-8') as f:
        f.write('# 由 etl_order.py 生成的"拓扑剪断的回边"：`子表 父表`，父表靠这些子表的外键指回来。\n')
        f.write('# 搬之前用 etl_cycle.sh drop 临时删掉这些外键，搬完 add 回来（add = 引用完整性校验）。\n')
        for c, p in sorted(cycles):
            f.write('%s %s\n' % (c, p))

    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('# 由 etl_order.py 自动生成（外键拓扑，父在前）—— 不要手改顺序，改 seeds\n')
        f.write('# 模式：upsert=按 id 覆盖 | insertignore=违约则跳过 | wipe=先按 id 删再插\n')
        f.write('# 第 3 列 = 人工排除列（见 --exclude-file），用于"20 有、19 没有落点"的列\n')
        for n in order:
            ex = excludes.get(n)
            f.write('%s %s%s\n' % (modes.get(n, 'upsert'), n, (' ' + ex) if ex else ''))

    print('种子 %d → 闭包 %d 表，回边 %d 条（%s），已写 %s'
          % (len(seeds), len(order), len(cycles), a.cycles_out, a.out))
    if dropped:
        print('!! 种子写了但 20 侧无此表（模型已删）: %s' % ' '.join(dropped))
    dead = sorted(t for t in only19 if t.startswith('tour_') or t in ('res_bank', 'account_group'))
    if dead:
        print('19 有 / 20 无 且与业务相关的表: %s' % ' '.join(dead))
    return 0


if __name__ == '__main__':
    sys.exit(main())
