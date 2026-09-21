# -*- coding: utf-8 -*-
"""A1 平桥金样例核对（在 odoo shell 内运行，只输出聚合值/哈希，不输出业务数据）。

用法（两侧各跑一次，输出可直接 diff）：
    RUN_WRITE=0 docker exec -i tms-odoo   odoo shell -c /etc/odoo/odoo.conf -d tms   --no-http < scripts/migration/a1_golden_paths.py
    RUN_WRITE=1 docker exec -i tour-odoo  odoo shell -c /etc/odoo/odoo.conf -d tour19 --no-http < scripts/migration/a1_golden_paths.py

四条链路：
  G1 财务报表出数（总账，逐账户借贷/余额 + 行数摘要）
  G2 财务过账 + 核销写入链路（RUN_WRITE=1 才跑；跑完 rollback，不留痕）
  G3 导游门户数据链路（订单/排团/结算的关键计算字段可读且非空比例一致）
  G4 附件可读（filestore 抽样 sha1 自校验）
  G5 用户与权限（密码哈希方案、活跃用户数、组数）
输出前缀 `G*_` 的键便于两侧 diff。
"""
import hashlib
import os

from odoo import fields
from odoo.tools import config as _config


def q(sql, params=None):
    """execute + fetchall（cr.select 在 19/20 之间存在性不稳定，统一走这一条）。

    params 必须保持 None 而不是 ()：psycopg2 在 params 为空元组时仍会做 % 插值，
    于是 SQL 字面量里的 `like '$%'` 会抛 IndexError。
    """
    env.cr.execute(sql, params)  # noqa: F821
    return env.cr.fetchall()  # noqa: F821

RUN_WRITE = os.environ.get('RUN_WRITE', '0') == '1'
DB = os.environ.get('DB_NAME') or _config['db_name']
# G1 范围：单月 + 三个有量的凭证（INV/BILL/BNK1 覆盖该月 15,055 行中的 15,051 行）。
# 全账户 × 8 个月的 GL 会跑过 10 分钟（本脚本首版即因此超时），金样例不需要那个量级。
DATE_FROM, DATE_TO = '2026-08-01', '2026-08-31'
GL_JOURNAL_CODES = ['BILL', 'BNK1', 'INV']
GL_STATEMENT_TIMEOUT = '240s'
out = []


def emit(k, v):
    out.append('%s\t%s' % (k, v))


# ---------- G1 总账出数（限定科目 + 限定凭证 + 单月） ----------
# 走 UI 同款路径：向导 _xlsx_base_data() 生成的 data 与 check_report() 逐字段相同，
# 再喂给 report 模型（active_model='account.account' 时 report 只遍历该子集），
# 从而覆盖 过滤条件 -> SQL -> 分组 -> 合计 -> 逐行余额 整条链路。
company = env['res.company'].sudo().search([], limit=1)  # noqa: F821
# 向导记录是 transient 表，但在生产上跑 G1 也会留一行，影响"0 差异"判据 -> 用 savepoint 包住
env.cr.execute('SAVEPOINT g1')  # noqa: F821
env.cr.execute("SET LOCAL statement_timeout = %s", (GL_STATEMENT_TIMEOUT,))  # noqa: F821
jid_rows = q("select id from account_journal where code in %s order by code",
             (tuple(GL_JOURNAL_CODES),))
journal_ids = [r[0] for r in jid_rows]
acc_rows0 = q(
    "select distinct l.account_id from account_move_line l "
    "where l.date between %s and %s and l.journal_id in %s order by 1",
    (DATE_FROM, DATE_TO, tuple(journal_ids)))
account_ids = [r[0] for r in acc_rows0]
emit('G1.scope_journals', ','.join(str(i) for i in journal_ids))
emit('G1.scope_accounts', ','.join(str(i) for i in account_ids))
wiz = env['account.report.general.ledger'].create({  # noqa: F821
    'date_from': DATE_FROM, 'date_to': DATE_TO, 'target_move': 'all',
    'display_account': 'all', 'initial_balance': True,
    'sortby': 'sort_date', 'company_id': company.id,
    'journal_ids': [(6, 0, journal_ids)],
})
data = wiz._xlsx_base_data()
# GL 的 report 还要读 display_account/sortby/initial_balance（check_report 的 read 列表里
# 按各 report 的字段不同），这里补齐成与 UI 提交完全相同的 form
data['form'].update({'display_account': wiz.display_account,
                     'sortby': wiz.sortby,
                     'initial_balance': wiz.initial_balance})
