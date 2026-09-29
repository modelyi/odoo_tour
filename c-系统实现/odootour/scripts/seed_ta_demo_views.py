# -*- coding: utf-8 -*-
"""seed_ta_demo_views.py — 为 tour20 正式库补小规模 demo 数据，使两个空置 SQL 报表视图可演示：
  * ta.guide.performance（导游绩效）：需要 发团计划 guide_ids 排班 + 已结算佣金 + 已审核报账；
  * ta.scenic.contribution（景点毛利贡献）：需要 kind∈(ticket,scenic) 的已确认计调条目。
ETM 迁移历史团无法回填这两处（旧库 tour_plan_guide_rel 全空、成本已折叠为 kind='other' 合成行），
故造少量贴近真实的 DEMO|V 数据。

运行方式（odoo shell，stdin 喂脚本；参照 seed_ta_demo.py / migrate_tms19_to_ta.py）：
  sudo docker cp c-系统实现/odootour/scripts/seed_ta_demo_views.py odootour-odoo:/tmp/
  sudo docker exec -i odootour-odoo python3 /usr/lib/odoo/odoo-server/odoo-bin \
      shell -d tour20 --no-http -c /etc/odoo/odoo.conf --db_host=db < /tmp/seed_ta_demo_views.py

幂等：所有新记录 name/note 以 'DEMO|V|' 开头并按确定性键（含 departure id）去重——存在即跳过；
导游排班挂接前先检查该用户是否已在 guide_ids 中。random.seed(7) + 稳定候选集（ORDER BY id），
重跑选择结果一致，count 不翻倍。

约束遵守：
  * 不改动任何 ETM| 行的字段值；唯一例外 = ta.departure.guide_ids m2m 挂接（补排班，非改业务数据）。
  * 计调条目参照 ta_ask/tests/test_ask.py 的做法直接建 state='confirmed'（qty/unit_price 必填，
    amount=qty*unit_price 为 stored compute，route_id/date_start related、company_id default
    自动补齐，move_id 允许为空）→ 绕开 action_confirm 对默认费用科目/采购日记账的依赖，
    且不会产生任何凭证。
  * 佣金/报账优先走真实状态机（settle 无权限校验；approve 需 group_ta_accountant 且审核人≠导游
    本人）。实测库中 group_ta_guide 无成员 → 导游 submit 链路必失败，按预案降级：sudo 建单+
    推进，approved_by 仍记真实会计（不自审）。状态机动作在 SAVEPOINT+flush_all 内执行，
    延迟到 flush 才爆出的 AccessError 也能被捕获并回滚到动作前，再走降级路径。
  * 只写库、不 -u、不重启；分批 flush_all + commit（≤50）。
"""
import logging
import random
from datetime import date, timedelta

_log = logging.getLogger('seed_ta_demo_views')
random.seed(7)

PREFIX = 'DEMO|V'
BATCH = 50
DATE_LO, DATE_HI = date(2026, 5, 1), date(2026, 9, 30)
DEP_N = 30                 # 挑 ~30 个 ETM 发团
GUIDE_POOL_N = 15          # 导游账号池
SUPPLIER_N = 8             # 景点供应商数
COMMISSION_N = 10          # 已结算佣金
EXPENSE_N = 6              # 已审核报账
NO_MAIL_CTX = {'mail_notrack': True, 'mail_create_nosubscribe': True}
DEGRADED = []              # 降级路径留痕（汇报用）


def checkpoint():
    env.flush_all()
    env.cr.commit()
    _log.info('seed_ta_demo_views: batch flushed & committed')


