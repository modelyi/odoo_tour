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
               'ir_model_relation', 'ir_translation', 'ir_attachment_backup',
               # 20 把 19 的 ir_model_access 改名成 ir_access 并把四个 perm_* bool 换成
               # 一列 operation（实测 c/cr/cru/crud/r/… 15 种）。表名不同 ⇒ 本来就不在交集里，
               # 但仍要 DENY：20 侧这张表由模块装载拥有，任何"以后同名"的写法都不能被 19 覆盖。
               'ir_access')
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


def junctions(side, cand, fk):
    """候选里筛出真正的中间表：除 id/审计列外**只有两个单列外键**。
    返回 (可直拷的集合, 因两端含 DENY 表而不能直拷的集合)。
    含 DENY 端（如 res_groups）的**绝不能按原 id 拷** —— 20 侧同一组的 id 不一样，
    照拷等于把用户挂到别的组上（权限放大，比没有还糟）。这类只能走自然键映射
    （见 s0_grant_groups.py）。"""
    if not cand:
        return set(), set()
    inlist = ','.join("'%s'" % t for t in cand)          # cand 全部来自 information_schema
    rows = q(side[0], side[1], """
select table_name, string_agg(column_name, ',' order by ordinal_position)
  from information_schema.columns
 where table_schema='public' and table_name in (%s)
 group by 1""" % inlist)
    cols = {t: set(c.split(',')) for t, c in rows}
    ok, deny_ended = set(), set()
    for t in cand:
        cs = cols.get(t)
        if not cs:
            continue
        fkcols, single = set(), True
        for p, c in fk[t].items():
            if len(c) != 1:
                single = False
            fkcols |= c
        if not single or (cs - fkcols) - (AUDIT_COLS | {'id'}):
            continue                                     # 还有别的业务列 → 不是纯中间表
        if any(p in DENY or p.startswith(DENY_PREFIX) for p in fk[t]) or t in DENY or t.startswith(DENY_PREFIX):
            deny_ended.add(t)
        else:
            ok.add(t)
    return ok, deny_ended


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

    # 1b) **多对多中间表（junction）不会从父表闭包里长出来** —— 它们只当子表，
    #     谁也不外键指向它们。实测漏掉 res_groups_users_rel 之后，影子库里 admin
    #     一个组都没有，`tour.guide` 直接 AccessError（"TMS/旅行社经理"那批组全空），
    #     表现成"数据搬齐了但业务看不见"。所以显式补：两端都在闭包里、
    #     除 id/审计列外**只有两个外键列**的表。
    def _ends_ok(t):
        # 两端要么在闭包里，要么是被 DENY 的 20 自有表（res_groups / mail_alias…）——
        # 后者 20 侧也有行，只是 id 不同，必须走自然键映射而不是原 id 照拷。
        return all(p in need or (p in both and (p in DENY or p.startswith(DENY_PREFIX)))
                   for p in fk.get(t, ()))

    def _ends_bad(t):   # 端点里"不能按 id 拷"的那类表：DENY 端 或 被 skip 的 20 自有表
        bad = []
        for p in fk.get(t, ()):
            if p in need and modes.get(p) == 'skip':
                bad.append('%s(skip)' % p)
            elif p in both and (p in DENY or p.startswith(DENY_PREFIX)):
                bad.append('%s(20自有)' % p)
        return bad
    cand = [t for t in sorted(both - need) if len(fk.get(t, ())) == 2 and _ends_ok(t)]
    jun, jun_deny = junctions(SRC, cand, fk)
    # 端点被 skip / 由 20 自有表持有的中间表**不进清单**：按 id 拷必然 FK 违约
    # （实测 payment_method 231→3、project_project 被 skip），硬搬只会把 FAIL 变成噪音。
    jun_bad = {t: _ends_bad(t) for t in jun if _ends_bad(t)}
    jun -= set(jun_bad)
    need |= jun
    if jun:
        print('补入中间表 %d 张: %s' % (len(jun), ' '.join(sorted(jun))))
    if jun_deny:
        print('!! 中间表 %d 张含 20 自有端（res_groups 等），**不按原 id 拷**，'
              '需自然键映射: %s' % (len(jun_deny), ' '.join(sorted(jun_deny))))
    if jun_bad:
        print('!! 中间表 %d 张端点不可按 id 引用（20 自有或已 skip）→ 不搬，需业务复核: %s'
              % (len(jun_bad), ' '.join('%s←%s' % (t, ','.join(v)) for t, v in sorted(jun_bad.items()))))

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
