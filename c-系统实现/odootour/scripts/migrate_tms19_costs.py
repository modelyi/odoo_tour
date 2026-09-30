# -*- coding: utf-8 -*-
"""
migrate_tms19_costs.py —— 原 TMS（tms 库）供应商成本明细 + 导游借支 → tour20（批3-3，任务#40）

框架逐字照抄 scripts/migrate_tms19_to_ta.py（批2）：DRY_RUN 常量、old_connect()、
TMS_MIG_BACKUP_ACK 门禁、chunk_insert BATCH=2000、非 DRY_RUN 幂等清理、`if __name__` 入口。

目标：把旧系统真实请款明细（tour_pay_request，81,215 行全 paid）逐条导入
ta.dispatch.item，导游借支（tour_guide_loan，9 行）导入 ta.guide.loan，
让历史团产品报表（单团损益/景点毛利/绩效/供应商付款）出真数。

== 接口语义（批3-2 交付，不得改）==
- ta.dispatch.item.paid_date：date 可空，store+readonly=False compute；**move_id 空 +
  paid_date 有值 → ta.supplier.payable 视图按条目全额已付**（视图 SQL 已实现）。
- 条目填满 NOT NULL 列（chunk_insert 风格）：company_id / create_uid / write_uid /
  create_date / write_date / state='confirmed' / move_id NULL / qty=1 / unit_price=amount。
- 条目 note 源引用：'ETM|X|P<旧id>'。

== kind 映射（读 ta_dispatch/models/ta_dispatch_item.py KIND 枚举定；含 ticket/vehicle/ditch）==
旧 tour_supplier.sup_type → 新 kind：
  scenic/ticket→'ticket'（KIND 有 ticket，按任务指定，不用 scenic）；meal→meal；
  hotel→hotel；vehicle_comp→vehicle；ditch/shop/self_fee/insurance/customer/空/未知→other。
实测（DRY_RUN 全量）：pay_request 付款对象经旧 partner 桥到 tour_supplier 后 sup_type
仅 customer(81,147)/ditch(68)，且 cost_type 全 'other' → kind 全 'other'。
影响：单团损益/绩效/供应商付款出真数；景点毛利视图口径 kind∈(ticket,scenic)，
历史条目无门票信号 → 历史团景点毛利为空（数据现实，报告呈现，不另造分类）。

== departure 反查 ==
旧 plan_id → tour_plan 行 → 批2归并键 norm_dates(begin,end) →
ta_departure.code='ETM|D|<line>|<b>|<e>'（正式库由批2已建好，本脚本只反查不改团）。
落不到团的条目跳过并计数报告；供应商 partner（ref='ETM|S<sid>'）未命中率>1% → 报告标红停下。

== 清理段（非 DRY_RUN 幂等）==
1) DELETE 批2合成条目：批2 note 实为 'ETM|X<departure_id>'（非 'ETM|X|S'）→
   谓词 note LIKE 'ETM|X%' AND note NOT LIKE 'ETM|X|%'；删前 SELECT Σamount 打印对基线
   150 条 / 1,260,845.61（V5）。
2) DELETE 上一轮本脚本条目 note LIKE 'ETM|X|P%'（重跑幂等）。
3) unlink 上一轮借支 name LIKE 'ETM|GL|%'。
插入后 UPDATE ta_departure.dispatch_cost_total 按 confirmed 条目重算（raw SQL 不走 ORM compute）。

== 借支（9 行，ORM sudo 直建）==
guide 经 'ETM|G<id>' partner ref；departure 同上反查（反不到→留空计数）；
amount=旧 amount；**outstanding 按新模型口径 = amount − Σ冲抵行**：旧 residual 是存量字段，
新系统只能由佣金冲抵行（ta.guide.commission.deduct）表达，历史冲抵行不补造（零凭证、
不伪造佣金单）→ 入插后 outstanding=amount，与旧 residual 的差额（实测 7,700＝旧#16 已冲抵
4,700 + 旧#17 已结清 3,000）在 V6c 如实报告为已知偏差；旧#17 state=settled 而 outstanding
按新口径仍为 3,000，属同一偏差。journal_id/paid_move_id 留空，**不重放凭证**，
note='ETM 历史借支，无凭证'。
坑：deducted_amount/outstanding 为 store=True compute（依赖冲抵行），建后 SQL 直写会被
flush/重算覆盖回 0/amount（阶段B 实测 V6b 差异根因）→ 不做直写。
state（Selection 字段可直写，无 SQL CHECK，action_* 只守卫方法入口）：
旧 state='settled'→'settled'；否则有 disbursement_date（或旧 state='disbursed' 兜底）→'paid'；
否则有 approve_date（或旧 state='approved' 兜底）→'approved'；否则 'draft'
（实测旧行 #16/#21/#22 有态无期，机械日期规则会错标 draft）；
name='ETM|GL|<旧id>'（旧模型 unique(name) 同约束新表也有，id 拼码唯一）。
旧库 9 行中 3 行 guide_id 为空（员工备用金）→ guide_id 必填不可导，跳过计数报告。

== 运行方式（协调人执行；DRY_RUN=True 时只读旧库+目标库，不落任何写）==
    sudo docker network connect tms-net odootour-odoo          # 跨库网络（批2实测结论同）
    export TMS_OLD_DB_PASSWORD='***'                            # 同 tms-odoo 容器 PGPASSWORD
    sudo docker cp c-系统实现/odootour/scripts/migrate_tms19_costs.py odootour-odoo:/tmp/
    sudo docker exec -i -e TMS_OLD_DB_PASSWORD -e TMS_MIG_BACKUP_ACK=1 odootour-odoo \
      python3 /usr/lib/odoo/odoo-server/odoo-bin shell -d tour20 --no-http \
      --db_host=db --db_user=odoo --db_password=<新库口令> < /tmp/migrate_tms19_costs.py
兜底：其他中转用 TMS_OLD_DB_HOST / TMS_OLD_DB_PORT 覆盖默认 tms-db / 5432。

== 断言/报告（V 系，两种模式都打；DRY_RUN「实测」列=内存预测）==
V1 新条目数 = 81,215 − 跳过数；V2 Σamount 对平 256,765,071.40 − 跳过额；
V3 sup_type→kind 分布表；V4 供应商/团未命中计数+清单；V5 合成条目删除额 1,260,845.61
（两模式均直读目标库实况）；V6 借支 9 行、Σresidual；V7 抽样 3 团新旧成本对比
（旧 Σout_price_quo_sum 参考口径 vs 新条目 Σ）；V8 全库 posted Σ借−Σ贷=0 且凭证数不变
（零凭证断言：脚本全程不建/不改 account.move，条目 move_id 恒 NULL）。
"""
import os
import datetime
from collections import defaultdict, Counter

