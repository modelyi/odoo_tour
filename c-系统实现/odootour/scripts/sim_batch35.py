# -*- coding: utf-8 -*-
"""批3.5 用户视角完整仿真（数据保留，'仿真|' 前缀可辨识）。

运行（容器内 odoo shell，事务式：任一非预期异常回滚，不留半截数据）:
  docker exec -i odootour-odoo sh -c 'export PGPASSWORD=$(python3 -c "...");
  python3 /usr/lib/odoo/odoo-server/odoo-bin shell -d tour20 --no-http \
  -c /etc/odoo/odoo.conf --db_host=db --db_user=odoo --db_password=$PGPASSWORD' \
  < scripts/sim_batch35.py

场景：仿真|海南5日游-20261001（route 432）→ BQ00266（dep 92519，20 座）
  O1 4 大 2 小 8000 已确认（本脚本修正 2 行价别为儿童）
  O2 2 大 3200 全款            O3 3 大 1 小 5600 未付（账龄）
  O4 探针：9 人确认 → 预期超位拦截（余 8）
  计调 4 项（景区/酒店/车队/餐厅）→ 供应商账单过账 → 付款 3960，欠 1400
  收款 2 笔（5000/3200）→ 三级审核 O2C（出纳登记→销售认领→会计审核）
  导游借支 3000 → 导游报账 600 → 佣金 1200 冲抵 → 未结清 1800
  费用报销 400（凭证留草稿）   固定资产 8000/36 月/5% → 2026-09 折旧 211.11 过账
幂等：各阶段以 '仿真|批3.5' 标记 get-or-create，重跑不重复造数。
"""
import secrets
import traceback

from odoo import fields
from odoo.exceptions import AccessError, UserError

SIM = '仿真|批3.5'
NO_MAIL_CTX = {'mail_notrack': True, 'mail_create_nosubscribe': True,
               'no_reset_password': True}

ADMIN = env['res.users'].browse(2)
P_CUSTOMER = env['res.partner'].search([('name', '=', '仿真|客户-散客甲')], limit=1)
P_GUIDE = env['res.partner'].search([('name', '=', '仿真|导游-林海')], limit=1)
P_SCENIC = env['res.partner'].search([('name', '=', '仿真|三亚湾景区')], limit=1)
P_HOTEL = env['res.partner'].search([('name', '=', '仿真|海棠湾酒店')], limit=1)
P_VEHICLE = env['res.partner'].search([('name', '=', '仿真|环岛车队')], limit=1)
P_MEAL = env['res.partner'].search([('name', '=', '仿真|椰香餐厅')], limit=1)
DEP = env['ta.departure'].browse(92519)
ORDER_O1 = env['ta.order'].browse(434855)

results = {}


def log(msg):
    print(msg)


def phase(title):
    print('\n' + '=' * 72)
    print('== ' + title)
    print('=' * 72)


def get_or_create_account(code, name, account_type):
    acc = env['account.account'].sudo().search([('code', '=', code)], limit=1)
    if not acc:
        acc = env['account.account'].sudo().create(
            {'code': code, 'name': name, 'account_type': account_type})
        log(f'  新建科目 {code} {name}')
    return acc


def set_param(key, value):
    ICP = env['ir.config_parameter'].sudo()
    rec = ICP.search([('key', '=', key)], limit=1)
    if rec:
        rec.value = str(value)
    else:
        ICP.create({'key': key, 'value': str(value)})


def ensure_user(name, login, group_xmlids, partner=None):
    u = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if u:
        return u
    groups = [env.ref(x).id for x in group_xmlids if env.ref(x, raise_if_not_found=False)]
    u = env['res.users'].sudo().with_context(**NO_MAIL_CTX).create({
        'name': name, 'login': login,
        'password': secrets.token_urlsafe(16),
        'group_ids': [(6, 0, groups)],
        'company_ids': [(6, 0, [env.company.id])],
        'company_id': env.company.id,
    })
    if partner:
        orphan = u.partner_id
        u.sudo().write({'partner_id': partner.id})
        if orphan and orphan.id != partner.id:
            orphan.sudo().unlink()
    log(f'  新建用户 {name} (login={login})')
    return u