def try_action(rec, method, user=None, label=''):
    """以 user 身份执行 rec.method()；try 内 flush_all 逼出延迟 ACL 错误；
    失败回滚到保存点（ORM 缓存一并失效）返回 False，成功 True。"""
    cr = env.cr
    cr.execute('SAVEPOINT sp_g')
    try:
        target = rec.with_user(user) if user is not None else rec
        getattr(target.with_context(mail_notrack=True), method)()
        env.flush_all()
        cr.execute('RELEASE SAVEPOINT sp_g')
        return True
    except Exception as e:                                # noqa: BLE001 — 权限链降级
        cr.execute('ROLLBACK TO SAVEPOINT sp_g')
        env.invalidate_all()
        _log.warning('seed_ta_demo_views: %s[%s] 失败→降级：%s',
                     label, rec.id if rec else '?', e)
        return False


# ---------------------------------------------------------------------------
# 选取候选：发团计划 / 导游用户 / 景点供应商
# ---------------------------------------------------------------------------
def pick_departures():
    """ETM 发团、date_start∈[2026-05, 2026-09]；优先挑有已确认订单（收入>0）的团，
    使绩效/景点视图的收入与毛利数值贴近真实。不足则从全体补齐。"""
    cr = env.cr
    cr.execute("""
        SELECT d.id FROM ta_departure d
        WHERE d.code LIKE 'ETM|D%%' AND d.date_start BETWEEN %s AND %s
          AND EXISTS (SELECT 1 FROM ta_order o WHERE o.departure_id = d.id
                        AND o.state IN ('confirmed','tripping','settled')
                        AND o.amount_paid > 0)
        ORDER BY d.id""", (DATE_LO, DATE_HI))
    rich = [r[0] for r in cr.fetchall()]
    if len(rich) < DEP_N:
        cr.execute("""
            SELECT d.id FROM ta_departure d
            WHERE d.code LIKE 'ETM|D%%' AND d.date_start BETWEEN %s AND %s
            ORDER BY d.id""", (DATE_LO, DATE_HI))
        rich += [i for i, r in enumerate(cr.fetchall()) if i not in set(rich)]
    picked = sorted(random.sample(rich, min(DEP_N, len(rich))))
    _log.info('seed_ta_demo_views: 选定发团 %s 个（优先收入>0 候选 %s）', len(picked), len(rich))
    return env['ta.departure'].sudo().browse(picked)


def pick_guide_pool():
    """复用既有迁移导游账号（login 形如 g<id>@tour.local）+ guide_t@test.local（若存在）。"""
    U = env['res.users'].sudo()
    users = U.search([('active', '=', True),
                      '|', ('login', 'like', 'g%@tour.local'),
                           ('login', '=', 'guide_t@test.local')])
    if not users:
        raise RuntimeError('库中无导游账号（g<id>@tour.local / guide_t@test.local）')
    has_test = bool(U.search_count([('login', '=', 'guide_t@test.local')]))
    ids = sorted(users.ids)
    pool = U.browse(sorted(random.sample(ids, min(GUIDE_POOL_N, len(ids)))))
    pool = pool.filtered(lambda u: u.partner_id)
    _log.info('seed_ta_demo_views: 导游池 %s 人（guide_t@test.local %s，迁移账号共 %s）',
              len(pool), '存在' if has_test else '不存在→跳过', len(ids))
    return pool


def pick_scenic_suppliers():
    """res_partner：ref LIKE 'ETM|S%' 且类目=景点（实测存在该类目，无需名字兜底；
    保留名字关键词偏好 景区/景点/公园/度假… 让展示更贴近真实）。"""
    cat = env['res.partner.category'].sudo().search([('name', '=', '景点')], limit=1)
    dom = [('ref', 'like', 'ETM|S%'), ('active', '=', True)]
    if cat:
        dom.append(('category_id', '=', cat.id))
    sups = env['res.partner'].sudo().search(dom, order='id')
    kw = ('景区', '景点', '公园', '度假', '森林', '湿地', '博物馆', '乐园', '影视城')
    named = sups.filtered(lambda p: any(k in (p.name or '') for k in kw))
    pool = named if len(named) >= 3 else sups
    if not pool:
        raise RuntimeError('未找到景点供应商（ETM|S% + 景点类目）')
    picked = sorted(random.sample(sorted(pool.ids), min(SUPPLIER_N, len(pool))))
    _log.info('seed_ta_demo_views: 景点供应商 %s 家（类目=%s，关键词命中 %s/%s）',
              len(picked), cat.name if cat else '无→按名字兜底', len(named), len(sups))
    return env['res.partner'].sudo().browse(picked)


