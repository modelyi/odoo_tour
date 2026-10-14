# -*- coding: utf-8 -*-
"""批6 P0-5 期初三表验证（只读）：BS-16 §6.2 六项检查 + BS-14 补记基线。

运行（odoo shell stdin，全程无写操作、无提交）：
    cd c-系统实现/odootour && source .env
    docker compose run --rm odoo python3 /usr/lib/odoo/odoo-server/odoo-bin \
        -c /etc/odoo/odoo.conf --db_host=db --db_user=odoo \
        --db_password=$POSTGRES_PASSWORD -d tour20 shell --no-http \
        < scripts/verify_opening_bs16.py

用途：P0-6 收入成本补记前/后各跑一次，两次输出对照写入批6 验收报告
（补记前基线 / 补记后复验）。

硬断言（FAIL 即退出码 1）：
  C1 期初凭证 ref='期初建账' 唯一、posted、journal=OPEN、借贷平衡
  C2 全库 posted 借贷差 = 0.00
  C3 资产 = 负债 + 权益（按 account_type 分组恒等）
  C4 期初凭证无损益行（income/expense 类科目）
  C5 银行 1002 余额 = 9,228,332.70（BS-16 §6.2 期望）

参考对照（不硬断言，仅输出差异供报告）：
  权益 vs BS-16 初版 52,718,463.79（迁移已按轧平口径落 4104，以 C3 恒等为准）
  P0-6 补记目标（BS-14 R 表）：6001.01=235,972,275 贷 / 6001.03=1,210,748 贷 /
      2221 销项税=14,158,338 贷 / 6401=255,423,213 借
"""
import os
import sys

FAILS = []


def check(tag, ok, detail):
    print(f"  [{'PASS' if ok else 'FAIL'}] {tag}: {detail}")
    if not ok:
        FAILS.append(tag)


def q(sql, params=None):
    env.cr.execute(sql, params or ())
    return env.cr.fetchall()


def bal_exact(code):
    """posted 下指定科目编码（code_store 公司键）借贷差 dr-cr。"""
    rows = q("""
        SELECT ROUND(SUM(l.debit-l.credit), 2)
        FROM account_move_line l
        JOIN account_move m ON m.id = l.move_id
        JOIN account_account a ON a.id = l.account_id
        WHERE m.state='posted' AND a.code_store->>%s = %s
    """, (str(cid), code))
    return rows[0][0] or 0.0


def bal_prefix(prefix):
    """posted 下编码前缀分组余额（dr-cr）。"""
    return q("""
        SELECT a.code_store->>%s AS code, a.account_type,
               ROUND(SUM(l.debit-l.credit), 2)
        FROM account_move_line l
        JOIN account_move m ON m.id = l.move_id
        JOIN account_account a ON a.id = l.account_id
        WHERE m.state='posted' AND a.code_store->>%s LIKE %s
        GROUP BY 1, 2 ORDER BY 1
    """, (str(cid), str(cid), prefix + '%'))


print('=' * 72)
print('== 批6 P0-5 期初三表验证（只读） — ' +
      os.environ.get('P05_BASELINE', '补记前基线'))
print('=' * 72)
cid = env.company.id
print(f"公司: {env.company.name} (id={cid})；数据库: {env.cr.dbname}")
print()

# ---- C1 期初凭证唯一性 / journal / 平衡 ----
print('[C1] 期初建账凭证')
rows = q("""
    SELECT m.id, m.name, m.ref, m.state, j.code,
           ROUND(SUM(l.debit), 2), ROUND(SUM(l.credit), 2)
    FROM account_move m
    JOIN account_journal j ON j.id = m.journal_id
    JOIN account_move_line l ON l.move_id = m.id
    WHERE m.ref LIKE '%%期初%%'
    GROUP BY m.id, m.name, m.ref, m.state, j.code
""")
check('C1-唯一', len(rows) == 1, f"期初凭证 {len(rows)} 张" + (
    f"（id={rows[0][0]} {rows[0][1]} ref={rows[0][2]}）" if rows else ""))
if rows:
    _, name, ref, state, jcode, dr, cr = rows[0]
    check('C1-posted', state == 'posted', f"state={state}（{name}）")
    check('C1-journal', jcode == 'OPEN', f"journal={jcode}")
    check('C1-平衡', abs((dr or 0) - (cr or 0)) < 0.005,
          f"借={dr} 贷={cr} 差={round((dr or 0) - (cr or 0), 2)}")
    for rid, rname, rref, rstate, rcode, rdr, rcr in rows:
        print(f"    {rname} | ref={rref} state={rstate} journal={rcode} "
              f"借={rdr} 贷={rcr}")

# ---- C2 全库 posted 借贷差 ----
print('\n[C2] 全库 posted 借贷差')
dr, cr, diff, moves = q("""
    SELECT ROUND(SUM(l.debit), 2), ROUND(SUM(l.credit), 2),
           ROUND(SUM(l.debit-l.credit), 2), COUNT(DISTINCT m.id)
    FROM account_move_line l
    JOIN account_move m ON m.id = l.move_id
    WHERE m.state='posted'
""")[0]
check('C2', abs(diff) < 0.005, f"借={dr} 贷={cr} 差={diff}（{moves} 张 posted 凭证）")