import psycopg2  # odootour-odoo 容器内实测可 import

# ---------------------------------------------------------------------------
# 开关与常量
# ---------------------------------------------------------------------------
DRY_RUN = True   # ← 协调人核对 dry-run 报告后改为 False 正式执行
BATCH = 2000
TOL = 0.01

OLD_DB_HOST = os.environ.get('TMS_OLD_DB_HOST', 'tms-db')
OLD_DB_PORT = os.environ.get('TMS_OLD_DB_PORT', '5432')
OLD_DB_NAME = os.environ.get('TMS_OLD_DB_NAME', 'tms')
OLD_DB_USER = os.environ.get('TMS_OLD_DB_USER', 'odoo')

# 基线锚（任务#40 给定；实测偏差进报告）
ANCHOR_PR_ROWS = 81215
ANCHOR_PR_AMOUNT = 256765071.40
ANCHOR_SYNTH_ROWS = 150
ANCHOR_SYNTH_AMOUNT = 1260845.61
ANCHOR_LOAN_ROWS = 9
SUP_MISS_REDLINE = 0.01   # 供应商未命中率 >1% → 停下

SUP_TYPE_KIND = {          # 旧 sup_type → 新 kind（KIND 枚举实测含 ticket/vehicle/ditch）
    'scenic': 'ticket', 'ticket': 'ticket',
    'meal': 'meal', 'hotel': 'hotel', 'vehicle_comp': 'vehicle',
    'ditch': 'other', 'shop': 'other', 'self_fee': 'other',
    'insurance': 'other', 'customer': 'other',
}
KIND_FALLBACK = 'other'
ITEM_PREFIX = '历史请款(迁移)'
LOAN_NOTE = 'ETM 历史借支，无凭证'
NOTE_ITEM = 'ETM|X|P%s'
CODE_DEP = 'ETM|D|%s|%s|%s'