# ---------------------------------------------------------------------------
# 1) 导游排班（guide_ids m2m —— ETM 行唯一允许的补录，见文件头说明）
# ---------------------------------------------------------------------------
def link_guides(deps, pool):
    linked = {}                        # departure_id -> [res.users]（本次选定应挂的导游）
    pool_list = list(pool)
    fresh_total = 0
    for n, dep in enumerate(deps, 1):
        chosen = random.sample(pool_list, random.choice([1, 2]))
        fresh = [u for u in chosen if u not in dep.guide_ids]
        if fresh:
            dep.write({'guide_ids': [(4, u.id, 0) for u in fresh]})
        fresh_total += len(fresh)
        linked[dep.id] = chosen
        if n % BATCH == 0:
            checkpoint()
    checkpoint()
    _log.info('seed_ta_demo_views: 排班挂接 %s 团 / 本次新挂 %s 人次（已挂自动跳过）',
              len(linked), fresh_total)
    return linked


# ---------------------------------------------------------------------------
# 2) 景点门票派工条目（直建 confirmed，绕科目依赖；口径同 ta_ask 测试）
#    每团 1–2 条：目标条数/条目参数用按 departure id 固定的种子 → 跨运行确定性；
#    且只增不减（目标条数 ≥ 库中已有最大序号），重跑 count 严格不变。
# ---------------------------------------------------------------------------
def seed_dispatch_items(deps, suppliers):
    I = env['ta.dispatch.item'].sudo().with_context(**NO_MAIL_CTX)
    sup_ids = sorted(suppliers.ids)
    made = skipped = 0
    for dep in deps:
        cnt = random.Random(900000 + dep.id).choice([1, 2])
        have = I.search([('name', 'like', '%s|DISP%d-' % (PREFIX, dep.id))])
        if have:
            cnt = max(cnt, max(int(n.rsplit('-', 1)[1]) for n in have.mapped('name')))
        for i in range(1, cnt + 1):
            name = '%s|DISP%d-%02d' % (PREFIX, dep.id, i)
            if I.search_count([('name', '=', name)]):
                skipped += 1
                continue
            rng = random.Random(900000 + dep.id * 100 + i)
            I.create({
                'name': name,
                'note': '%s 门票派工（演示）' % PREFIX,
                'departure_id': dep.id,
                'kind': 'ticket' if rng.random() < 0.7 else 'scenic',   # 约 7:3
                'supplier_id': sup_ids[rng.randrange(len(sup_ids))],
                'qty': 1.0,
                'unit_price': float(rng.randint(30, 150)),              # 定额，与团人数无关
                'state': 'confirmed',                                   # move_id 留空，不落账
            })
            made += 1
            if (made + skipped) % BATCH == 0:
                checkpoint()
    checkpoint()
    _log.info('seed_ta_demo_views: 计调条目 新建 %s / 已存在跳过 %s', made, skipped)


# ---------------------------------------------------------------------------
# 3) 佣金 + 报账（让绩效表更丰满）
# ---------------------------------------------------------------------------
def resolve_accountant():
    """参照 seed_ta_demo.py：取 group_ta_accountant 既有成员（佣金 settle 无科目/凭证依赖，
    不强制 account.group_account_manager）。"""
    grp = env.ref('ta_base.group_ta_accountant')
    cands = env['res.users'].sudo().search(
        [('group_ids', '=', grp.id), ('active', '=', True)])
    if not cands:
        raise RuntimeError('库中无 group_ta_accountant 成员，无法走报账审核链路')
    _log.info('seed_ta_demo_views: 使用既有会计 uid=%s (%s)', cands[0].id, cands[0].login)
    return cands[0]