# ---- C4 期初凭证无损益行 ----
print('\n[C4] 期初凭证无损益行')
cnt = q("""
    SELECT COUNT(*) FROM account_move_line l
    JOIN account_move m ON m.id = l.move_id
    JOIN account_account a ON a.id = l.account_id
    WHERE m.ref LIKE '%%期初%%'
      AND a.account_type IN ('income', 'income_other',
                             'expense', 'expense_direct_cost',
                             'expense_depreciation')
""")[0][0]
check('C4', cnt == 0, f"期初凭证损益行数 = {cnt}（期望 0）")

# ---- C5 银行 1002 ----
print('\n[C5] 银行 1002 余额')
bank = bal_exact('1002')
check('C5', abs(bank - 9228332.70) < 0.005,
      f"1002={bank:,.2f}（BS-16 期望 +9,228,332.70）")

# ---- C3 资产 = 负债 + 权益（account_type 分组恒等） ----
print('\n[C3] 资产 = 负债 + 权益（恒等）')
groups = q("""
    SELECT CASE
             WHEN a.account_type LIKE 'asset%%' THEN 'asset'
             WHEN a.account_type LIKE 'liability%%' THEN 'liability'
             WHEN a.account_type LIKE 'equity%%' THEN 'equity'
             WHEN a.account_type LIKE 'income%%' THEN 'income'
             WHEN a.account_type LIKE 'expense%%' THEN 'expense'
           END AS grp,
           ROUND(SUM(l.debit-l.credit), 2)
    FROM account_move_line l
    JOIN account_move m ON m.id = l.move_id
    JOIN account_account a ON a.id = l.account_id
    WHERE m.state='posted'
      AND (a.account_type LIKE 'asset%%' OR a.account_type LIKE 'liability%%'
           OR a.account_type LIKE 'equity%%' OR a.account_type LIKE 'income%%'
           OR a.account_type LIKE 'expense%%')
    GROUP BY 1
""")
g = {row[0]: (row[1] or 0.0) for row in groups}
assets = g.get('asset', 0.0)                # dr-cr（含累计折旧贷方抵减）
liab_cr = -g.get('liability', 0.0)          # 负债按贷方为正
equity_cr = -(g.get('equity', 0.0) + g.get('income', 0.0) + g.get('expense', 0.0))
diff3 = round(assets - liab_cr - equity_cr, 2)
print(f"    资产={assets:,.2f}  负债={liab_cr:,.2f}  权益(含本年损益)={equity_cr:,.2f}")
print(f"    资产-负债-权益 = {diff3:,.2f}")
check('C3', abs(diff3) < 0.005, f"恒等差 = {diff3}")

# ---- 三表试算输出 ----
print('\n== 三表试算（posted） ==')
print('\n[资产负债表] 科目编码余额（dr-cr；负=贷方余额）')
bs_codes = ['1002', '1012', '1122', '1123', '1221', '1222',
            '2202', '2203', '2211', '2221', '2241', '4001', '4104']
for code in bs_codes:
    rows = bal_prefix(code)
    if not rows:
        print(f"    {code:<8} —")
        continue
    for c, atype, b in rows:
        print(f"    {c:<8} {atype:<20} {b:>16,.2f}")
print(f"    {'合计':<8} {'资产':<20} {assets:>16,.2f}")
print(f"    {'合计':<8} {'负债':<20} {liab_cr:>16,.2f}")
print(f"    {'合计':<8} {'权益(含本年损益)':<14} {equity_cr:>16,.2f}")

print('\n[利润表] 收入/成本科目余额（dr-cr；负=贷方发生）')
pl_codes = ['6001', '6051', '6401', '6407']
for code in pl_codes:
    rows = bal_prefix(code)
    if not rows:
        print(f"    {code:<8} —")
        continue
    for c, atype, b in rows:
        print(f"    {c:<8} {atype:<20} {b:>16,.2f}")

print('\n== 参考对照（仅输出差异，不硬断言） ==')
eq_bs16 = 52718463.79
print(f"[权益] BS-16 初版参考 = {eq_bs16:,.2f}；当前(含本年损益) = {equity_cr:,.2f}；"
      f"差异 = {equity_cr - eq_bs16:,.2f}")
print(f"        （迁移迭代6 已按轧平口径落 4104={-g.get('equity', 0.0):,.2f}，"
      f"恒等以 C3 为准；差异含迁移口径尾差与批3-5 仿真损益）")
targets = [
    ('6001.01', 235972275.0, '贷', '组团收入净额（BS-14 R2）'),
    ('6001.03', 1210748.0, '贷', '代订差价（BS-14，含税）'),
    ('2221', 14158338.0, '贷', '销项税（BS-14 R3，前缀组）'),
    ('6401', 255423213.0, '借', '主营成本（BS-14 全额）'),
]
print('[P0-6 补记目标] 当前余额 vs BS-14 目标（补记前应近 0，补记后接近目标）')
for code, target, side, desc in targets:
    if code == '2221':
        cur = sum(b for _, _, b in bal_prefix(code)) or 0.0
    else:
        cur = bal_exact(code)
    print(f"    {code:<8} 当前={cur:>16,.2f}  目标={target:>16,.2f}（{side}） {desc}")

print('\n== RESULT ==')
if FAILS:
    print(f"FAIL: {', '.join(FAILS)}")
    sys.exit(1)
print('PASS: 期初三表验证全部通过（硬断言 C1-C5）')