NOW = datetime.datetime.now().replace(microsecond=0)
TODAY = NOW.date().isoformat()


# ---------------------------------------------------------------------------
# 纯函数工具（批2同款）
# ---------------------------------------------------------------------------
def f(v, default=0.0):
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def i(v, default=0):
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def s(v, default=''):
    return default if v is None else str(v)


def money(v):
    return round(f(v), 2)


def norm_dates(b, e):
    """R10 脏日期规范化（批2同款，保证归并键逐字一致）：颠倒交换、单侧缺失互补。"""
    if b and e and e < b:
        b, e = e, b
    if b and not e:
        e = b
    if e and not b:
        b = e
    return b, e


def date_of(dtval, fallback=None):
    """Datetime→date（approve/disbursement 旧列是 Datetime）。"""
    if dtval is None:
        return fallback
    return dtval.date() if isinstance(dtval, datetime.datetime) else dtval


# ---------------------------------------------------------------------------
# 旧库读取（psycopg2 独立连接；批2同款）
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
    ctx = {}
    ctx['payreq'] = old_fetch(conn, """
        SELECT id, plan_id, supplier_id, amount, approve_date, apply_date, state, name, reason
        FROM tour_pay_request ORDER BY id""")
    ctx['loan'] = old_fetch(conn, """
        SELECT id, name, guide_id, plan_id, amount, residual, state, apply_date,
               approve_date, disbursement_date, due_date
        FROM tour_guide_loan ORDER BY id""")
    ctx['plans'] = old_fetch(conn, """
        SELECT id, line_id, begin_date, end_date, out_price_quo_sum
        FROM tour_plan ORDER BY id""")
    ctx['suppliers'] = old_fetch(conn, """
        SELECT id, partner_id, sup_type FROM tour_supplier ORDER BY id""")
    # 桥：旧 res_partner.id → tour_supplier.id（pay_request.supplier_id 是旧 partner）
    ctx['partner_to_sup'] = {r[1]: r[0] for r in ctx['suppliers'] if r[1]}
    ctx['sup_type'] = {r[0]: s(r[2]) for r in ctx['suppliers']}
    # plan_id → 归并键 code + 旧 out_price 聚合（V7 参考）
    dep_of_plan, cost_by_key = {}, defaultdict(float)
    for (pid, lid, b, e, outq) in ctx['plans']:
        b, e = norm_dates(b, e)
        code = CODE_DEP % (lid, b, e)
        dep_of_plan[pid] = code
        cost_by_key[code] += money(outq)
    ctx['dep_of_plan'] = dep_of_plan
    ctx['cost_by_key'] = {k: round(v, 2) for k, v in cost_by_key.items()}
    return ctx


# ---------------------------------------------------------------------------
# 目标库只读快照（两种模式都读——正式数据批2已在库内；DRY_RUN 不落写）
# ---------------------------------------------------------------------------
def scalar(sql, args=None):
    env.cr.execute(sql, args)
    row = env.cr.fetchone()
    return row[0] if row else None


