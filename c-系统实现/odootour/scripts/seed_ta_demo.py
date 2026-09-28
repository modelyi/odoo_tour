# -*- coding: utf-8 -*-
"""seed_ta_demo.py — 财务 MVP demo 造数脚本（ta.asset 资产卡片 + ta.expense 费用报销）

用途：
  为 tour20 库补小规模 demo 数据（新模块无历史数据）：
    * ta.asset 30 张（DEMO| 前缀）+ 每张 12 个月折旧记录，走 action_validate +
      action_create_move 真实链路，产生已过账凭证；
    * ta.expense 100 单（DEMO| 前缀），覆盖 draft/submitted/approved/rejected，
      approved 走 action_submit→action_approve 真实审批并生成费用凭证
      （审核人固定会计、报销人分散到 10 个 DEMO 内部用户，满足 AC-05 岗位分离）。

运行方式（odoo shell，stdin 喂脚本；本脚本不打印任何密码/连接串）：
  cd c-系统实现/tms-platform
  docker compose run --rm -i odoo python3 /usr/lib/odoo/odoo-bin \
      shell -d tour20 --no-http < /path/to/seed_ta_demo.py
  （宿主机脚本目录需可读，可用 -v 挂到容器内任意只读路径）

幂等：所有记录 name/code 以 'DEMO|' 开头；存在即跳过（资产按 code、费用按 name、
折旧按 (asset, period) 唯一键、凭证按 move_id）。分批 create + flush_all + commit。

random.seed(42) → 金额/日期完全可复现。日期范围 2025-07-01 → 2026-09-27。

Odoo 20 环境注意（本脚本已遵守）：
  * account.account 无 company_id 字段，创建时不传；
  * journal type 仅 sale/purchase/cash/bank/general；
  * ICP 写值用 search+create/update ir.config_parameter（set_int/set_param 不保证存在），
    读值用 get_int（模型源码内部使用）；
  * account.move / move.line 对非会计用户可能静默返回空集，读取断言一律 .sudo()；
  * message_post 用 message_type='comment'（本脚本用 mail_notrack 抑制自动跟踪消息）。
"""
import logging
import random
import secrets
from datetime import date, timedelta

_log = logging.getLogger('seed_ta_demo')

random.seed(42)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
PREFIX = 'DEMO|'
BATCH = 50

ASSET_N = 30
DEP_MONTHS = 12                      # 每张资产 12 期
ASSET_CATS = ['vehicle', 'office', 'furniture', 'electronic', 'other']
RESIDUAL_RATES = [0.0, 3.0, 5.0, 10.0]
DEP_MONTH_OPTIONS = [24, 36, 48, 60]  # 总折旧月数 > 12，保证 12 期均为足额月提
ACQ_START, ACQ_END = date(2025, 7, 1), date(2025, 9, 30)  # 12 期最迟到 2026-08

EXPENSE_N = 100
EXPENSE_MIX = [('draft', 15), ('submitted', 25), ('approved', 45), ('rejected', 15)]
EXPENSE_TYPES = ['office', 'travel', 'entertainment', 'freight', 'marketing', 'other']
EXPENSE_REASONS = {
    'office': '办公用品采购', 'travel': '出差交通住宿', 'entertainment': '客户招待',
    'freight': '快递杂费', 'marketing': '推广物料制作', 'other': '零星杂费',
}
EXP_START, EXP_END = date(2025, 7, 1), date(2026, 9, 27)

APPLICANT_LOGIN_FMT = 'demo_exp_%02d'
APPLICANT_NAME_FMT = PREFIX + '报销员%02d'
ACCOUNTANT_LOGIN = 'demo_accountant'
ACCOUNTANT_NAME = PREFIX + '会计'

NO_MAIL_CTX = {'mail_notrack': True, 'mail_create_nosubscribe': True,
               'no_reset_password': True}


def rdate(d1, d2):
    return d1 + timedelta(days=random.randint(0, (d2 - d1).days))


def checkpoint():
    env.flush_all()
    env.cr.commit()
    _log.info('seed_ta_demo: batch flushed & committed')