def guide_of(dep, linked):
    """取该团本次选定（或已挂）的导游用户首位，佣金/报账以其 partner 入账。"""
    guides = linked.get(dep.id) or list(dep.guide_ids)
    return guides[0] if guides else None


def seed_commissions(deps, linked, accountant):
    C = env['ta.guide.commission'].sudo().with_context(**NO_MAIL_CTX)
    targets = []
    for dep in list(deps)[:COMMISSION_N]:
        name = '%s|CM%d' % (PREFIX, dep.id)
        c = C.search([('name', '=', name)], limit=1)
        if not c:
            u = guide_of(dep, linked)
            if not u or not u.partner_id:
                _log.warning('seed_ta_demo_views: 团 %s 无导游，跳过佣金', dep.code)
                continue
            d0 = dep.date_end or dep.date_start
            c = C.create({
                'name': name,
                'date': (d0 + timedelta(days=random.randint(0, 5))).isoformat(),
                'guide_id': u.partner_id.id,
                'departure_id': dep.id,
                'allowance': round(random.uniform(500.0, 1500.0), 2),
                'tax_rate': 0.06,
                'rule_note': '出团补贴 %d 天+零返佣（演示）' % random.randint(3, 8),
                'note': '%s 佣金（演示）' % PREFIX,
            })
        targets.append(c)
    checkpoint()
    settled = 0
    for c in targets:
        if c.state != 'draft':
            continue
        if not try_action(c, 'action_settle', accountant, label='佣金settle'):
            DEGRADED.append('commission#%s' % c.id)
            c.sudo().with_context(mail_notrack=True).action_settle()  # settle 本身无权限校验
        settled += 1
    checkpoint()
    _log.info('seed_ta_demo_views: 佣金 %s 张（本次推进 settle %s）', len(targets), settled)


def seed_expenses(deps, linked, accountant):
    E = env['ta.guide.expense'].sudo().with_context(**NO_MAIL_CTX)
    targets = []
    for dep in list(deps)[COMMISSION_N:COMMISSION_N + EXPENSE_N]:
        note = '%s|EXP%d' % (PREFIX, dep.id)
        exp = E.search([('note', '=', note), ('departure_id', '=', dep.id)], limit=1)
        u = guide_of(dep, linked)
        if not exp:
            if not u or not u.partner_id:
                _log.warning('seed_ta_demo_views: 团 %s 无导游，跳过报账', dep.code)
                continue
            d0 = dep.date_end or dep.date_start
            exp = E.create({
                'note': note,
                'date': (d0 + timedelta(days=random.randint(1, 10))).isoformat(),
                'guide_id': u.partner_id.id,
                'departure_id': dep.id,
                'line_ids': [(0, 0, {
                    'name': '%s 导游垫付（餐费/票务杂费）' % PREFIX,
                    'amount': round(random.uniform(100.0, 400.0), 2),
                    'invoice_ref': note.replace('|', '-'),
                })],
            })
        targets.append((exp, u))
    checkpoint()
    approved = 0
    for exp, u in targets:
        if exp.state in ('draft', 'rejected'):
            actor = u if (u and u.has_group('ta_base.group_ta_guide')
                          and u.partner_id == exp.guide_id) else None
            # 优先导游本人提交；库中 group_ta_guide 无成员 → actor 恒 None（预案降级）
            if actor is None or not try_action(exp, 'action_submit', actor, label='报账submit'):
                if actor is not None:
                    DEGRADED.append('expense#%s.submit' % exp.id)
                exp.sudo().with_context(mail_notrack=True).action_submit()
        if exp.state == 'submitted':
            if not try_action(exp, 'action_approve', accountant, label='报账approve'):
                DEGRADED.append('expense#%s.approve' % exp.id)
                # 降级直写：approved_by 仍记会计（≠导游本人，不违规自审）
                exp.sudo().write({'approved_by': accountant.id, 'state': 'approved'})
            approved += 1
    checkpoint()
    _log.info('seed_ta_demo_views: 报账 %s 单推进至 approved（本次 %s）', len(targets), approved)