def load_target(ctx):
    env.cr.execute("SELECT id, code, route_id FROM ta_departure WHERE code LIKE 'ETM|D|%'")
    ctx['dep_by_code'] = {}
    for did, code, rid in env.cr.fetchall():
        ctx['dep_by_code'][code] = (did, rid)
    env.cr.execute("SELECT id, ref FROM res_partner WHERE ref LIKE 'ETM|S%'")
    ctx['sup_by_ref'] = {ref: pid for pid, ref in env.cr.fetchall()}
    env.cr.execute("SELECT id, ref FROM res_partner WHERE ref LIKE 'ETM|G%'")
    ctx['guide_by_ref'] = {ref: pid for pid, ref in env.cr.fetchall()}
    # 批2合成条目实况（note='ETM|X<dep_id>'，无 '|' 段）
    env.cr.execute("SELECT count(*), COALESCE(round(sum(amount)::numeric,2),0) FROM ta_dispatch_item "
                   "WHERE note LIKE 'ETM|X%%' AND note NOT LIKE 'ETM|X|%%'")
    ctx['synth_rows'], ctx['synth_sum'] = env.cr.fetchone()
    env.cr.execute("SELECT count(*) FROM ta_dispatch_item WHERE note LIKE 'ETM|X|P%%'")
    ctx['prev_p_rows'] = env.cr.fetchone()[0]
    env.cr.execute("SELECT count(*) FROM ta_guide_loan WHERE name LIKE 'ETM|GL|%%'")
    ctx['prev_loan_rows'] = env.cr.fetchone()[0]
    # V8 基线：凭证数与 posted 借贷差（本脚本运行前后必须不变/为0）
    ctx['move_count0'] = scalar("SELECT count(*) FROM account_move")
    ctx['posted_diff0'] = money(scalar("SELECT COALESCE(round(sum(debit-credit),2),0) "
                                       "FROM account_move_line WHERE parent_state='posted'"))
    print('目标库只读快照：departure(ETM)=%d sup_partner=%d guide_partner=%d 合成条目=%d(Σ%.2f) '
          '既有P条目=%d 既有借支=%d 凭证数=%s posted差=%.2f' % (
              len(ctx['dep_by_code']), len(ctx['sup_by_ref']), len(ctx['guide_by_ref']),
              ctx['synth_rows'], ctx['synth_sum'], ctx['prev_p_rows'], ctx['prev_loan_rows'],
              ctx['move_count0'], ctx['posted_diff0']))


# ---------------------------------------------------------------------------
# raw SQL 批量写（批2逐字同款；DRY_RUN 时不应被调用）
# ---------------------------------------------------------------------------
def chunk_insert(cr, table, cols, rows):
    """多值 INSERT，每 BATCH 条提交一次。返回插入行数。"""
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
# phase0 备份检查（批2逐字同款）
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
# phase1 请款明细 → dispatch.item 行构建（内存；两种模式都算）
# ---------------------------------------------------------------------------
def phase1_build_items(ctx):
    print('== phase1 tour_pay_request → ta.dispatch.item 构建 ==')
    cid, super_id = env.company.id, env.ref('base.user_root').id
    rows = []
    skip_sup, skip_dep, skip_amt = [], [], []
    kind_cnt, sup2kind_cnt, pr_state_cnt = Counter(), Counter(), Counter()
    nodate = 0
    sum_all = 0.0
    by_dep = defaultdict(float)
    for (prid, plan_id, sup_partner_old, amount, appr_dt, apply_dt, st, old_name, reason) \
            in ctx['payreq']:
        amt = money(amount)
        sum_all = round(sum_all + amt, 2)
        pr_state_cnt[s(st)] += 1
        code = ctx['dep_of_plan'].get(plan_id)
        dep = ctx['dep_by_code'].get(code) if code else None
        sup_ref = 'ETM|S%s' % ctx['partner_to_sup'][sup_partner_old] \
            if sup_partner_old and sup_partner_old in ctx['partner_to_sup'] else None
        sup_new = ctx['sup_by_ref'].get(sup_ref) if sup_ref else None
        if dep is None:
            skip_dep.append((prid, code))
            continue
        if sup_new is None:
            skip_sup.append((prid, s(sup_ref) or 'old_partner=%s' % sup_partner_old))
            continue
        if amt <= 0:            # 负/0 请款：unit_price>=0 CHECK 拦截 → 跳过计数
            skip_amt.append((prid, amt))
            continue
        stype = ctx['sup_type'].get(ctx['partner_to_sup'].get(sup_partner_old), '')
        kind = SUP_TYPE_KIND.get(stype, KIND_FALLBACK)
        kind_cnt[kind] += 1
        sup2kind_cnt[(stype or '(空)', kind)] += 1
        pdate = date_of(appr_dt) or apply_dt
        if pdate is None:
            nodate += 1
            pdate = TODAY       # 双空兜底（历史已付语义必须有 paid_date；实测应为 0）
        rows.append((cid, dep[0], dep[1], sup_new, kind,
                     ('%s %s' % (ITEM_PREFIX, s(old_name) or 'P%s' % prid))[:200],
                     1.0, amt, amt, 'confirmed', None, pdate,
                     NOTE_ITEM % prid, super_id, super_id, NOW, NOW))
        by_dep[dep[0]] = round(by_dep[dep[0]] + amt, 2)
    ctx['items'], ctx['by_dep'] = rows, by_dep
    ctx['sum_all'] = sum_all
    ctx['skip_sup'], ctx['skip_dep'], ctx['skip_amt'] = skip_sup, skip_dep, skip_amt
    ctx['kind_cnt'], ctx['sup2kind_cnt'], ctx['pr_state_cnt'] = kind_cnt, sup2kind_cnt, pr_state_cnt
    ctx['nodate'] = nodate
    keep_sum = round(sum(r[8] for r in rows), 2)   # 第9列=amount
    ctx['keep_sum'] = keep_sum
    ctx['skipped_sum'] = round(sum_all - keep_sum, 2)
    total = len(ctx['payreq'])
    miss_rate = len(skip_sup) / float(total or 1)
    print('  请款行=%d Σamount=%.2f（基线 %d / %.2f，偏差 %s / %.2f）' % (
        total, sum_all, ANCHOR_PR_ROWS, ANCHOR_PR_AMOUNT, total - ANCHOR_PR_ROWS,
        round(sum_all - ANCHOR_PR_AMOUNT, 2)))
    print('  旧 state 分布：%s' % dict(pr_state_cnt))
    print('  入插=%d（Σ=%.2f） 跳过：团反查不到=%d 供应商未命中=%d(率%.3f%%) 金额≤0=%d 无日期兜底=%d'
          ' 跳过额合计=%.2f' % (len(rows), keep_sum, len(skip_dep), len(skip_sup),
                              miss_rate * 100, len(skip_amt), nodate, ctx['skipped_sum']))
    if miss_rate > SUP_MISS_REDLINE:
        print('  !!标红!! 供应商未命中率 %.3f%% > 1%% 红线，样例：%s' % (
            miss_rate * 100, skip_sup[:10]))
        raise RuntimeError('供应商 partner 未命中率超过 1%%，停止（不进入写入阶段）')