# ---------------------------------------------------------------------------
# 基础设施：科目 / 日记账 / ICP / 用户
# ---------------------------------------------------------------------------
def get_or_create_account(code, name, account_type, **extra):
    acc = env['account.account'].sudo().search([('code', '=', code)], limit=1)
    if not acc:
        vals = {'code': code, 'name': name, 'account_type': account_type}
        vals.update(extra)
        acc = env['account.account'].sudo().create(vals)
        _log.info('seed_ta_demo: 新建科目 %s %s', code, name)
    return acc


def get_or_create_journal(jtype, name, code):
    J = env['account.journal'].sudo()
    comp = env.company.id
    j = J.search([('code', '=', code), ('company_id', '=', comp)], limit=1) \
        or J.search([('type', '=', jtype), ('company_id', '=', comp)], limit=1)
    if not j:
        j = J.create({'name': name, 'code': code, 'type': jtype, 'company_id': comp})
        _log.info('seed_ta_demo: 新建日记账 %s (%s)', name, jtype)
    return j


def _valid_account(val):
    try:
        aid = int(val)
    except (TypeError, ValueError):
        return False
    return aid and env['account.account'].sudo().browse(aid).exists()


def set_param(key, value, overwrite=False):
    ICP = env['ir.config_parameter'].sudo()
    rec = ICP.search([('key', '=', key)], limit=1)
    if rec and not overwrite and _valid_account(rec.value):
        return  # 已有有效配置则保留（幂等重跑不覆盖既有设置）
    if rec:
        rec.value = str(value)
    else:
        ICP.create({'key': key, 'value': str(value)})


def ensure_base_data():
    company = env.company
    # 6 个科目（按 code get-or-create）
    acc_bank = get_or_create_account('1002', 'DEMO|银行存款', 'asset_cash')
    acc_recv = get_or_create_account('1122', 'DEMO|应收账款', 'asset_receivable')
    acc_pay = get_or_create_account('2241', 'DEMO|其他应付款', 'liability_payable')
    acc_exp = get_or_create_account('6601', PREFIX + '费用（管理）', 'expense')
    acc_dep = get_or_create_account('6602', PREFIX + '折旧费', 'expense_depreciation')
    acc_cum = get_or_create_account('1602', PREFIX + '累计折旧', 'asset_non_current')
    # 日记账：折旧凭证走通用、费用凭证走采购
    get_or_create_journal('general', PREFIX + '折旧凭证', 'DEMOGEN')
    get_or_create_journal('purchase', PREFIX + '费用凭证', 'DEMOEXP')
    # ICP（写值用 search+create/update；读值模型源码里用 get_int）
    set_param('ta_asset.depreciation_account_id', acc_dep.id)
    set_param('ta_asset.accumulated_account_id', acc_cum.id)
    set_param('ta_finance.payable_employee_account_id', acc_pay.id)
    if not company.sudo().expense_account_id:
        company.sudo().expense_account_id = acc_exp.id
    _log.info('seed_ta_demo: 基础科目/日记账/ICP 就绪（bank=%s recv=%s pay=%s）',
              acc_bank.code, acc_recv.code, acc_pay.code)
    checkpoint()


def _ensure_user(name, login, group_xmlids):
    U = env['res.users'].sudo()
    u = U.search([('login', '=', login)], limit=1)
    if u:
        return u
    groups = [env.ref(x).id for x in group_xmlids if env.ref(x, raise_if_not_found=False)]
    u = U.with_context(**NO_MAIL_CTX).create({
        'name': name, 'login': login,
        'password': secrets.token_urlsafe(16),   # 随机生成，绝不打印
        'group_ids': [(6, 0, groups)],            # Odoo 20: res.users.groups_id 已移除
        'company_ids': [(6, 0, [env.company.id])],
        'company_id': env.company.id,
    })
    _log.info('seed_ta_demo: 创建用户 %s (login=%s)', name, login)
    return u