# ---------------------------------------------------------------------------
phase('P0 角色与基础设施（幂等 get-or-create）')
accountant = env['res.users'].sudo().search([('login', '=', 'demo_accountant')], limit=1)
assert accountant, 'demo_accountant 不存在（先跑 seed_ta_demo.py）'
grp_ta_acc = env.ref('ta_base.group_ta_accountant')
grp_mgr = env.ref('account.group_account_manager', raise_if_not_found=False)
if grp_ta_acc not in accountant.group_ids:
    accountant.sudo().write({'group_ids': [(4, grp_ta_acc.id)]})
if grp_mgr and grp_mgr not in accountant.group_ids:
    accountant.sudo().write({'group_ids': [(4, grp_mgr.id)]})
cashier = ensure_user('仿真|出纳-王（系统用户）', 'sim_cashier',
                      ['base.group_user', 'ta_base.group_ta_cashier'],
                      partner=env['res.partner'].search(
                          [('name', '=', '仿真|出纳-王')], limit=1))
guide_user = ensure_user('仿真|导游-林海（系统用户）', 'sim_guide',
                         ['base.group_user', 'ta_base.group_ta_guide'],
                         partner=P_GUIDE)
log(f'  会计 demo_accountant uid={accountant.id}  出纳 uid={cashier.id}  导游用户 uid={guide_user.id}')

# 公司默认费用科目（计调账单 / 费用报销落账依赖）
company = env.company.sudo()
if not company.expense_account_id:
    acc_exp = get_or_create_account('6601', 'DEMO|费用（管理）', 'expense')
    company.expense_account_id = acc_exp.id
    log(f'  补设公司费用科目 → {acc_exp.code}')
# 仿真专用银行日记账：存量日记账的付款方式行全部缺 payment_account_id
# （全库 1086/1086 行为空），登记付款将生成"无凭证支付"→ 计调账单余额永不清零。
# 本仿真自建规范日记账走通闭环；存量日记账问题作为产品缺陷记入验收报告。
broken_method_lines = env['account.payment.method.line'].sudo().search_count(
    [('payment_account_id', '=', False)])
log(f'  [缺陷取证] 全库付款方式行缺 payment_account_id: {broken_method_lines} 行')
sim_bank = env['account.journal'].sudo().search([('code', '=', 'SIMBANK')], limit=1)
if not sim_bank:
    bank_acc = env['account.journal'].browse(6).default_account_id \
        or env['account.account'].sudo().search(
            [('account_type', '=', 'asset_cash')], limit=1)
    assert bank_acc and bank_acc.account_type == 'asset_cash', '缺少资产-现金类科目'
    sim_bank = env['account.journal'].sudo().create({
        'name': '仿真|银行存款', 'code': 'SIMBANK', 'type': 'bank',
        'company_id': env.company.id, 'default_account_id': bank_acc.id,
    })
    log(f'  新建仿真银行日记账 {sim_bank.id}（默认科目 {bank_acc.id}）')
methods = sim_bank.sudo().outbound_payment_method_line_ids \
    | sim_bank.sudo().inbound_payment_method_line_ids
for m in methods:
    if not m.payment_account_id:
        m.sudo().payment_account_id = sim_bank.default_account_id.id
        log(f'  付款方式「{m.name}」补设付款账户 → {sim_bank.default_account_id.id}')
assert sim_bank.default_account_id, '仿真银行日记账缺默认科目'
bank_journal = sim_bank
purchase_journal = env['account.journal'].search(
    [('type', '=', 'purchase'), ('company_id', '=', env.company.id)], order='id', limit=1)
general_journal = env['account.journal'].search(
    [('type', '=', 'general'), ('company_id', '=', env.company.id)], order='id', limit=1) \
    or env['account.journal'].search([('company_id', '=', env.company.id)], limit=1)
assert bank_journal and bank_journal.default_account_id, '银行日记账缺默认科目'
log(f'  日记账：银行={bank_journal.name}({bank_journal.id}) 采购={purchase_journal.name} '
    f'通用={general_journal.name}')