# ---------------------------------------------------------------------------
# phase2 借支行构建（内存；两种模式都算）
# ---------------------------------------------------------------------------
def phase2_build_loans(ctx):
    print('== phase2 tour_guide_loan → ta.guide.loan 构建 ==')
    cid = env.company.id
    loans, lskip = [], []
    for (lid, lname, gid, plan_id, amount, residual, st, apply_dt,
         appr_dt, disb_dt, due_dt) in ctx['loan']:
        amt = money(amount)
        res = amt if residual is None else money(residual)
        g_ref = 'ETM|G%s' % gid
        guide = ctx['guide_by_ref'].get(g_ref)
        code = ctx['dep_of_plan'].get(plan_id) if plan_id else None
        dep = ctx['dep_by_code'].get(code) if code else None
        # 日期证据优先；日期缺失时按旧 state 字段兜底（实测 #16/#21/#22 有态无期，
        # 若机械按日期规则会错标 draft，损失历史真值）
        if s(st) == 'settled':
            nstate = 'settled'
        elif disb_dt or s(st) == 'disbursed':
            nstate = 'paid'
        elif appr_dt or s(st) == 'approved':
            nstate = 'approved'
        else:
            nstate = 'draft'
        if guide is None or amt <= 0:
            lskip.append((lid, 'guide未命中' if guide is None else '金额≤0'))
            continue
        loans.append(dict(oid=lid, vals={
            'name': 'ETM|GL|%s' % lid, 'guide_id': guide,
            'departure_id': dep[0] if dep else False, 'company_id': cid,
            'date': date_of(apply_dt, apply_dt) or TODAY,
            'amount': amt, 'due_date': due_dt,
            'date_paid': date_of(disb_dt) or False,
            'state': nstate, 'note': LOAN_NOTE,
        }, deducted=round(amt - res, 2), outstanding=res,
            dep_hit=bool(dep), old_state=s(st)))
    ctx['loans'], ctx['loan_skip'] = loans, lskip
    ctx['loan_res_sum'] = round(sum(l['outstanding'] for l in loans), 2)
    ctx['loan_amt_sum'] = round(sum(l['vals']['amount'] for l in loans), 2)
    print('  借支=%d 行（基线 %d），Σamount=%.2f Σresidual=%.2f，dep 反查命中=%d' % (
        len(loans), ANCHOR_LOAN_ROWS, ctx['loan_amt_sum'], ctx['loan_res_sum'],
        sum(1 for l in loans if l['dep_hit'])))
    if lskip:
        print('  跳过借支=%d（旧库 guide_id 为空的员工备用金行，ta.guide.loan.guide_id '
              '必填不可导）：%s' % (len(lskip), lskip))
    for l in loans:
        print('    旧#%-3s guide=%s dep=%s state旧=%-10s→新=%-9s amount=%.2f residual=%.2f' % (
            l['oid'], l['vals']['guide_id'], l['vals']['departure_id'] or '-',
            l['old_state'], l['vals']['state'], l['vals']['amount'], l['outstanding']))
    print('  state 直写结论：ta.guide.loan.state 为 Selection 字段（无 SQL CHECK、无 compute/'
          '约束方法拦截，action_* 仅守卫方法入口）→ ORM create 直写 state 合法')