# ---------------------------------------------------------------------------
# 4) verify（SQL 视图读取前先 env.flush_all() — 坑⑨）
# ---------------------------------------------------------------------------
def verify():
    env.flush_all()
    cr = env.cr

    def q(sql, args=None):
        cr.execute(sql, args or ())
        return cr.fetchall()

    perf = q('SELECT count(*) FROM ta_guide_performance')[0][0]
    scenic = q('SELECT count(*) FROM ta_scenic_contribution')[0][0]
    print('\n===== seed_ta_demo_views 核对 =====')
    print('ta.guide.performance   行数: %s %s' % (perf, 'OK' if perf > 0 else '!! 为空'))
    print('ta.scenic.contribution 行数: %s %s' % (scenic, 'OK' if scenic > 0 else '!! 为空'))
    print('\n-- 抽 2 行 景点毛利贡献（code/supplier/占比/贡献）--')
    for r in q("""SELECT sc.code, p.name, sc.ticket_cost, sc.cost_total, sc.income,
                         sc.profit, sc.cost_ratio, sc.profit_contribution
                  FROM ta_scenic_contribution sc
                  JOIN res_partner p ON p.id = sc.supplier_id
                  ORDER BY random() LIMIT 2"""):
        print('  %s | %s | 门票=%.2f 全团成本=%.2f 收入=%.2f 毛利=%.2f 占比=%.2f%% 贡献=%.2f' % r)
    print('\n-- 抽 1 行 导游绩效 --')
    for r in q("""SELECT gp.ym, p.name, gp.tour_count, gp.heads, gp.income, gp.cost_total,
                         gp.profit, gp.expense_count,
                         coalesce(gp.expense_lag_days, 0), gp.commission_net,
                         gp.loan_outstanding
                  FROM ta_guide_performance gp
                  JOIN res_partner p ON p.id = gp.guide_id
                  ORDER BY gp.tour_count DESC, random() LIMIT 1"""):
        print('  月=%s 导游=%s 带团=%s 人数=%s 收入=%.2f 成本=%.2f 毛利=%.2f '
              '报账单=%s 时效=%.1f天 佣金净额=%.2f 借支未清=%.2f' % r)
    print('\nDEMO|V 存量: 计调=%s 佣金=%s 报账(approved)=%s 排班团=%s' % (
        q("SELECT count(*) FROM ta_dispatch_item WHERE name LIKE %s", (PREFIX + '%',))[0][0],
        q("SELECT count(*) FROM ta_guide_commission WHERE name LIKE %s", (PREFIX + '%',))[0][0],
        q("SELECT count(*) FROM ta_guide_expense WHERE note LIKE %s AND state='approved'",
          (PREFIX + '%',))[0][0],
        q("""SELECT count(DISTINCT d.id) FROM ta_departure d
             JOIN res_users_ta_departure_rel rel ON rel.ta_departure_id = d.id
             JOIN res_users u ON u.id = rel.res_users_id
             WHERE d.code LIKE 'ETM|D%%'""")[0][0]))
    if DEGRADED:
        print('降级路径记录: %s' % ', '.join(DEGRADED))
    print('===================================\n')


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    _log.info('seed_ta_demo_views: begin')
    deps = pick_departures()
    pool = pick_guide_pool()
    suppliers = pick_scenic_suppliers()
    linked = link_guides(deps, pool)
    seed_dispatch_items(deps, suppliers)
    accountant = resolve_accountant()
    seed_commissions(deps, linked, accountant)
    seed_expenses(deps, linked, accountant)
    verify()
    _log.info('seed_ta_demo_views: done')


main()
