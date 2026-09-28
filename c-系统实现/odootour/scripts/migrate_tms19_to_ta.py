# -*- coding: utf-8 -*-
"""
migrate_tms19_to_ta.py —— 原 TMS（tms 库 / tour_*）→ tour20（ta_*）数据迁移（odoo shell 脚本）

规格：b-蓝图/迁移规格-原TMS数据导入tour20.md（逐节实现）；协调人拍板覆盖 R1/R2/R3/R5/R7/R8。
幂等范式参照：c-系统实现/tms-platform/scripts/migrate_et_data.py。

== 运行方式（协调人执行）==
    # 1) 打通跨库网络（连通性实测结论见下）：
    #    sudo docker network connect tms-net odootour-odoo
    # 2) 注入旧库口令（严禁写入本文件/镜像）：
    #    export TMS_OLD_DB_PASSWORD='***'      # 值同 tms-odoo 容器 env.PGPASSWORD
    # 3) 拷入容器并以 odoo shell 运行（先保持 DRY_RUN=True 干跑核对）：
    sudo docker cp c-系统实现/odootour/scripts/migrate_tms19_to_ta.py odootour-odoo:/tmp/
    sudo docker exec -i -e TMS_OLD_DB_PASSWORD -e TMS_MIG_BACKUP_ACK=1 odootour-odoo \
      python3 /usr/lib/odoo/odoo-server/odoo-bin shell -d tour20 --no-http \
      --db_host=db --db_user=odoo --db_password=<新库口令> < /tmp/migrate_tms19_to_ta.py
    # 4) 跑完可还原网络：sudo docker network disconnect tms-net odootour-odoo

== 跨库连通实测结论（2026-09-28）==
- tms-db 容器在 `tms-net`（网络内 DNS 名 tms-db → 172.23.0.2:5432）；odootour-odoo 默认只在
  `odootour_odootour-net`：不附加网络时 getent tms-db 失败、直连 172.23.0.2:5432 超时（跨 bridge
  被隔离）；tms-db 无宿主机端口映射，127.0.0.1+映射端口方案不可行。
- 执行 `docker network connect tms-net odootour-odoo`（无需重启容器）后：DNS、TCP、psycopg2
  认证实测全部通过（SELECT count(*) FROM tour_plan = 86927）。**正式执行前必须先跑该 connect**。
- 兜底：若改用其他中转（如宿主机 socat/端口映射），用环境变量 TMS_OLD_DB_HOST / TMS_OLD_DB_PORT
  覆盖默认 tms-db / 5432 即可。

== DRY_RUN ==
下方常量 DRY_RUN 默认 True：全流程只做「读旧库 + 内存归并/摊价 + 读新库 + 打印对平报告」，
**不落任何写**（ORM create/write、raw INSERT/UPDATE/DELETE、期初凭证全部跳过）。
协调人核对 dry-run 报告后改 False 正式执行。各阶段幂等可重跑：正式模式 phase2 开头会按 §6
先精准 DELETE 全部 ETM 前缀数据（顺序 order_line→receivable_plan→order→departure→bank_line→
dispatch_item），再重建。

== 金额与口径（拍板项落地）==
- R1 价别折叠：老人/学生→adult，婴儿→child，不扩枚举。
- R2 应收基准：amount_total = tour_plan.in_com_quo_sum（后置 UPDATE 直写；173 单无名单时仍保
  amount_total 正确）；amount_paid = sum_pay_normal；amount_open = total − paid（stored compute，
  迁移数据直接 UPDATE，无需依赖重算）。line 单价按 §3 摊法：线路价打底 → 有成人线余量并成人线
  → 无线路价均摊、末位吸收舍入（Σline=round(total,2) 精确）。
- R3 成本：每个 ETM departure 组 Σout_price_quo_sum 造一条合成 ta.dispatch.item（kind='other'，
  name='历史成本(迁移合成)'，qty=1，unit_price=Σ，state 直置 'confirmed'，move_id 留空、绝不生成
  凭证，note='ETM|X<departure_id>'）。first_plan_id 实测全 NULL →「仅团计划代表行」判据落地为：
  组内承载 out_price_quo_sum>0 且非净额法(plan_type∉{5,41}) 的行，按 plan_code 去重取最小 id
  （实测这 660 行全是 plan_type=2/biz_mode=14 的并团成本记录行，即团成本代表行；去重无损）。
  supplier_id=组内出现频次最高的非景点供应商；无则用兜底 partner「历史成本(迁移)」。
- R5 收款：方案A 纯快照——pay_money>0 的 claim → 1 条 ta.bank.line（ref='ETM|C<id>'）；
  order.amount_paid 直写快照，**不建 shadow claim、不重放核销**。bank.line 的
  state/claimed_amount/residual 为 stored compute（依赖认领行，迁移恒为 0）→ 按快照直写：
  claim_state∈{2,3}→claimed/amount/0；{0,1}→to_claim/0/amount。
- R7/R8：期初一张凭证（BS-16）：Dr 1122 ΣAR_open、Dr 1002 ΣBank(=Σ tour_bank_account.balance
  9,228,332.70)、Cr 2202 ΣAP_open(=Σ合成成本)、Cr 4104 Equity；4001 建而不挂金额；不挂 partner。
  Equity = ΣAR_open + ΣBank − ΣAP_open（使 Σ借=Σ贷 恒成立；规格 §5 文字式为该恒等式的另一种
  移项）。幂等 ref='期初建账'。
- R4 已闭环：旧库 currency 仅「人民币/空」、exchange_rate≡1（实测 0 行≠1）；新库公司币种 USD ——
  金额按数值直录不换算，币种字段统一取公司币种。
- 已知口径尾差（报告呈现，不视为错误）：Σamount_open≈75.1M ≠ 旧 Σsum_un_pay≈14.6M（R2 取列
  差异，规格 §3「尾差进期初」——差额已由期初轧平进 4104）。

== Odoo 20 坑（已规避）==
account.account 无 company_id 列（code 为 compute↔company_dependent code_store，get-or-create 走
ORM search(code)，异常时 savepoint 回退 SQL code_store->>company_id）；journal.type 仅
sale/purchase/cash/bank/general；account.journal.code 是 readonly=False 的 stored compute
（precompute），create 显式传值可直落；ir.config_parameter 本脚本只读不写；旧库 numeric 列大量
NULL → 一律 COALESCE/兜底；全程不调用 message 相关 API（tracking_disable/mail_notrack）。
raw SQL 批量写不走 ORM（with_user 不适用），NOT NULL 列显式给：company_id、create_uid=超管id、
create_date/write_date 手工填。
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
TOL = 0.01       # 规格 §7 容差（±0.01×行数量级；单项报告按 ±0.01 判）

OLD_DB_HOST = os.environ.get('TMS_OLD_DB_HOST', 'tms-db')
OLD_DB_PORT = os.environ.get('TMS_OLD_DB_PORT', '5432')
OLD_DB_NAME = os.environ.get('TMS_OLD_DB_NAME', 'tms')
OLD_DB_USER = os.environ.get('TMS_OLD_DB_USER', 'odoo')

STATE_MAP = {  # 旧 tour_plan.state → 新 ta.order.state（规格 §1.7；实测 6 值全覆盖）
    'draft': 'draft', 'pending': 'draft',
    'confirmed': 'confirmed', 'operating': 'confirmed', 'in_progress': 'tripping',
    'completed': 'settled', 'archived': 'settled',
    'cancelled': 'cancel', 'refunded': 'cancel', 'void': 'cancel',
}
SUP_TYPE_LABEL = {  # 旧 sup_type → partner category（规格 §1.4，新模型无 sup_type 字段）
    'customer': '客户', 'ditch': '地接', 'hotel': '酒店', 'meal': '餐厅',
    'vehicle_comp': '车队', 'ticket': '票务', 'scenic': '景点', 'shop': '购物',
    'insurance': '保险', 'self_fee': '自费',
}
CAT_GUIDE, CAT_LEGACY = '导游', '历史成本'
LEGACY_SUP_NAME = '历史成本(迁移)'
ITEM_NAME = '历史成本(迁移合成)'
OPENING_REF = '期初建账'

NOW = datetime.datetime.now().replace(microsecond=0)
TODAY = NOW.date().isoformat()


# ---------------------------------------------------------------------------
# 纯函数工具
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
    """R10 脏日期规范化：颠倒交换、单侧缺失互补（实测 0 脏行，规则保留）。"""
    if b and e and e < b:
        b, e = e, b
    if b and not e:
        e = b
    if e and not b:
        b = e
    return b, e


def plan_kind(plan_type, biz_mode):
    """规格 §2.1：无独立计划表，kind 由 plan_type+biz_mode 判定。"""
    pt, bm = s(plan_type), s(biz_mode)
    if pt in ('5', '41'):
        return 'team'                      # 代订（净额法）归团队口径
    if pt == '1' or bm in ('1', '12', '21'):
        return 'team'
    if pt == '2' or bm in ('13', '14', '15', '31'):
        return 'fit'
    if pt == '7':                          # 跟随 first_plan；实测全 NULL → 按 biz_mode 回退
        return 'fit' if bm in ('13', '14', '15', '31') else 'team'
    return 'team'


def is_net_method(plan_type, biz_mode):
    """代收代付/代订（净额法）：规格 §3 不进成本。"""
    return s(plan_type) in ('5', '41') or s(biz_mode) == '41'


def merge_departure_state(order_states):
    """规格 §1.7 departure 组内聚合：
    有 confirmed/tripping→confirmed；全 settled→settled；全 cancel→cancel；否则 open。"""
    st = set(order_states)
    if st & {'confirmed', 'tripping'}:
        return 'confirmed'
    if st and st <= {'settled'}:
        return 'settled'
    if st and st <= {'cancel'}:
        return 'cancel'
    return 'open'


def allocate_amounts(total, kinds, price_adult, price_child):
    """规格 §3 line 单价摊法；保证 Σ == round(total,2)，末位吸收舍入：
    ① 能取到线路价→按价别取（R1 折叠后旧库 child 线路价实测全 0，自动落入均摊）；
    ② 有成人 line→余量并入成人 line；无成人→并入全部；
    ③ 线路价缺失→总额均摊。"""
    T = money(total)
    n = len(kinds)
    if n == 0:
        return []
    pa, pc = money(price_adult), money(price_child)
    if pa == 0 and pc == 0:                       # 全部均摊
        share = round(T / n, 2)
        base = [share] * n
        base[-1] = round(T - share * (n - 1), 2)
        return base
    base = [pa if k == 'adult' else pc for k in kinds]
    delta = round(T - round(sum(base), 2), 2)
    if abs(delta) >= 0.005:
        idx = [x for x, k in enumerate(kinds) if k == 'adult'] or list(range(n))
        share = round(delta / len(idx), 2)
        for x in idx[:-1]:
            base[x] = round(base[x] + share, 2)
        rest = round(delta - round(share * (len(idx) - 1), 2), 2)
        base[idx[-1]] = round(base[idx[-1]] + rest, 2)
    return [round(x, 2) for x in base]


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
    """一次性拉取旧数据（约 24 万行，内存可承受）。列序与 SELECT 对齐。"""
    ctx = {}
    ctx['lines'] = old_fetch(conn, """
        SELECT id, name, code, help_code, short_name, day_num, send_place, end_place,
               adult_price, child_price, old_man_price, student_price, baby_price,
               audit_state, fee_include, fee_exclude, guide_share_rate, is_abroad,
               is_special, active
        FROM tour_line ORDER BY id""")
    ctx['suppliers'] = old_fetch(conn, """
        SELECT id, name, sup_type, tax_payer_no, manager, manager_mobile, bank, account,
               remark, active, partner_id, province, city_name, location
        FROM tour_supplier ORDER BY id""")
    ctx['guides'] = old_fetch(conn, """
        SELECT id, name, guide_code, guide_account, tel, mobile, id_num, area, grade
        FROM tour_guide ORDER BY id""")
    ctx['banks'] = old_fetch(conn, """
        SELECT id, name, acc_number, balance, active, remark, power_area
        FROM tour_bank_account ORDER BY id""")
    ctx['plans'] = old_fetch(conn, """
        SELECT id, line_id, begin_date, end_date, plan_code, plan_name, contract_no,
               plan_type, biz_mode, state, supplier_id, order_date, guest_count, plan_num,
               in_com_quo_sum, out_price_quo_sum, sum_pay_normal, sum_un_pay
        FROM tour_plan ORDER BY id""")
    ctx['regs'] = old_fetch(conn, """
        SELECT id, plan_id, adult_num, child_num, old_man_num, baby_num, student_num, state
        FROM tour_plan_reg ORDER BY id""")
    ctx['claims'] = old_fetch(conn, """
        SELECT id, plan_id, supplier_id, account_id, pay_date, pay_money, claim_state,
               account_name_pay, name
        FROM tour_payment_claim ORDER BY id""")
    # tour_plan.supplier_id 指向旧 res_partner.id → 经 tour_supplier.partner_id 桥到 tour_supplier
    ctx['partner_to_sup'] = {r[1]: r[0] for r in old_fetch(
        conn, "SELECT id, partner_id FROM tour_supplier WHERE partner_id IS NOT NULL")}
    ctx['line_name'] = {r[0]: s(r[1], '未命名线路%s' % r[0]) for r in ctx['lines']}
    return ctx


# ---------------------------------------------------------------------------
# raw SQL 批量写（odoo env.cr；DRY_RUN 时不应被调用）
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


def chunk_update(cr, sql_head, rows):
    """UPDATE ... FROM (VALUES %s) v(...) WHERE ... 批量回写。"""
    if not rows:
        return 0
    total = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        parts = []
        for r in chunk:
            m = cr.mogrify('(' + ','.join(['%s'] * len(r)) + ')', r)
            parts.append(m if isinstance(m, str) else m.decode())
        cr.execute(sql_head + ','.join(parts))
        total += len(chunk)
        cr.commit()
    return total


def scalar(sql, args=None):
    env.cr.execute(sql, args)
    row = env.cr.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# phase0 备份检查
# ---------------------------------------------------------------------------
def phase0_backup_check():
    print('== phase0 备份检查 ==')
    print('  pg_dump 双备份（宿主机执行，dump 落在各容器 /tmp，注意备份介质归档）：')
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
# phase1 主数据：route / supplier / guide / bank journal（ORM upsert，幂等）
# ---------------------------------------------------------------------------
def phase1_master(ctx):
    print('== phase1 主数据 ==')
    cid = env.company.id
    cur_id = env.company.currency_id.id
    super_id = env.ref('base.user_root').id
    CTX = dict(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)

    # ---- partner category 字典 ----
    cat_map = {}
    for label in sorted(set(list(SUP_TYPE_LABEL.values()) + [CAT_GUIDE, CAT_LEGACY])):
        if DRY_RUN:
            cat_map[label] = 0
            continue
        C = env['res.partner.category'].with_context(**CTX)
        rec = C.with_context(active_test=False).search([('name', '=', label)], limit=1)
        if not rec:
            rec = C.create({'name': label})
        cat_map[label] = rec.id

    # ---- 业务模式码：任意码→正式码 id（别名 2→1 / 15→14 / 52→51）----
    bm_map = {}
    for m in env['ta.biz.mode'].with_context(active_test=False).search([]):
        target = m if not m.is_alias else m.alias_of
        if target:
            bm_map[m.code] = target.id
    print('  biz.mode 码位: %s' % sorted(bm_map))

    # ---- tour_line → ta.route（+ stop 支撑 days compute + price 五价折叠两价）----
    route_map, route_price = {}, {}
    R = env['ta.route'].with_context(**CTX)
    for (lid, name, lcode, help_code, short, day_num, send, endp,
         p_adult, p_child, p_old, p_stu, p_baby, audit, fee_inc, fee_exc,
         gshare, abroad, special, active) in ctx['lines']:
        rname = s(name).strip() or ('未命名线路%s' % lid)
        code = 'ETM|L%s' % lid
        note_bits = []
        for label, val in (('旧码', lcode), ('拼音码', help_code), ('简称', short)):
            if s(val):
                note_bits.append('%s:%s' % (label, s(val)))
        fold = ['老人/学生→adult', '婴儿→child']
        for val, tag in ((p_old, '老人价'), (p_stu, '学生价'), (p_baby, '婴儿价')):
            if money(val) > 0:
                fold.append('%s%.2f(并入%d)' % (tag, money(val),
                                                'child' if tag == '婴儿价' else 'adult'))
        desc_bits = []
        if s(send) or s(endp):
            desc_bits.append('发团/返回地：%s → %s' % (s(send, '-'), s(endp, '-')))
        if s(fee_inc):
            desc_bits.append('费用包含：%s' % s(fee_inc)[:800])
        if s(fee_exc):
            desc_bits.append('费用不含：%s' % s(fee_exc)[:800])
        misc = []
        if gshare:
            misc.append('导游分成率 %s' % gshare)
        if abroad:
            misc.append('出境线')
        if special:
            misc.append('特殊线')
        if misc:
            desc_bits.append('旧字段迁移：%s' % '；'.join(misc))
        pa, pc = money(p_adult), money(p_child)
        state = 'on_sale' if (s(audit) == 'approved' and pa > 0) else 'draft'
        route_price[lid] = (pa, pc)
        if DRY_RUN:
            route_map[lid] = lid  # 伪 id，仅供后续计数/摊价
            continue
        rec = R.with_context(active_test=False).search([('code', '=', code)], limit=1)
        vals = {'name': rname, 'code': code, 'state': state,
                'note': '；'.join(note_bits + fold)[:500],
                'description': ('<p>' + '</p><p>'.join(desc_bits) + '</p') if desc_bits else False,
                'active': active is not False, 'company_id': cid}
        if rec:
            keep = {'name': rname, 'code': code, 'company_id': cid,
                    'active': vals['active']}
            if rec.state != state:
                if state == 'on_sale':
                    keep['state'] = 'on_sale'          # 进入在售不触发约束
                else:
                    # 离开/保持非在售：若有未完结 ETM 发团则跳过 state 写，
                    # 避开 _check_open_departures（raw 插入的发团不受 ORM 约束）
                    blocking = env['ta.departure'].with_context(active_test=False).search_count(
                        [('route_id', '=', rec.id),
                         ('state', 'in', ('open', 'confirmed', 'departed'))])
                    if not blocking:
                        keep['state'] = state
            if keep.get('state', rec.state) == rec.state or rec.state == 'on_sale':
                keep.setdefault('note', vals['note'])
                keep.setdefault('description', vals['description'])
            rec.write(keep)
        else:
            rec = R.create(vals)
        route_map[lid] = rec.id
        n_stops = max(i(day_num, 1), 1)
        if len(rec.stop_ids) != n_stops:
            rec.stop_ids.unlink()
            env['ta.route.stop'].create(
                [{'route_id': rec.id, 'day_no': d, 'name': '第%d天' % d}
                 for d in range(1, n_stops + 1)])
        have = {(p.kind, money(p.amount)) for p in rec.price_ids}
        want = []
        if pa > 0:
            want.append(('adult', pa, '迁移：成人门市价'))
        if pc > 0:
            want.append(('child', pc, '迁移：儿童价'))
        for val, tag in ((p_old, '老人价'), (p_stu, '学生价'), (p_baby, '婴儿价')):
            if money(val) > 0:
                kind = 'child' if tag == '婴儿价' else 'adult'   # R1 折叠，不扩枚举
                want.append((kind, money(val), '迁移：%s→%s' % (tag, kind)))
        for kind, amt, pnote in want:
            if (kind, amt) not in have:
                env['ta.route.price'].create({'route_id': rec.id, 'kind': kind,
                                              'amount': amt, 'note': pnote,
                                              'currency_id': cur_id})
    if not DRY_RUN:
        env.cr.commit()
        env.invalidate_all()
    n_sale = sum(1 for lid in route_map
                 if route_price[lid][0] > 0)
    print('  route: %d 条（on_sale≈%d，adult 价>0；其余 draft）' % (len(route_map), n_sale))

    # ---- tour_supplier → res.partner（category+rank 表达角色）----
    sup_map, oldp_to_new = {}, {}
    if DRY_RUN:
        for row in ctx['suppliers']:
            sup_map[row[0]] = row[0]
            if row[10]:
                oldp_to_new[row[10]] = row[0]
    else:
        P = env['res.partner'].with_context(**CTX)
        for (sid, name, sup_type, vat, manager, mmobile, bank, account,
             remark, active, old_pid, prov, city, loc) in ctx['suppliers']:
            ref = 'ETM|S%s' % sid
            st = s(sup_type, 'customer')
            street = ' '.join(x for x in (s(prov), s(city), s(loc)) if x)
            comment = '；'.join(x for x in (('联系人 %s' % s(manager)) if s(manager) else '',
                                            ('电话 %s' % s(mmobile)) if s(mmobile) else '',
                                            ('开户 %s' % s(bank)) if s(bank) else '',
                                            ('账号 %s' % s(account)) if s(account) else '',
                                            s(remark)) if x)
            vals = {'name': s(name, '(无名供应商%s)' % sid), 'ref': ref,
                    'active': active is not False, 'vat': s(vat),
                    'phone': s(mmobile), 'street': street[:200],
                    'comment': comment[:2000], 'company_id': cid,
                    'customer_rank': 1 if st == 'customer' else 0,
                    'supplier_rank': 0 if st == 'customer' else 1}
            rec = P.with_context(active_test=False).search([('ref', '=', ref)], limit=1)
            if rec:
                rec.write(vals)
            else:
                rec = P.create(vals)
            cat = cat_map.get(SUP_TYPE_LABEL.get(st, st))
            if cat:
                rec.write({'category_id': [(4, cat)]})
            sup_map[sid] = rec.id
            if old_pid:
                oldp_to_new[old_pid] = rec.id
        env.cr.commit()
        env.invalidate_all()
    print('  supplier partner: %d 条（客户 customer_rank，其余 supplier_rank）' % len(sup_map))

    # ---- tour_guide → res.partner(导游) + res.users(账号) ----
    # guide_account 实测大量空(1170)/重复(66 distinct)→ 首个持有者保留，其余 g<id>@tour.local
    first_owner = {}
    for row in ctx['guides']:
        acc = s(row[3])
        if acc and acc not in first_owner:
            first_owner[acc] = row[0]
    guide_map = {}
    if DRY_RUN:
        for row in ctx['guides']:
            guide_map[row[0]] = row[0]
    else:
        U = env['res.users'].with_context(**CTX)
        for (gid, name, gcode, gacc, tel, mobile, idnum, area, grade) in ctx['guides']:
            acc = s(gacc)
            login = acc if (acc and first_owner.get(acc) == gid) else 'g%s@tour.local' % gid
            ref = 'ETM|G%s' % gid
            rec = U.with_context(active_test=False).search(
                [('partner_id.ref', '=', ref)], limit=1)
            if rec:
                rec.write({'name': s(name, '导游%s' % gid)})
                rec.partner_id.write({'ref': ref, 'phone': s(mobile) or s(tel),
                                      'category_id': [(4, cat_map[CAT_GUIDE])]})
            else:
                rec = U.create({'name': s(name, '导游%s' % gid), 'login': login,
                                'active': True, 'email': False})
                rec.partner_id.write({'ref': ref, 'phone': s(mobile) or s(tel),
                                      'category_id': [(4, cat_map[CAT_GUIDE])]})
            guide_map[gid] = rec.id
            if len(guide_map) % 500 == 0:
                env.cr.commit()
                env.invalidate_all()
        env.cr.commit()
        env.invalidate_all()
    print('  guide users: %d 条（login 去重回退 g<id>@tour.local，密码交付时统一重置）' % len(guide_map))

    # ---- tour_bank_account → account.journal(bank) + acc→journal 映射 ----
    bank_map, balances = {}, []
    for (bid, name, acc_no, balance, active, remark, power) in ctx['banks']:
        balances.append(money(balance))
        if DRY_RUN:
            bank_map[bid] = bid
            continue
        J = env['account.journal'].with_context(**CTX)
        code = 'ETM|B%s' % bid
        vals = {'name': s(name, '银户%s' % bid)[:64], 'code': code, 'type': 'bank',
                'company_id': cid, 'active': active is not False}
        rec = J.with_context(active_test=False).search([('code', '=', code)], limit=1)
        if rec:
            rec.write(vals)
        else:
            rec = J.create(vals)
        bank_map[bid] = rec.id
    if not DRY_RUN:
        env.cr.commit()
        env.invalidate_all()
    ctx['bank_map'] = bank_map
    ctx['sum_balance'] = round(sum(balances), 2)
    print('  bank journal: %d 条；Σbalance=%.2f（期初银行输入，R7 财务已确认可先按此值）' % (
        len(bank_map), ctx['sum_balance']))

    ctx.update(route_map=route_map, route_price=route_price, sup_map=sup_map,
               oldp_to_new=oldp_to_new, bm_map=bm_map, cid=cid, cur_id=cur_id,
               super_id=super_id, cat_map=cat_map)


# ---------------------------------------------------------------------------
# phase2 departures：归并 K=(line_id, begin, end)；同时产出 order_ctx
# ---------------------------------------------------------------------------
def phase2_departures(ctx):
    print('== phase2 departures 归并 ==')
    cid, super_id = ctx['cid'], ctx['super_id']
    bm_map = ctx['bm_map']
    groups = defaultdict(list)
    order_ctx = []
    for (pid, lid, b0, e0, pcode, pname, cno, ptype, bmode, st, sup_id,
         odate, guest, plan_num, in_quo, out_quo, pay_nor, un_pay) in ctx['plans']:
        b, e = norm_dates(b0, e0)
        key = (lid, b, e)
        o = dict(pid=pid, key=key, lid=lid, b=b, e=e,
                 kind=plan_kind(ptype, bmode), net=is_net_method(ptype, bmode),
                 state=STATE_MAP.get(s(st), 'draft'), biz=s(bmode),
                 sup=sup_id, odate=odate, guest=i(guest), pnum=i(plan_num),
                 total=money(in_quo), cost=money(out_quo), paid=money(pay_nor),
                 unpay=money(un_pay), pcode=s(pcode), pname=s(pname), cno=s(cno))
        groups[key].append(o)
        order_ctx.append(o)
    ctx['order_ctx'] = order_ctx
    ctx['groups'] = groups

    deps = []
    for key, rows in groups.items():
        lid, b, e = key
        rep = min(rows, key=lambda r: r['pid'])            # R11：多代表取最小 id
        # R3 成本聚合：承载 out_price_quo_sum 的行即“团成本记录行”（实测 660 行全部
        # plan_type=2/biz_mode=14 并团代表行，first_plan_id 判据不可用后的落地等价式）；
        # 排除净额法；组内按 plan_code 去重取最小 id（防并团重复计，实测本数据无重复、无损）
        seen, cost_sum = set(), 0.0
        for r in sorted(rows, key=lambda r: r['pid']):
            if not r['net'] and r['cost'] > 0 and r['pcode'] not in seen:
                seen.add(r['pcode'])
                cost_sum += r['cost']
        code = 'ETM|D|%s|%s|%s' % (lid, b, e)
        deps.append(dict(lid=lid, b=b, e=e, key=key, code=code,
                         name='%s %s' % (ctx['line_name'].get(lid, ''), code),
                         route_id=ctx['route_map'].get(lid),
                         biz_id=bm_map.get(rep['biz'], bm_map.get('12')),
                         state=merge_departure_state([r['state'] for r in rows]),
                         seats_total=max(max(r['pnum'] for r in rows),
                                         sum(r['guest'] for r in rows)),
                         cost=money(cost_sum), rows=rows))
    deps.sort(key=lambda d: d['code'])
    ctx['deps'] = deps
    print('  归并：plan %d 行 → departure %d 组（K=line|begin|end；distinct 校验基线）' % (
        len(order_ctx), len(deps)))

    # 重跑清理（§6）：FK 顺序删；DRY_RUN 不删
    if not DRY_RUN:
        for sql in (
            "DELETE FROM ta_order_line WHERE order_id IN (SELECT id FROM ta_order WHERE name LIKE 'ETM|P%')",
            "DELETE FROM ta_receivable_plan WHERE order_id IN (SELECT id FROM ta_order WHERE name LIKE 'ETM|P%')",
            "DELETE FROM ta_order WHERE name LIKE 'ETM|P%'",
            "DELETE FROM ta_departure WHERE code LIKE 'ETM|D%'",
            "DELETE FROM ta_bank_line WHERE ref LIKE 'ETM|C%'",
            "DELETE FROM ta_dispatch_item WHERE note LIKE 'ETM|X%'",
        ):
            env.cr.execute(sql)
        env.cr.commit()
        env.invalidate_all()
        print('  重跑清理完成（ETM 前缀精准删除，非迁移数据不动）')
        cols = ['company_id', 'route_id', 'biz_mode_id', 'seats_total', 'seats_used',
                'name', 'code', 'state', 'date_start', 'date_end',
                'create_uid', 'write_uid', 'create_date', 'write_date',
                'dispatch_cost_total']
        chunk_insert(env.cr, 'ta_departure', cols, [
            (cid, d['route_id'], d['biz_id'], d['seats_total'], 0,
             d['name'], d['code'], d['state'], d['b'], d['e'],
             super_id, super_id, NOW, NOW, 0.0) for d in deps])
        env.invalidate_all()
        env.cr.execute("SELECT id, code FROM ta_departure WHERE code LIKE 'ETM|D%'")
        id_by_code = dict((code, did) for did, code in env.cr.fetchall())
    else:
        print('  [DRY-RUN] 跳过清理与 departure INSERT')
        id_by_code = {d['code']: n for n, d in enumerate(deps, 1)}   # 伪 id 供预演
    for d in deps:
        d['id'] = id_by_code[d['code']]
        d['oid'] = None
    print('  departure id 映射：%d（含 seats_total=max(plan_num,Σguest_count)，seats_used 待 phase3 直写）' % len(deps))


# ---------------------------------------------------------------------------
# phase3 orders + lines + compute(store) 后置回写 + 期次 + seats_used
# ---------------------------------------------------------------------------
def phase3_orders(ctx):
    print('== phase3 orders（raw SQL 批量 + 后置回写）==')
    cid, super_id = ctx['cid'], ctx['super_id']
    bm_map = ctx['bm_map']
    keymap = {d['key']: d for d in ctx['deps']}

    # 名单展开（R1：old_man/student→adult、baby→child；cancelled reg 不展开）
    kinds_by_plan = defaultdict(list)     # plan_id → [(reg_id, kind), ...]
    line_expected = 0
    for (rid, pid, a, c, om, baby, stu, st) in ctx['regs']:
        if s(st) == 'cancelled':
            continue
        ks = (['adult'] * max(i(a), 0) + ['adult'] * max(i(om), 0) + ['adult'] * max(i(stu), 0)
              + ['child'] * max(i(c), 0) + ['child'] * max(i(baby), 0))
        if ks:
            kinds_by_plan[pid].extend((rid, k) for k in ks)
            line_expected += len(ks)
    ctx['line_expected'] = line_expected

    order_rows, line_rows = [], []
    heads_fix, totals_fix, state_fix = [], [], []
    clamped, zero_heads_non_draft = [], []
    for o in ctx['order_ctx']:
        d = keymap[o['key']]
        pname = 'ETM|P%s' % o['pid']
        o['pname'] = pname
        o['dep'] = d
        ks = [k for _r, k in kinds_by_plan.get(o['pid'], [])]
        unit = allocate_amounts(o['total'], ks, *ctx['route_price'].get(o['lid'], (0.0, 0.0)))
        paid = o['paid']
        if paid > o['total'] + TOL:       # 校验断言：越界记录并夹到 amount_total
            clamped.append((pname, paid, o['total']))
            paid = o['total']
        o['paid_clamped'] = paid
        order_rows.append((cid, d['id'], d['route_id'], o['kind'], 'draft',
                           ctx['oldp_to_new'].get(o['sup']),
                           bm_map.get(o['biz'], bm_map.get('12')),
                           o['odate'] or o['b'], pname,
                           '|'.join(x for x in (o['pcode'], o['cno'], o['pname']) if x)[:500],
                           False, 0, 0.0, 0.0, 0.0,          # seats_released/heads/total/paid/open
                           super_id, super_id, NOW, NOW))
        for seq, ((rid, k), up) in enumerate(zip(kinds_by_plan.get(o['pid'], []), unit), 1):
            line_rows.append((pname, seq * 10, '游客%s-%s' % (rid, seq), k, up))
        if ks:
            heads_fix.append((pname, len(ks)))
            if o['state'] != 'draft':
                state_fix.append((pname, o['state']))
        elif o['state'] != 'draft':
            zero_heads_non_draft.append(pname)   # heads=0 触发 CHECK → 留 draft，进报告
    ctx['clamped'] = clamped
    ctx['zero_heads'] = zero_heads_non_draft
    print('  order=%d（空名单非 draft→留 draft %d）、line=%d、amount_paid 越界夹紧=%d' % (
        len(order_rows), len(zero_heads_non_draft), len(line_rows), len(clamped)))

    if DRY_RUN:
        ctx['order_id_map'] = {o['pname']: n for n, o in enumerate(ctx['order_ctx'], 1)}
        print('  [DRY-RUN] 跳过 order/line INSERT 与回写')
    else:
        cols = ['company_id', 'departure_id', 'route_id', 'kind', 'state', 'partner_id',
                'biz_mode_id', 'date_confirm', 'name', 'note', 'seats_released',
                'heads', 'amount_total', 'amount_paid', 'amount_open',
                'create_uid', 'write_uid', 'create_date', 'write_date']
        chunk_insert(env.cr, 'ta_order', cols, order_rows)
        env.cr.execute("SELECT id, name FROM ta_order WHERE name LIKE 'ETM|P%'")
        ctx['order_id_map'] = {n: oid for oid, n in env.cr.fetchall()}
        om = ctx['order_id_map']
        lcols = ['company_id', 'order_id', 'sequence', 'name', 'kind', 'unit_price', 'amount',
                 'create_uid', 'write_uid', 'create_date', 'write_date']
        chunk_insert(env.cr, 'ta_order_line', lcols,
                     [(cid, om[p], sq, nm, k, up, up, super_id, super_id, NOW, NOW)
                      for (p, sq, nm, k, up) in line_rows])
        env.invalidate_all()
        # —— compute(store) 列后置回写（迁移数据不走 ORM 依赖重算）——
        chunk_update(env.cr,
                     'UPDATE ta_order o SET heads=v.h FROM (VALUES %s) AS v(pn,h) WHERE o.name=v.pn',
                     [(p, h) for p, h in heads_fix])
        chunk_update(env.cr,
                     'UPDATE ta_order o SET amount_total=v.t, amount_paid=v.p '
                     'FROM (VALUES %s) AS v(pn,t,p) WHERE o.name=v.pn',
                     [(o['pname'], o['total'], o['paid_clamped']) for o in ctx['order_ctx']])
        chunk_update(env.cr,
                     "UPDATE ta_order o SET state=v.s FROM (VALUES %s) AS v(pn,s) "
                     "WHERE o.name=v.pn AND o.heads > 0",
                     state_fix)
        env.cr.execute("UPDATE ta_order SET amount_open=round(amount_total-amount_paid,2) "
                       "WHERE name LIKE 'ETM|P%'")
        env.cr.commit()
        # 兜底断言：非 draft 必须 heads>0（ta_order_heads_check 同口径）
        env.cr.execute("SELECT count(*) FROM ta_order "
                       "WHERE name LIKE 'ETM|P%' AND state<>'draft' AND heads<=0")
        bad = env.cr.fetchone()[0]
        if bad:
            print('  !! heads=0 但状态非 draft 残留 %d → 强制回 draft' % bad)
            env.cr.execute("UPDATE ta_order SET state='draft' "
                           "WHERE name LIKE 'ETM|%' AND state<>'draft' AND heads<=0")
            env.cr.commit()

        # —— 期次（§4：每 order 一条；纯快照，amount_paid 直写）——
        pc = ['company_id', 'order_id', 'name', 'due_date', 'amount', 'amount_paid', 'note',
              'create_uid', 'write_uid', 'create_date', 'write_date']
        chunk_insert(env.cr, 'ta_receivable_plan', pc, [
            (cid, om[o['pname']], 'ETM|P%s' % om[o['pname']], o['dep']['b'],
             o['total'], o['paid_clamped'], '迁移期次(纯快照 R5-A)',
             super_id, super_id, NOW, NOW) for o in ctx['order_ctx']])

        # —— departure.seats_used 直写（不调 change_seats）；seats_total 保底 ≥ seats_used ——
        env.cr.execute(
            "UPDATE ta_departure d SET seats_used=s.c, "
            " seats_total=CASE WHEN d.seats_total < s.c THEN s.c ELSE d.seats_total END "
            "FROM (SELECT o.departure_id, count(l.id) AS c FROM ta_order o "
            "      JOIN ta_order_line l ON l.order_id = o.id "
            "      WHERE o.name LIKE 'ETM|P%' GROUP BY o.departure_id) s "
            "WHERE d.id = s.departure_id")
        env.cr.commit()
        env.invalidate_all()
        print('  回写完成：heads/amount_total/amount_paid/state/amount_open/期次/seats_used')

    # —— 期初与对平输入（两种模式同口径，内存计算）——
    ctx['sum_total'] = round(sum(o['total'] for o in ctx['order_ctx']), 2)
    ctx['sum_paid'] = round(sum(o['paid_clamped'] for o in ctx['order_ctx']), 2)
    ctx['sum_ar_open'] = round(ctx['sum_total'] - ctx['sum_paid'], 2)
    ctx['sum_un_pay'] = round(sum(o['unpay'] for o in ctx['order_ctx']), 2)
    ctx['sum_clamp_excess'] = round(sum(p - t for _n, p, t in clamped), 2)
    print('  Σamount_total=%.2f  Σamount_paid=%.2f  ΣAR_open=%.2f（旧 Σsum_un_pay=%.2f，'
          '口径差进期初轧平，见头注）' % (ctx['sum_total'], ctx['sum_paid'],
                                          ctx['sum_ar_open'], ctx['sum_un_pay']))


# ---------------------------------------------------------------------------
# phase4 bank.line：收款纯快照（R5 方案A；amount_paid 已在 phase3 直写，不重放核销）
# ---------------------------------------------------------------------------
def phase4_bankline_paid(ctx):
    print('== phase4 bank.line 收款快照 ==')
    cid, super_id, cur_id = ctx['cid'], ctx['super_id'], ctx['cur_id']
    fallback = None
    if not DRY_RUN:
        env.cr.execute("SELECT min(id) FROM account_journal "
                       "WHERE type='bank' AND code LIKE 'ETM|B%'")
        fallback = env.cr.fetchone()[0]
        if not fallback:
            env.cr.execute("SELECT min(id) FROM account_journal WHERE type='bank'")
            fallback = env.cr.fetchone()[0]
        if not fallback:
            raise RuntimeError('无 bank 日记账，无法定位缺省收款账户')
    rows, cnt, sum_pay, skipped = [], 0, 0.0, 0
    for (clid, plan_id, sup_id, acc_id, pay_date, pay_money, cstate, acc_name, name) in ctx['claims']:
        amt = money(pay_money)
        if amt <= 0:                       # R12：0/负金额跳过
            skipped += 1
            continue
        cnt += 1
        sum_pay = round(sum_pay + amt, 2)
        jid = ctx['bank_map'].get(acc_id) or fallback or 1
        claimed = s(cstate) in ('2', '3')  # 已审核/已平账 → 快照记 claimed
        rows.append((cid, cur_id, jid, ctx['oldp_to_new'].get(sup_id), super_id,
                     pay_date or TODAY, amt, 'ETM|C%s' % clid,
                     ('旧收款单:%s' % s(name))[:200], s(acc_name)[:200],
                     'claimed' if claimed else 'to_claim',
                     amt if claimed else 0.0, 0.0 if claimed else amt,
                     super_id, super_id, NOW, NOW))
    ctx['claim_cnt_pos'], ctx['claim_sum'] = cnt, sum_pay
    print('  claim %d → bank.line %d（跳过 0/负金额 %d），Σpay_money=%.2f' % (
        len(ctx['claims']), cnt, skipped, sum_pay))
    if DRY_RUN:
        print('  [DRY-RUN] 跳过 bank.line INSERT')
        return
    cols = ['company_id', 'currency_id', 'journal_id', 'partner_id', 'registered_by',
            'date', 'amount', 'ref', 'note', 'partner_name',
            'state', 'claimed_amount', 'residual',
            'create_uid', 'write_uid', 'create_date', 'write_date']
    chunk_insert(env.cr, 'ta_bank_line', cols, rows)
    env.invalidate_all()
    print('  bank.line 入库完成（不建 shadow claim；amount_paid 以 sum_pay_normal 快照为准）')


# ---------------------------------------------------------------------------
# phase5 合成成本条目（R3）
# ---------------------------------------------------------------------------
def phase5_synth_cost_items(ctx):
    print('== phase5 合成成本 ta.dispatch.item ==')
    cid, super_id = ctx['cid'], ctx['super_id']
    scenic_sup = {row[0] for row in ctx['suppliers'] if s(row[2]) == 'scenic'}
    sup_of_oldp = ctx['oldp_to_new']
    rows = []
    for d in ctx['deps']:
        if d['cost'] <= 0:
            continue
        cnt = Counter()
        for o in d['rows']:
            np = sup_of_oldp.get(o['sup']) if o['sup'] and o['sup'] not in scenic_sup else None
            if np:
                cnt[np] += 1
        rows.append(dict(departure=d['id'], route=d['route_id'],
                         supplier=cnt.most_common(1)[0][0] if cnt else None,
                         cost=d['cost']))
    ctx['sum_ap'] = round(sum(r['cost'] for r in rows), 2)
    n_legacy = sum(1 for r in rows if r['supplier'] is None)
    print('  合成条目=%d 条 / ΣAP_open=%.2f（景点供应商已排除；无供应商组=%d → 兜底 partner）' % (
        len(rows), ctx['sum_ap'], n_legacy))
    if DRY_RUN:
        print('  [DRY-RUN] 跳过 dispatch.item INSERT')
        return
    legacy = env['res.partner'].with_context(active_test=False).search(
        [('ref', '=', 'ETM|LEGACY')], limit=1)
    if not legacy:
        CTX = dict(tracking_disable=True, mail_notrack=True)
        legacy = env['res.partner'].with_context(**CTX).create(
            {'name': LEGACY_SUP_NAME, 'ref': 'ETM|LEGACY', 'supplier_rank': 1, 'company_id': cid})
        legacy.write({'category_id': [(4, ctx['cat_map'][CAT_LEGACY])]})
        env.cr.commit()
    cols = ['company_id', 'departure_id', 'route_id', 'supplier_id', 'kind', 'name',
            'qty', 'unit_price', 'amount', 'state', 'move_id', 'note',
            'create_uid', 'write_uid', 'create_date', 'write_date']
    chunk_insert(env.cr, 'ta_dispatch_item', cols, [
        (cid, r['departure'], r['route'], r['supplier'] or legacy.id, 'other', ITEM_NAME,
         1.0, r['cost'], r['cost'], 'confirmed', None,      # move_id 留空：绝不出凭证
         'ETM|X%s' % r['departure'], super_id, super_id, NOW, NOW) for r in rows])
    env.invalidate_all()
    print('  合成成本入库完成（state=confirmed、move_id 全空）')


# ---------------------------------------------------------------------------
# phase6 期初凭证（BS-16 一张；幂等 ref='期初建账'）
# ---------------------------------------------------------------------------
def _acct_by_code(code, name, acct_type, cid):
    """Odoo 20：account.account 无 company_id；code 为 compute↔code_store（公司相关）。"""
    A = env['account.account'].with_context(active_test=False)
    acc = None
    try:
        with env.cr.savepoint():
            acc = A.search([('code', '=', code)], limit=1)
    except Exception:
        acc = None
    if acc:
        return acc
    env.cr.execute("SELECT id FROM account_account WHERE code_store->>%s = %s",
                   (str(cid), code))
    r = env.cr.fetchone()
    if r:
        return env['account.account'].browse(r[0])
    return A.create({'code': code, 'name': name, 'account_type': acct_type})


def phase6_opening_move(ctx):
    print('== phase6 期初凭证（BS-16）==')
    cid = ctx['cid']
    ar, bank = ctx['sum_ar_open'], ctx['sum_balance']
    ap = ctx.get('sum_ap', 0.0)
    equity = round(ar + bank - ap, 2)     # 恒等式：Dr(ar+bank) == Cr(ap+equity)
    assert abs((ar + bank) - (ap + equity)) < 0.005, '期初不平（算术异常）'
    print('  Dr1122=%.2f  Dr1002=%.2f  Cr2202=%.2f  Cr4104(Equity)=%.2f' % (ar, bank, ap, equity))
    ctx['opening'] = dict(ar=ar, bank=bank, ap=ap, equity=equity)
    if DRY_RUN:
        print('  [DRY-RUN] 跳过科目/日记账/凭证写入')
        return
    if env['account.move'].with_context(active_test=False).search_count(
            [('ref', '=', OPENING_REF)]):
        print('  幂等：ref=期初建账 凭证已存在，跳过')
        return
    a_ar = _acct_by_code('1122', '应收账款', 'asset_receivable', cid)
    a_bank = _acct_by_code('1002', '银行存款', 'asset_cash', cid)
    a_ap = _acct_by_code('2202', '应付账款', 'liability_payable', cid)
    _acct_by_code('4001', '实收资本', 'equity', cid)          # 建而不挂金额（R7 拍板）
    a_re = _acct_by_code('4104', '未分配利润', 'equity', cid)
    J = env['account.journal'].with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    jrn = J.with_context(active_test=False).search([('code', '=', 'OPEN')], limit=1)
    if not jrn:
        jrn = J.create({'name': '期初建账', 'code': 'OPEN', 'type': 'general',
                        'company_id': cid})
    lines = []
    for amount, acc, label in ((ar, a_ar, '期初应收(迁移)'),
                               (bank, a_bank, '期初银行(迁移)'),
                               (ap, a_ap, '期初应付-历史成本(迁移合成)'),
                               (equity, a_re, '期初权益(未分配利润，迁移轧平)')):
        if abs(amount) < 0.005:
            continue
        lines.append((0, 0, {'name': label, 'account_id': acc.id,
                             'debit': max(amount, 0.0), 'credit': max(-amount, 0.0)}))
    move = env['account.move'].create({'move_type': 'entry', 'journal_id': jrn.id,
                                       'date': TODAY, 'ref': OPENING_REF,
                                       'line_ids': lines})
    dr = sum(move.line_ids.mapped('debit'))
    cr_ = sum(move.line_ids.mapped('credit'))
    assert abs(dr - cr_) < 0.005, '期初分录借贷不平 %.2f vs %.2f' % (dr, cr_)
    move.action_post()
    env.cr.commit()
    env.invalidate_all()
    print('  期初凭证已入账 id=%s（不挂 partner，R8；Equity 全进 4104）' % move.id)


# ---------------------------------------------------------------------------
# phase7 对平报告（规格 §7 V1~V16）
# ---------------------------------------------------------------------------
def phase7_report(ctx):
    print('== phase7 对平报告（§7 V1~V16）==')
    cr = env.cr

    def actual_or_pred(sql, pred):
        if DRY_RUN:
            return pred
        try:
            v = scalar(sql)
            return v if v is not None else 0
        except Exception:
            cr.rollback()
            return pred

    eq = ctx.get('opening', {})
    rows = [
        ('V1 order 数 = 旧 plan 行数', len(ctx['order_ctx']),
         actual_or_pred("SELECT count(*) FROM ta_order WHERE name LIKE 'ETM|P%'",
                        len(ctx['order_ctx']))),
        ('V2 line 行数 = Σ价别人数', ctx['line_expected'],
         actual_or_pred("SELECT count(*) FROM ta_order_line l JOIN ta_order o ON o.id=l.order_id "
                        "WHERE o.name LIKE 'ETM|P%'", ctx['line_expected'])),
        ('V3 Σamount_total = Σin_com_quo_sum', ctx['sum_total'],
         actual_or_pred("SELECT round(sum(amount_total),2) FROM ta_order "
                        "WHERE name LIKE 'ETM|P%'", ctx['sum_total'])),
        ('V4 Σamount_paid = Σsum_pay_normal(夹后)', ctx['sum_paid'],
         actual_or_pred("SELECT round(sum(amount_paid),2) FROM ta_order "
                        "WHERE name LIKE 'ETM|P%'", ctx['sum_paid'])),
        ('V5 Σamount_open(口径=total-paid)', ctx['sum_ar_open'],
         actual_or_pred("SELECT round(sum(amount_open),2) FROM ta_order "
                        "WHERE name LIKE 'ETM|P%'", ctx['sum_ar_open'])),
        ('V5b 旧 Σsum_un_pay(参考基线)', ctx['sum_un_pay'], ctx['sum_un_pay']),
        ('V6 bank.line 数 = Σpay_money>0', ctx['claim_cnt_pos'],
         actual_or_pred("SELECT count(*) FROM ta_bank_line WHERE ref LIKE 'ETM|C%'",
                        ctx['claim_cnt_pos'])),
        ('V7 Σbank.line.amount = Σpay_money', ctx['claim_sum'],
         actual_or_pred("SELECT round(sum(amount),2) FROM ta_bank_line "
                        "WHERE ref LIKE 'ETM|C%'", ctx['claim_sum'])),
        ('V8 departure 数 = distinct(line,begin,end)', len(ctx['deps']),
         actual_or_pred("SELECT count(*) FROM ta_departure WHERE code LIKE 'ETM|D%'",
                        len(ctx['deps']))),
        ('V9 route 数', len(ctx['lines']),
         actual_or_pred("SELECT count(*) FROM ta_route WHERE code LIKE 'ETM|L%'",
                        len(ctx['lines']))),
        ('V10 供应商 partner 数', len(ctx['suppliers']),
         actual_or_pred("SELECT count(*) FROM res_partner WHERE ref LIKE 'ETM|S%'",
                        len(ctx['suppliers']))),
        ('V11 导游 partner 数', len(ctx['guides']),
         actual_or_pred("SELECT count(*) FROM res_partner WHERE ref LIKE 'ETM|G%'",
                        len(ctx['guides']))),
        ('V12 bank journal 数', len(ctx['banks']),
         actual_or_pred("SELECT count(*) FROM account_journal WHERE code LIKE 'ETM|B%'",
                        len(ctx['banks']))),
        ('V13 期初借1002 = Σbalance', ctx['sum_balance'],
         actual_or_pred("SELECT round(sum(l.debit-l.credit),2) FROM account_move_line l "
                        "JOIN account_move m ON m.id=l.move_id "
                        "WHERE m.ref='期初建账'", ctx['sum_balance'])),
        ('V14 期初凭证 Σ借−Σ贷 (应=0)', 0.0,
         actual_or_pred("SELECT round(sum(debit)-sum(credit),2) FROM account_move_line l "
                        "JOIN account_move m ON m.id=l.move_id "
                        "WHERE m.ref='期初建账'", 0.0)),
        ('V15 全库 posted Σ借−Σ贷 (应=0)', 0.0,
         actual_or_pred("SELECT round(sum(debit-credit),2) FROM account_move_line "
                        "WHERE parent_state='posted'", 0.0)),
        ('V16 历史订单级凭证数 (应=0)', 0,
         actual_or_pred("SELECT count(*) FROM account_move WHERE ref LIKE 'ETM%'", 0)),
    ]
    print('%-50s %20s %20s %s' % ('核对项', '基线/预测', '实测', '判定'))
    print('-' * 108)
    for name, base, act in rows:
        try:
            ok = abs(float(act) - float(base)) <= TOL
        except (TypeError, ValueError):
            ok = False
        print('%-50s %20s %20s %s' % (name, base, act, 'OK' if ok else '差异!'))
    print('-' * 108)
    print('补充：amount_paid 越界夹紧 %d 单（超出合计 %.2f → 期初轧平）；'
          '空名单本应非 draft 滞留 draft %d 单；期初 Equity=%.2f' % (
              len(ctx.get('clamped', [])), ctx.get('sum_clamp_excess', 0.0),
              len(ctx.get('zero_heads', [])), ctx.get('opening', {}).get('equity', 0.0)))
    if DRY_RUN:
        print('[DRY-RUN] 「实测」列=预测值。目标库当前实况（只读）：')
        for label, sql in (('ta_order', "SELECT count(*) FROM ta_order"),
                           ('ta_departure', "SELECT count(*) FROM ta_departure"),
                           ('ta_route', "SELECT count(*) FROM ta_route"),
                           ('ta_bank_line', "SELECT count(*) FROM ta_bank_line"),
                           ('ta_dispatch_item', "SELECT count(*) FROM ta_dispatch_item")):
            try:
                print('  %-18s = %s' % (label, scalar(sql)))
            except Exception:
                cr.rollback()
                print('  %-18s = ?' % label)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print('MODE = %s' % ('DRY-RUN（只读预演，不落任何写）' if DRY_RUN else '正式迁移'))
    conn = old_connect()
    try:
        ctx = load_old(conn)
        print('旧库读取：line=%d supplier=%d guide=%d bank=%d plan=%d reg=%d claim=%d' % (
            len(ctx['lines']), len(ctx['suppliers']), len(ctx['guides']),
            len(ctx['banks']), len(ctx['plans']), len(ctx['regs']), len(ctx['claims'])))
        phase0_backup_check()
        phase1_master(ctx)
        phase2_departures(ctx)
        phase3_orders(ctx)
        phase4_bankline_paid(ctx)
        phase5_synth_cost_items(ctx)
        phase6_opening_move(ctx)
        phase7_report(ctx)
    finally:
        conn.close()
    print('== 完成（%s）==' % ('dry-run 全程未写入' if DRY_RUN else '正式迁移'))


# odoo shell 以 __name__=='__main__' 命名空间 exec 本文件（范式同 migrate_et_data.py）
if __name__ == '__main__':
    main()