# ---------------------------------------------------------------------------
# phase3 清理段（非 DRY_RUN；批2合成条目 + 重跑残留）
# ---------------------------------------------------------------------------
def phase3_cleanup(ctx):
    print('== phase3 幂等清理 ==')
    if DRY_RUN:
        print('  [DRY-RUN] 跳过 DELETE。将删：合成条目 %d 条(Σ%.2f, 基线 %d/%.2f)；'
              '既有P条目残留 %d；既有借支残留 %d' % (
                  ctx['synth_rows'], ctx['synth_sum'], ANCHOR_SYNTH_ROWS,
                  ANCHOR_SYNTH_AMOUNT, ctx['prev_p_rows'], ctx['prev_loan_rows']))
        return
    # 批2合成条目：note='ETM|X<dep_id>'（无 |S 段，实况格式）→ 'ETM|X%' 且非 'ETM|X|%'
    env.cr.execute("SELECT count(*), COALESCE(round(sum(amount)::numeric,2),0) FROM ta_dispatch_item "
                   "WHERE note LIKE 'ETM|X%%' AND note NOT LIKE 'ETM|X|%%'")
    n, tot = env.cr.fetchone()
    print('  删前合成条目：count=%s Σamount=%s（基线 %d / %.2f → 判定 %s）' % (
        n, tot, ANCHOR_SYNTH_ROWS, ANCHOR_SYNTH_AMOUNT,
        'OK' if abs(f(tot) - ANCHOR_SYNTH_AMOUNT) <= 0.01 else '差异!'))
    env.cr.execute("DELETE FROM ta_dispatch_item "
                   "WHERE note LIKE 'ETM|X%%' AND note NOT LIKE 'ETM|X|%%'")
    env.cr.execute("DELETE FROM ta_dispatch_item WHERE note LIKE 'ETM|X|P%%'")
    old_loans = env['ta.guide.loan'].sudo().with_context(
        tracking_disable=True, mail_notrack=True).search([('name', 'like', 'ETM|GL|%')])
    if old_loans:
        old_loans.unlink()
    env.cr.commit()
    env.invalidate_all()
    print('  清理完成（合成条目 + 上一轮 P 条目 + 上一轮借支）')