def resolve_accountant():
    """找一个 group_ta_accountant 组成员；优先同时具备会计记账权限（可建/过凭证）的，
    否则 get-or-create 一个加入了 account.group_account_manager 的 DEMO|会计。"""
    grp = env.ref('ta_base.group_ta_accountant')
    mgr = env.ref('account.group_account_manager', raise_if_not_found=False)
    cands = env['res.users'].sudo().search(
        [('group_ids', '=', grp.id), ('active', '=', True)])
    for u in cands:
        if not mgr or mgr in u.sudo().group_ids:
            _log.info('seed_ta_demo: 使用既有会计用户 uid=%s', u.id)
            return u
    if cands:
        _log.warning('seed_ta_demo: 既有会计组成员均无记账权限(account.group_account_manager)，'
                     '改用具备权限的 DEMO|会计')
    else:
        _log.warning('seed_ta_demo: 库中无 group_ta_accountant 成员，改用 DEMO|会计')
    return _ensure_user(ACCOUNTANT_NAME, ACCOUNTANT_LOGIN,
                        ['base.group_user', 'ta_base.group_ta_accountant',
                         'account.group_account_invoice', 'account.group_account_manager'])


def get_applicants(n=10):
    return [_ensure_user(APPLICANT_NAME_FMT % i, APPLICANT_LOGIN_FMT % i,
                         ['base.group_user'])
            for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# 资产 + 折旧
# ---------------------------------------------------------------------------
def seed_assets(accountant):
    A = env['ta.asset'].sudo()
    assets = A.search([('code', '=like', PREFIX + 'FA%')])
    for i in range(1, ASSET_N + 1):
        code = '%sFA%03d' % (PREFIX, i)
        if any(a.code == code for a in assets):
            continue
        cost = float(random.randrange(30000, 300001, 100))
        assets |= A.create({
            'name': '%s固定资产%02d' % (PREFIX, i),
            'code': code,
            'category': random.choice(ASSET_CATS),
            'acquisition_date': rdate(ACQ_START, ACQ_END).isoformat(),
            'cost': cost,
            'residual_rate': random.choice(RESIDUAL_RATES),
            'depreciation_months': random.choice(DEP_MONTH_OPTIONS),
        })
        if len(assets) % BATCH == 0:
            checkpoint()
    checkpoint()

    # 状态机：draft → action_validate（with_user 会计）
    for n, a in enumerate(assets.filtered(lambda x: x.state == 'draft'), 1):
        a.with_user(accountant).with_context(mail_notrack=True).action_validate()
        if n % BATCH == 0:
            checkpoint()
    checkpoint()
    _log.info('seed_ta_demo: 资产卡片 %s 张（在用）', len(assets))
    return assets


def seed_depreciation(assets, accountant):
    D = env['ta.asset.depreciation'].sudo()
    made = D.browse()
    for a in assets:
        existing = {d.period: d for d in a.depreciation_line_ids}
        accumulated = sum(d.amount for d in existing.values())
        base = round(a.cost * (1 - a.residual_rate / 100.0), 2)
        ay, am = a.acquisition_date.year, a.acquisition_date.month
        for i in range(DEP_MONTHS):
            py, pm = ay + (am - 1 + i) // 12, (am - 1 + i) % 12 + 1
            p = '%04d-%02d' % (py, pm)
            if p in existing:
                continue
            remaining = round(base - accumulated, 2)
            amount = min(a.monthly_depreciation, max(remaining, 0.0))
            if amount <= 0:
                break
            made |= D.create({'asset_id': a.id, 'period': p,
                              'amount': round(amount, 2)})
            accumulated = round(accumulated + amount, 2)
            if len(made) % BATCH == 0:
                checkpoint()
    checkpoint()
    _log.info('seed_ta_demo: 新建折旧记录 %s 条，批量过账凭证', len(made))
    # 真实链路：action_create_move（内部幂等：move_id 已有值自动跳过）
    need = made.filtered(lambda d: not d.move_id)
    for i in range(0, len(need), BATCH):
        need[i:i + BATCH].with_user(accountant).action_create_move()
        checkpoint()
    return need


# ---------------------------------------------------------------------------
# 费用报销
# ---------------------------------------------------------------------------
def seed_expenses(accountant, applicants):
    E = env['ta.expense'].sudo()
    plan = []
    for st, n in EXPENSE_MIX:
        plan += [st] * n
    assert len(plan) == EXPENSE_N
    random.shuffle(plan)

    actions = []
    for i, goal in enumerate(plan, 1):
        name = '%sEXP%03d' % (PREFIX, i)
        exp = E.search([('name', '=', name)], limit=1)
        if not exp:
            d = rdate(EXP_START, EXP_END)
            etype = random.choice(EXPENSE_TYPES)
            exp = E.create({
                'name': name,
                'reason': '%s %s' % (EXPENSE_REASONS[etype], d.strftime('%Y%m%d')),
                'applicant_id': applicants[i % len(applicants)].id,
                'expense_type': etype,
                'date': d.isoformat(),
                'amount': round(random.uniform(80.0, 6000.0), 2),
            })
        actions.append((exp, goal))
        if i % BATCH == 0:
            checkpoint()
    checkpoint()

    # 状态机（只向前推进，天然幂等）：draft --submit(报销人)--> submitted
    #   --approve/reject(会计，审核人≠报销人 AC-05)--> approved / rejected
    for n, (exp, goal) in enumerate(actions, 1):
        applicant = exp.applicant_id
        if applicant == accountant:            # 防御：保证岗位分离
            applicant = applicants[0]
        if exp.state == 'draft' and goal in ('submitted', 'approved', 'rejected'):
            exp.with_user(applicant).with_context(mail_notrack=True).action_submit()
        if exp.state == 'submitted' and goal in ('approved', 'rejected'):
            step = exp.with_user(accountant).with_context(mail_notrack=True)
            if goal == 'approved':
                step.action_approve()          # 内部生成费用凭证（草稿，待付款）
            else:
                step.action_reject()
        if n % BATCH == 0:
            checkpoint()
    checkpoint()
    _log.info('seed_ta_demo: 费用报销 %s 单状态机推进完成', len(actions))


# ---------------------------------------------------------------------------
# 核对输出
# ---------------------------------------------------------------------------
def verify():
    cr = env.cr
    out = []
    cr.execute("SELECT count(*) FROM ta_asset WHERE name LIKE %s", (PREFIX + '%',))
    out.append(('资产卡片数(DEMO)', cr.fetchone()[0], ''))
    cr.execute("""SELECT count(*), coalesce(sum(d.amount), 0)
                  FROM ta_asset_depreciation d JOIN ta_asset a ON a.id = d.asset_id
                  WHERE a.name LIKE %s""", (PREFIX + '%',))
    r = cr.fetchone()
    out.append(('折旧记录数(DEMO)', r[0], '%.2f 元' % r[1]))
    cr.execute("""SELECT count(*) FROM account_move m
                  JOIN ta_asset_depreciation d ON d.move_id = m.id
                  JOIN ta_asset a ON a.id = d.asset_id
                  WHERE a.name LIKE %s AND m.state = 'posted'""", (PREFIX + '%',))
    out.append(('折旧凭证数(已过账)', cr.fetchone()[0], ''))
    cr.execute("""SELECT state, count(*), coalesce(sum(amount), 0)
                  FROM ta_expense WHERE name LIKE %s GROUP BY state ORDER BY state""",
               (PREFIX + '%',))
    for st, c, ssum in cr.fetchall():
        out.append(('费用[%s]' % st, c, '%.2f 元' % ssum))
    cr.execute("""SELECT count(*) FROM account_move m
                  JOIN ta_expense e ON e.move_id = m.id
                  WHERE e.name LIKE %s""", (PREFIX + '%',))
    out.append(('费用凭证数', cr.fetchone()[0], ''))
    print('\n===== seed_ta_demo 核对 =====')
    for label, cnt, extra in out:
        print('%-18s %8s  %s' % (label, cnt, extra))
    print('===========================\n')


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    _log.info('seed_ta_demo: begin')
    ensure_base_data()
    accountant = resolve_accountant()
    applicants = get_applicants(10)
    checkpoint()
    assets = seed_assets(accountant)
    seed_depreciation(assets, accountant)
    seed_expenses(accountant, applicants)
    verify()
    _log.info('seed_ta_demo: done')


main()