rep = env['report.tour_accounting.report_general_ledger'].with_context(  # noqa: F821
    active_model='account.account', active_ids=account_ids)
vals = rep._get_report_values(account_ids, data)
acc_rows, line_rows = [], []
for a in vals['Accounts']:
    acc_rows.append('%s|%s|%s|%d' % (
        a.get('code'), round(a.get('debit') or 0, 2), round(a.get('credit') or 0, 2),
        len(a.get('move_lines') or [])))
    for ln in (a.get('move_lines') or []):
        line_rows.append('%s|%s|%s|%s|%s|%s|%s' % (
            ln.get('ldate'), ln.get('lcode'), ln.get('move_name'),
            round(ln.get('debit') or 0, 2), round(ln.get('credit') or 0, 2),
            round(ln.get('balance') or 0, 2), ln.get('fname')))
acc_rows.sort()
line_rows.sort()
emit('G1.accounts', len(acc_rows))
emit('G1.digest', hashlib.sha256('\n'.join(acc_rows).encode()).hexdigest()[:16])
emit('G1.total_debit', round(sum(float(x.split('|')[1]) for x in acc_rows), 2))
emit('G1.total_credit', round(sum(float(x.split('|')[2]) for x in acc_rows), 2))
emit('G1.lines', len(line_rows))
emit('G1.lines_digest', hashlib.sha256('\n'.join(line_rows).encode()).hexdigest()[:16])
env.cr.execute('ROLLBACK TO SAVEPOINT g1')  # noqa: F821

# ---------- G2 过账 + 核销（写入后回滚） ----------
if RUN_WRITE:
    try:
        # 选一个没有银行账号的客户：Odoo 19 的 posting 守卫会对"未信任的公司银行账号"
        # 抛 RedirectWarning，且该异常消息会把（加密的）银行账号打进日志。
        partner = env['res.partner'].sudo().search(  # noqa: F821
            [('parent_id', '=', False), ('bank_ids', '=', False)], limit=1)
        if not partner:
            partner = env['res.partner'].sudo().search(  # noqa: F821
                [('parent_id', '=', False)], limit=1)
        move = env['account.move'].with_user(env.ref('base.user_admin')).create({  # noqa: F821
            'move_type': 'out_invoice', 'partner_id': partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'A1 冒烟：过账与核销链路',
                'quantity': 1, 'price_unit': 123.45,
            })],
        })
        move.partner_bank_id = False  # 同上，避免触发银行账号信任守卫
        move.action_post()
        jn = env['account.journal'].search(  # noqa: F821
            [('type', 'in', ('bank', 'cash')), ('company_id', '=', company.id)],
            order='code', limit=1)
        # 19 起 account.payment 没有 move_date / destination_journal_id，
        # 凭证方式取自 journal.inbound_payment_method_line_ids（不再是 inbound_payment_method_ids）
        pm_line = jn.inbound_payment_method_line_ids.filtered(
            lambda l: l.payment_method_id.code == 'manual')[:1] \
            or jn.inbound_payment_method_line_ids[:1]
        pay = env['account.payment'].create({  # noqa: F821
            'payment_type': 'inbound', 'partner_type': 'customer',
            'partner_id': partner.id, 'amount': 123.45, 'journal_id': jn.id,
            'payment_method_id': pm_line.payment_method_id.id,
            'date': fields.Date.context_today(env['account.payment']),  # noqa: F821
        })
        pay.action_post()

        def _is_recv(line):
            at = getattr(line.account_id, 'account_type', None) or line.account_id.internal_type
            return at in ('asset_receivable', 'receivable')

        rec_lines = move.line_ids.filtered(_is_recv) | pay.move_id.line_ids.filtered(_is_recv)
        # 19 中过账收款可能已自动核销；只对尚未核销的行显式核销
        emit('G2.auto_reconciled', bool(rec_lines.mapped('full_reconcile_id')))
        pending = rec_lines.filtered(lambda l: not l.full_reconcile_id)
        if pending:
            pending.reconcile()
        moved = move.line_ids.filtered(lambda l: l.reconciled)
        ok_state = move.state == 'posted' and pay.move_id.state == 'posted'
        ok_recon = bool(moved) and all(l.full_reconcile_id for l in moved)
        ok_match = all(l.matching_number == str(l.full_reconcile_id.id)
                       for l in moved if l.full_reconcile_id)
        bal = round(sum(l.balance for l in move.line_ids), 2)
        emit('G2.posted', ok_state)
        emit('G2.journal', jn.code)
        emit('G2.reconciled_lines', len(moved))
        emit('G2.invariant_full_reconcile', ok_recon)
        emit('G2.invariant_matching_number', ok_match)
        emit('G2.move_balance_zero', bal == 0.0)
        emit('G2.amount_total', round(move.amount_total, 2))
    except Exception as exc:  # 只报异常类型，异常消息可能含业务数据
        emit('G2.error', type(exc).__name__)
    finally:
        env.cr.rollback()  # noqa: F821
        emit('G2.rolled_back', True)