# 导游借款科目（1221 口径，action_pay 依赖 ICP）
if not env['ir.config_parameter'].sudo().get_int('ta_guide.loan_account_id', 0):
    acc_loan = get_or_create_account('1221', 'DEMO|其他应收款-导游借款', 'asset_receivable')
    set_param('ta_guide.loan_account_id', acc_loan.id)
    log(f'  补设导游借款科目 ICP → {acc_loan.code}')
# 供应商应付科目兜底（in_invoice 过账依赖）
for p in (P_SCENIC, P_HOTEL, P_VEHICLE, P_MEAL):
    if not p.sudo().property_account_payable_id and company.property_account_payable_id:
        p.sudo().property_account_payable_id = company.property_account_payable_id
        log(f'  补供应商应付科目 {p.name}')
assert P_CUSTOMER.sudo().property_account_receivable_id, '客户缺应收科目'

# ---------------------------------------------------------------------------
phase('P1 修正 O1 报名价别（2 行 800 应为儿童）')
child_lines = ORDER_O1.line_ids.filtered(lambda l: l.unit_price == 800.0)
if child_lines and child_lines[0].kind != 'child':
    with env.cr.savepoint():
        child_lines.sudo().write({'kind': 'child'})
    log(f'  O1 价别修正：{len(child_lines)} 行 → 儿童')
else:
    log('  O1 价别已正确（或无需修正），跳过')
env.flush_all()

# ---------------------------------------------------------------------------
phase('P2 O2 订单：2 大人 3200 全款（自动价）')
o2 = env['ta.order'].search([('departure_id', '=', DEP.id), ('note', '=', SIM + '|O2')], limit=1)
if not o2:
    o2 = env['ta.order'].with_context(**NO_MAIL_CTX).create({
        'departure_id': DEP.id, 'partner_id': P_CUSTOMER.id, 'note': SIM + '|O2',
        'line_ids': [(0, 0, {'name': '仿真客7', 'kind': 'adult'}),
                     (0, 0, {'name': '仿真客8', 'kind': 'adult'})],
    })
    o2.with_user(ADMIN).action_confirm()
    log(f'  O2 创建并确认 → {o2.name} 金额={o2.amount_total:.0f}')
else:
    log(f'  O2 已存在 {o2.name} state={o2.state}（跳过）')
results['O2'] = o2

# ---------------------------------------------------------------------------
phase('P3 O3 订单：3 大 1 小 5600 未付（账龄样本）')
o3 = env['ta.order'].search([('departure_id', '=', DEP.id), ('note', '=', SIM + '|O3')], limit=1)
if not o3:
    o3 = env['ta.order'].with_context(**NO_MAIL_CTX).create({
        'departure_id': DEP.id, 'partner_id': P_CUSTOMER.id, 'note': SIM + '|O3',
        'line_ids': [(0, 0, {'name': '仿真客9', 'kind': 'adult'}),
                     (0, 0, {'name': '仿真客10', 'kind': 'adult'}),
                     (0, 0, {'name': '仿真客11', 'kind': 'adult'}),
                     (0, 0, {'name': '仿真客12', 'kind': 'child'})],
    })
    o3.with_user(ADMIN).action_confirm()
    log(f'  O3 创建并确认 → {o3.name} 金额={o3.amount_total:.0f}（不收款）')
else:
    log(f'  O3 已存在 {o3.name} state={o3.state}（跳过）')
results['O3'] = o3

# ---------------------------------------------------------------------------
phase('P4 探针：9 人报名 → 预期超位拦截（已占 12/20）')
o4 = env['ta.order'].with_context(**NO_MAIL_CTX).create({
    'departure_id': DEP.id, 'partner_id': P_CUSTOMER.id, 'note': SIM + '|O4-探针',
    'line_ids': [(0, 0, {'name': f'探针客{i}', 'kind': 'adult'}) for i in range(1, 10)],
})
try:
    o4.with_user(ADMIN).action_confirm()
    log('  !! 探针未拦截：9 人确认成功（与预期不符，需人工核查）')
    results['O4_blocked'] = False
except UserError as e:
    log(f'  O4 探针超位拦截生效 → {e}')
    results['O4_blocked'] = True