# ---------------------------------------------------------------------------
# phase4 写入：条目 raw 批量 + 借支 ORM + dispatch_cost_total 重算
# ---------------------------------------------------------------------------
def phase4_write(ctx):
    print('== phase4 写入 ==')
    if DRY_RUN:
        print('  [DRY-RUN] 跳过全部写入。将插条目 %d 行（Σ%.2f）、借支 %d 行；'
              '并 UPDATE ta_departure.dispatch_cost_total（仅 ETM 团）' % (
                  len(ctx['items']), ctx['keep_sum'], len(ctx['loans'])))
        return
    cols = ['company_id', 'departure_id', 'route_id', 'supplier_id', 'kind', 'name',
            'qty', 'unit_price', 'amount', 'state', 'move_id', 'paid_date', 'note',
            'create_uid', 'write_uid', 'create_date', 'write_date']
    n = chunk_insert(env.cr, 'ta_dispatch_item', cols, ctx['items'])
    print('  dispatch.item 入库 %d 行' % n)
    CTX = dict(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    L = env['ta.guide.loan'].sudo().with_context(**CTX)
    made = []
    for l in ctx['loans']:
        rec = L.create(l['vals'])
        # deducted/outstanding 为 store=True compute（依赖冲抵行）→ 不直写，直写会被重算覆盖
        made.append(rec.id)
    env.cr.commit()
    # raw 写入不走 ORM compute：confirmed 条目合计直写回 departure.dispatch_cost_total
    env.cr.execute(
        "UPDATE ta_departure d SET dispatch_cost_total="
        "COALESCE((SELECT round(sum(i.amount)::numeric,2) FROM ta_dispatch_item i "
        "          WHERE i.departure_id=d.id AND i.state='confirmed'),0) "
        "WHERE d.code LIKE 'ETM|D|%'")
    env.cr.commit()
    env.invalidate_all()
    print('  借支入库 %d 行（journal_id/paid_move_id 留空，不重放凭证）；'
          'dispatch_cost_total 重算完成' % len(made))


# ---------------------------------------------------------------------------
# phase5 V 系报告（两种模式都打；DRY_RUN「实测」=内存预测）
# ---------------------------------------------------------------------------
def phase5_report(ctx):
    print('== phase5 对平报告（V1~V8）==')
    cr = env.cr

    def actual_or_pred(sql, pred, args=None):
        if DRY_RUN:
            return pred
        try:
            v = scalar(sql, args)
            return v if v is not None else 0
        except Exception:
            cr.rollback()
            return 'SQL异常'

    expected_rows = len(ctx['payreq']) - len(ctx['skip_sup']) - len(ctx['skip_dep']) \
        - len(ctx['skip_amt'])
    expected_sum = ctx['keep_sum']
    anchor_net = round(ANCHOR_PR_AMOUNT - ctx['skipped_sum'], 2)   # V2 对平锚：基线−跳过额
    rows = [
        ('V1 新条目数 = 请款行−跳过(%d)' % (len(ctx['skip_sup']) + len(ctx['skip_dep'])
                                            + len(ctx['skip_amt'])),
         expected_rows,
         actual_or_pred("SELECT count(*) FROM ta_dispatch_item WHERE note LIKE 'ETM|X|P%%'",
                        expected_rows)),
        ('V2 Σamount = %.2f−跳过额%.2f' % (ANCHOR_PR_AMOUNT, ctx['skipped_sum']),
         expected_sum,
         actual_or_pred("SELECT round(sum(amount)::numeric,2) FROM ta_dispatch_item "
                        "WHERE note LIKE 'ETM|X|P%%'", expected_sum)),
        ('V2b 旧实测Σamount vs 基线(锚差)', ctx['sum_all'], ANCHOR_PR_AMOUNT),
        ('V2c 对平锚：基线−跳过额', anchor_net, expected_sum),
        ('V5 合成条目删除额(目标库实况)', ctx['synth_sum'], ANCHOR_SYNTH_AMOUNT),
        ('V6 借支行数', len(ctx['loans']),
         actual_or_pred("SELECT count(*) FROM ta_guide_loan WHERE name LIKE 'ETM|GL|%%'",
                        len(ctx['loans']))),
        ('V6b Σoutstanding(入插借支, 模型口径=Σamount)', ctx['loan_amt_sum'],
         actual_or_pred("SELECT round(sum(outstanding)::numeric,2) FROM ta_guide_loan "
                        "WHERE name LIKE 'ETM|GL|%%'", ctx['loan_amt_sum'])),
        ('V6c 旧residual差额(已知偏差, 不直写compute)',
         round(ctx['loan_amt_sum'] - ctx['loan_res_sum'], 2),
         actual_or_pred("SELECT CASE WHEN abs(sum(outstanding) - %s) <= 0.01 "
                        "THEN 'OK' ELSE '差异!' END FROM ta_guide_loan "
                        "WHERE name LIKE 'ETM|GL|%%'", 'OK',
                        args=(ctx['loan_amt_sum'],))),
        ('V8a 凭证数不变（运行前后）', ctx['move_count0'],
         scalar("SELECT count(*) FROM account_move")),
        ('V8b 全库 posted Σ借−Σ贷 (应=0)', 0.0,
         money(scalar("SELECT COALESCE(round(sum(debit-credit),2),0) FROM account_move_line "
                      "WHERE parent_state='posted'"))),
        ('V8c 条目 move_id 非空数 (应=0)', 0,
         actual_or_pred("SELECT count(*) FROM ta_dispatch_item "
                        "WHERE note LIKE 'ETM|X|P%%' AND move_id IS NOT NULL", 0)),
    ]
    print('%-58s %20s %20s %s' % ('核对项', '基线/预测', '实测', '判定'))
    print('-' * 112)
    for name, base, act in rows:
        try:
            ok = abs(float(act) - float(base)) <= TOL
        except (TypeError, ValueError):
            ok = act == base
        print('%-58s %20s %20s %s' % (name, base, act, 'OK' if ok else '差异!'))
    print('-' * 112)

    print('V3 sup_type→kind 分布（入插条目）：')
    for (st, kind), c in sorted(ctx['sup2kind_cnt'].items(), key=lambda x: -x[1]):
        print('   %-14s → %-8s %6d' % (st, kind, c))
    print('   kind 合计：%s' % dict(ctx['kind_cnt']))
    print('V4 未命中清单：供应商 miss=%d（样例 %s）；团 miss=%d（样例 %s）；金额≤0=%d（样例 %s）'
          % (len(ctx['skip_sup']), ctx['skip_sup'][:5],
             len(ctx['skip_dep']), ctx['skip_dep'][:5],
             len(ctx['skip_amt']), ctx['skip_amt'][:5]))

    print('V7 抽样 3 团新旧成本对比（旧 Σout_price=团级参考口径 vs 新条目 Σ）：')
    top = sorted(ctx['by_dep'].items(), key=lambda x: -x[1])[:3]
    code_of_id = {v[0]: k for k, v in ctx['dep_by_code'].items()}
    for dep_id, tot in top:
        code = code_of_id.get(dep_id, '?')
        old_sum = ctx['cost_by_key'].get(code, 0.0)
        print('   dep=%-34s 旧out_price=%14.2f 新条目Σ=%14.2f' % (code, old_sum, tot))

    if DRY_RUN:
        print('[DRY-RUN] 「实测」=预测。目标库实况（只读）：dispatch.item(ETM|X|P)=%d、'
              '借支(ETM|GL)=%d、凭证数=%s' % (
                  ctx['prev_p_rows'], ctx['prev_loan_rows'], ctx['move_count0']))
    else:
        assert ctx['move_count0'] == scalar("SELECT count(*) FROM account_move"), \
            '凭证数变化（应零凭证）'
        assert abs(money(scalar("SELECT COALESCE(round(sum(debit-credit),2),0) "
                                "FROM account_move_line WHERE parent_state='posted'"))) < 0.005,\
            'posted 借贷差非 0'
        print('V8 零凭证断言通过（凭证数不变=%s，posted 借贷差=0）' % ctx['move_count0'])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print('MODE = %s' % ('DRY-RUN（只读预演，不落任何写）' if DRY_RUN else '正式迁移(批3-3)'))
    conn = old_connect()
    try:
        ctx = load_old(conn)
        print('旧库读取：payreq=%d loan=%d plan=%d supplier=%d' % (
            len(ctx['payreq']), len(ctx['loan']), len(ctx['plans']), len(ctx['suppliers'])))
        phase0_backup_check()
        load_target(ctx)
        phase1_build_items(ctx)
        phase2_build_loans(ctx)
        phase3_cleanup(ctx)
        phase4_write(ctx)
        phase5_report(ctx)
    finally:
        conn.close()
    print('== 完成（%s）==' % ('dry-run 全程未写入' if DRY_RUN else '正式迁移(批3-3)'))


# odoo shell 以 __name__=='__main__' 命名空间 exec 本文件（范式同批2）
if __name__ == '__main__':
    main()