else:
    emit('G2.skipped', 'RUN_WRITE=0')

# ---------- G3 导游门户数据链路 ----------
# 现网没有 tour.order 这个模型；门户链路实际读的是排团/报名/导游三张表。
for model, label in (('tour.plan', 'G3.plan'), ('tour.plan.reg', 'G3.plan_reg'),
                     ('tour.guide', 'G3.guide')):
    if env['ir.model'].sudo().search_count([('model', '=', model)]):  # noqa: F821
        recs = env[model].sudo().search([], limit=50)  # noqa: F821
        fl = [f for f in env[model]._fields  # noqa: F821
              if env[model]._fields[f].compute and not env[model]._fields[f].related]  # noqa: F821
        vals3 = recs.read(fl[:8]) if recs else []
        nonempty = sum(1 for v in vals3 for f in (fl[:8] if fl else []) if v.get(f))
        emit(label + '.n', env[model].sudo().search_count([]))  # noqa: F821
        emit(label + '.computed_fields', len(fl))
        emit(label + '.nonempty_reads', nonempty)

# ---------- G4 附件可读 ----------
rows = q("(select store_fname, id from ir_attachment where store_fname is not null "
         "and store_fname <> '' order by id limit 25) "
         "union all "
         "(select store_fname, id from ir_attachment where store_fname is not null "
         "and store_fname <> '' order by id desc limit 25) "
         "order by id")
hits = mismatch = missing = 0
for fname, _aid in rows:
    # store_fname 本身形如 `44/44d16...`（已含 2 级目录前缀）；不要用 fname[:2] 拼接，
    # os.path.join 遇到以 '/' 开头的片段会丢弃前面的路径。
    rel = fname if '/' in fname else '%s/%s' % (fname[:2], fname[2:])
    p = os.path.join('/var/lib/odoo/filestore', DB, rel)
    if not os.path.isfile(p):
        # 生产 filestore 本身缺 415 个文件（A0 报告 K2），两侧同源，缺失不判失败
        missing += 1
        continue
    body = open(p, 'rb').read()
    if hashlib.sha1(body).hexdigest() == os.path.basename(fname).split('.')[0][:40]:
        hits += 1
    else:
        mismatch += 1
emit('G4.sample', len(rows))
emit('G4.sha1_match', hits)
emit('G4.sha1_mismatch', mismatch)
emit('G4.missing', missing)

# ---------- G5 用户与权限 ----------
# 19 起 passlib 的 CryptContext 变成 res.users 上的方法（模块级符号已移除），
# 这里只解析 MCF 前缀（方案名 + rounds），不 import 私有符号。
U = env['res.users'].sudo()  # noqa: F821
users = U.search_count([('active', '=', True)])
schemes = set()
for uid, pw in q("select id, password from res_users "
                 "where password is not null and password <> '' order by id limit 200"):
    parts = pw.split('$')
    if pw.startswith('$') and len(parts) >= 3:
        schemes.add('%s:rounds=%s' % (parts[1], parts[2]))
    else:
        schemes.add('UNHASHED')
emit('G5.active_users', users)
emit('G5.pwd_schemes', ';'.join(sorted(schemes)))
emit('G5.pwd_hashed', q("select count(*) from res_users "
                        "where password is not null and password like '$%'")[0][0])
emit('G5.groups', env['res.groups'].sudo().search_count([]))  # noqa: F821
emit('G5.installed_modules', env['ir.module.module'].sudo().search_count(  # noqa: F821
    [('state', '=', 'installed')]))

print('\n'.join(out))
print('A1_SMOKE_DONE', DB)