o4.sudo().unlink()
env.flush_all()
log(f'  当前占位 seats_used={DEP.seats_used}/20（预期 12）')

# ---------------------------------------------------------------------------
phase('P5 计调 4 项 → 账单 → 过账 → 付款')
items_spec = [
    ('scenic', P_SCENIC, '仿真|门票', 10, 120.0, 1200.0),
    ('hotel', P_HOTEL, '仿真|住宿', 8, 220.0, 1760.0),
    ('vehicle', P_VEHICLE, '仿真|用车', 1, 1800.0, 1800.0),
    ('meal', P_MEAL, '仿真|团餐', 10, 60.0, 600.0),
]
items = env['ta.dispatch.item'].search([('departure_id', '=', DEP.id), ('note', '=', SIM)])
if items:
    log(f'  计调条目已存在 {len(items)} 条（跳过创建，直接复用）')
else:
    created = []
    for kind, sup, name, qty, price, _amt in items_spec:
        it = env['ta.dispatch.item'].with_context(**NO_MAIL_CTX).create({
            'departure_id': DEP.id, 'kind': kind, 'supplier_id': sup.id,
            'name': name, 'qty': qty, 'unit_price': price, 'note': SIM,
        })
        it.with_user(ADMIN).action_confirm()
        created.append(it)
    items = created
    log(f'  创建并确认 4 条计调条目（账单草稿已生成）')
for it in items:
    bill = it.move_id
    if bill.state == 'draft':
        bill.with_user(accountant).action_post()
        log(f'  账单过账 {bill.name} {bill.amount_total:.0f} ({it.kind})')
    else:
        log(f'  账单已过账 {bill.name}（跳过）')
# 付款：景区 1200 全 / 酒店 1760 全 / 车队 1000 部分 / 餐厅 0
pay_spec = {1200.0: 1200.0, 1760.0: 1760.0, 1800.0: 1000.0, 600.0: 0.0}


def pay_bill(bill, amt):
    if amt <= 0.01:
        return None
    if bill.payment_state == 'paid':
        return None
    ctx = {'active_model': 'account.move', 'active_ids': [bill.id]}
    wiz = env['account.payment.register'].with_context(**ctx).create({
        'journal_id': bank_journal.id,
        'amount': amt,
        'payment_date': fields.Date.context_today(bill),
        'payment_difference_handling':
            'open' if amt + 0.01 < bill.amount_residual else 'reconcile',
    })
    return wiz.action_create_payments()


for it in items:
    bill = it.move_id
    want = pay_spec[round(it.amount, 2)]
    paid = round(bill.amount_total - bill.amount_residual, 2)
    if want > paid + 0.01:
        with env.cr.savepoint():
            pay_bill(bill, want)
        log(f'  付款 {it.name}: {want:.0f}（账上已付 {paid:.0f} → '
            f'{round(bill.amount_total - bill.amount_residual, 2):.0f}）')
    else:
        log(f'  付款 {it.name}: 目标 {want:.0f} ≤ 已付 {paid:.0f}（跳过）')
env.flush_all()
results['items'] = items

# ---------------------------------------------------------------------------
phase('P6 收款闭环：出纳登记 → 销售认领 → 会计审核（AC-05 岗位分离）')
Bank = env['ta.bank.line']
bl1 = Bank.search([('ref', '=', '仿真|网银-0001')], limit=1)
bl2 = Bank.search([('ref', '=', '仿真|网银-0002')], limit=1)
if not bl1:
    bl1 = Bank.with_context(**NO_MAIL_CTX).with_user(cashier).create({
        'date': fields.Date.context_today(env.user), 'amount': 5000.0,
        'journal_id': bank_journal.id, 'partner_id': P_CUSTOMER.id,
        'partner_name': P_CUSTOMER.name, 'ref': '仿真|网银-0001',
        'note': SIM + ' O1 部分款',
    })
    log(f'  出纳登记到账 5000 → {bl1.id}（登记人={bl1.registered_by.name}）')
if not bl2:
    bl2 = Bank.with_context(**NO_MAIL_CTX).with_user(cashier).create({
        'date': fields.Date.context_today(env.user), 'amount': 3200.0,
        'journal_id': bank_journal.id, 'partner_id': P_CUSTOMER.id,
        'partner_name': P_CUSTOMER.name, 'ref': '仿真|网银-0002',
        'note': SIM + ' O2 全款',
    })
    log(f'  出纳登记到账 3200 → {bl2.id}（登记人={bl2.registered_by.name}）')
Claim = env['ta.payment.claim']
cl1 = Claim.search([('line_ids.bank_line_id', '=', bl1.id)], limit=1)
if not cl1:
    cl1 = Claim.with_context(**NO_MAIL_CTX).with_user(ADMIN).create({
        'line_ids': [(0, 0, {'bank_line_id': bl1.id, 'amount': 5000.0})],
        'alloc_ids': [(0, 0, {'order_id': ORDER_O1.id, 'amount_allocated': 5000.0})],
    })
    cl1.with_user(ADMIN).action_submit()
    log(f'  销售（admin）创建认领单 {cl1.name}：5000 → O1')
cl2 = Claim.search([('line_ids.bank_line_id', '=', bl2.id)], limit=1)
if not cl2:
    cl2 = Claim.with_context(**NO_MAIL_CTX).with_user(ADMIN).create({
        'line_ids': [(0, 0, {'bank_line_id': bl2.id, 'amount': 3200.0})],
        'alloc_ids': [(0, 0, {'order_id': o2.id, 'amount_allocated': 3200.0})],
    })
    cl2.with_user(ADMIN).action_submit()
    log(f'  销售（admin）创建认领单 {cl2.name}：3200 → O2')
# AC-05 探针：认领人（admin）自己审核 → 预期拦截
if cl2.state == 'submitted' and not cl2.move_id:
    try:
        cl2.with_user(ADMIN).action_approve()
        log('  !! AC-05 未拦截：认领人自审成功（与预期不符）')
        results['ac05_blocked'] = False
    except AccessError as e:
        log(f'  AC-05 岗位分离探针生效（认领人自审被拦截）→ {e}')
        results['ac05_blocked'] = True
# 会计审核两单
for cl in (cl1, cl2):
    if cl.state == 'submitted':
        cl.with_user(accountant).action_approve()
        log(f'  会计审核通过 {cl.name} → 凭证 {cl.move_id.name} 已过账 '
            f'（审核人={cl.approved_by.name}）')
env.flush_all()
log(f'  O1 已付={ORDER_O1.amount_paid:.0f}/8000  O2 已付={o2.amount_paid:.0f}/3200')
for p in ORDER_O1.plan_ids:
    log(f'  O1 期次「{p.name}」核销 {p.amount_paid:.0f}/{p.amount:.0f}')

# ---------------------------------------------------------------------------
phase('P7 导游借支 3000 → 审批 → 发放')
Loan = env['ta.guide.loan']
loan = Loan.search([('note', '=', SIM)], limit=1)
if not loan:
    loan = Loan.with_context(**NO_MAIL_CTX).create({
        'guide_id': P_GUIDE.id, 'departure_id': DEP.id,
        'date': fields.Date.context_today(env.user), 'amount': 3000.0,
        'due_date': '2026-11-01', 'journal_id': bank_journal.id, 'note': SIM,
    })
    loan.with_user(accountant).action_approve()
    loan.with_user(accountant).action_pay()
    log(f'  借款 {loan.name} 审批并发放 → 凭证 {loan.paid_move_id.name} 过账，'
        f'未结清={loan.outstanding:.0f}')
else:
    log(f'  借款已存在 {loan.name} state={loan.state}（跳过）')
results['loan'] = loan

# ---------------------------------------------------------------------------
phase('P8 导游报账 600 → 提交 → 会计审核')
Ge = env['ta.guide.expense']
gexp = Ge.search([('note', '=', SIM)], limit=1)
if not gexp:
    gexp = Ge.with_context(**NO_MAIL_CTX).with_user(guide_user).create({
        'guide_id': P_GUIDE.id, 'departure_id': DEP.id,
        'date': fields.Date.context_today(env.user),
        'line_ids': [(0, 0, {'name': '仿真|门票补差', 'amount': 300.0,
                             'invoice_ref': 'FP-0901'}),
                     (0, 0, {'name': '仿真|临时杂费', 'amount': 300.0})],
        'note': SIM,
    })
    gexp.with_user(guide_user).action_submit()
    gexp.with_user(accountant).action_approve()
    log(f'  报账 #{gexp.id} 提交（导游本人）→ 会计审核通过，'
        f'合计={gexp.amount_total:.0f}（审核人={gexp.approved_by.name}）')
else:
    log(f'  报账已存在 state={gexp.state}（跳过）')
results['gexp'] = gexp

# ---------------------------------------------------------------------------
phase('P9 导游佣金 1200 → 结算冲抵借款')
Com = env['ta.guide.commission']
com = Com.search([('note', '=', SIM)], limit=1)
if not com:
    com = Com.with_context(**NO_MAIL_CTX).create({
        'guide_id': P_GUIDE.id, 'departure_id': DEP.id,
        'date': fields.Date.context_today(env.user), 'allowance': 1200.0,
        'rule_note': '仿真规则：80元/天×5天+购物零返佣', 'note': SIM,
    })
    com.with_user(accountant).action_settle()
    log(f'  佣金 {com.name} 结算：税后净额 1200 全量冲抵借款，'
        f'借款未结清={loan.outstanding:.0f}')
else:
    log(f'  佣金已存在 state={com.state}（跳过）')
results['com'] = com

# ---------------------------------------------------------------------------
phase('P10 费用报销 400（出纳申请人 → 会计审核，凭证留草稿）')
Exp = env['ta.expense']
exp = Exp.search([('reason', '=', '仿真|门市采购宣传物料')], limit=1)
if not exp:
    exp = Exp.with_context(**NO_MAIL_CTX).with_user(cashier).create({
        'reason': '仿真|门市采购宣传物料', 'applicant_id': cashier.id,
        'expense_type': 'marketing', 'date': fields.Date.context_today(env.user),
        'amount': 400.0, 'departure_id': DEP.id, 'invoice_ref': 'FP-0902',
        'note': SIM,
    })
    exp.with_user(cashier).action_submit()
    exp.with_user(accountant).action_approve()
    log(f'  报销 {exp.name} 提交（出纳）→ 会计审核，凭证 {exp.move_id.name} '
        f'state={exp.move_id.state}（草稿待付款）')
else:
    log(f'  报销已存在 state={exp.state}（跳过）')
results['exp'] = exp

# ---------------------------------------------------------------------------
phase('P11 固定资产 8000/36 月/5% → 启用 → 2026-09 折旧')
Ast = env['ta.asset']
asset = Ast.search([('note', '=', SIM)], limit=1)
if not asset:
    asset = Ast.with_context(**NO_MAIL_CTX).create({
        'name': '仿真|对讲机×4', 'category': 'electronic',
        'acquisition_date': '2026-09-01', 'cost': 8000.0,
        'residual_rate': 5.0, 'depreciation_months': 36, 'note': SIM,
    })
    asset.with_user(accountant).action_validate()
    log(f'  资产 {asset.code} 启用，月折旧={asset.monthly_depreciation:.2f}')
deprec = env['ta.asset.depreciation'].search(
    [('asset_id', '=', asset.id), ('period', '=', '2026-09')], limit=1)
if not deprec:
    deprec = env['ta.asset.depreciation'].with_context(**NO_MAIL_CTX).create(
        {'asset_id': asset.id, 'period': '2026-09',
         'amount': asset.monthly_depreciation})
    deprec.with_user(accountant).action_create_move()
    log(f'  2026-09 折旧 {deprec.amount:.2f} → 凭证 {deprec.move_id.name} 过账，'
        f'累计折旧={asset.accumulated_depreciation:.2f}，净值={asset.book_value:.2f}')
else:
    log(f'  折旧记录已存在（跳过）')

env.flush_all()
env.cr.commit()
print('\n' + '=' * 72)
print('== 全部业务动作完成（已提交）')
print('=' * 72)
