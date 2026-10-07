# -*- coding: utf-8 -*-
"""
fix_payment_method_accounts.py —— 存量修复：account.payment.method.line 过渡科目回填
                                  + 孤儿行清理（odoo shell 脚本，批4-A）

背景（缺陷已定位，见 d-交付验收/验收报告-用户仿真测试.md §5.1）：
- 存量库 tour20 中 account.payment.method.line 共 1089 行，1086 行 payment_account_id
  全空（362 入账 + 724 出账；其中 864 行 journal_id 为空属孤儿行）。
- Odoo 20 付款的 outstanding_account_id 由 payment_method_line_id.payment_account_id
  计算；为空 → account.payment._generate_journal_entry 的 need_move 过滤把付款排除 →
  登记付款生成"已付款"但不落凭证，供应商账单余额永远不清偿。
- 模块级防御（modules/ta_finance/models/ta_payment_method_account.py）只拦新数据，
  存量行由本脚本一次性修复。

== 运行方式（协调人执行）==
    # 1) 先备份（必须，由协调人执行）：cd c-系统实现/odootour && make backup
    # 2) 拷入容器并以 odoo shell 运行（先保持 DRY_RUN=True 干跑核对）：
    sudo docker cp c-系统实现/odootour/scripts/fix_payment_method_accounts.py odootour-odoo:/tmp/
    sudo docker exec -i -e PGPASSWORD=<新库口令> odootour-odoo \
      python3 /usr/lib/odoo/odoo-server/odoo-bin shell -d tour20 --no-http \
      --db_host=db --db_user=odoo < /tmp/fix_payment_method_accounts.py
    # 3) 干跑核对报告后：改 DRY_RUN=False，重跑前 export TMS_MIG_BACKUP_ACK=1：
    sudo docker exec -i -e PGPASSWORD=<新库口令> -e TMS_MIG_BACKUP_ACK=1 odootour-odoo \
      python3 /usr/lib/odoo/odoo-server/odoo-bin shell -d tour20 --no-http \
      --db_host=db --db_user=odoo < /tmp/fix_payment_method_accounts.py

== 修复口径 ==
- 回填：payment_account_id 为空 且 journal_id 非空 且 journal.default_account_id
  非空 → 回填 journal.default_account_id（实测 222 行 / 74 个 journal 全覆盖）。
- 孤儿清理：journal_id IS NULL 且未被 account_payment.payment_method_line_id 引用
  的行 → DELETE（实测 864 行、引用 0 行）。被付款引用的孤儿行只报告不删，
  防 Odoo m2o 默认 ondelete=set null 把历史付款的方式行置空。
- 幂等：只改"空→有值"和"孤儿→删"的差集，重跑 0 变更（结尾校验剩余空值应=0）。

== 口令约定 ==
口令只经环境变量注入（PGPASSWORD 供 libpq），严禁写进本文件/镜像/日志。
"""
import os

# ---------------------------------------------------------------------------
# 开关
# ---------------------------------------------------------------------------
DRY_RUN = True   # ← 协调人核对 dry-run 报告后改为 False 正式执行


# ---------------------------------------------------------------------------
# 工具（env 由 odoo shell 注入；范式同 migrate_tms19_to_ta.py）
# ---------------------------------------------------------------------------
def fetch(sql, args=None):
    env.cr.execute(sql, args)
    return env.cr.fetchall()


def scalar(sql, args=None):
    env.cr.execute(sql, args)
    row = env.cr.fetchone()
    return row[0] if row else None


def zh(name):
    """Odoo 20 翻译字段存 jsonb：取 zh_CN 显示名。"""
    if not name:
        return '(空)'
    if isinstance(name, dict):
        return name.get('zh_CN') or name.get('en_US') or str(name)
    return str(name)


# ---------------------------------------------------------------------------
# phase0 备份检查
# ---------------------------------------------------------------------------
def phase0_backup_check():
    print('== phase0 备份检查 ==')
    print('  正式执行前要求（协调人操作）：cd c-系统实现/odootour && make backup')
    print('  （pg_dump + filestore 存档到 $(ODOOTOUR_HOME)/backup）')
    if DRY_RUN:
        print('  [DRY-RUN] 只读预演，不校验 TMS_MIG_BACKUP_ACK')
        return
    if os.environ.get('TMS_MIG_BACKUP_ACK') != '1':
        raise RuntimeError(
            '未确认备份：请先执行 make backup 完成 pg_dump+filestore 备份，'
            '再 export TMS_MIG_BACKUP_ACK=1 重跑')
    print('  备份确认通过（TMS_MIG_BACKUP_ACK=1）')


# ---------------------------------------------------------------------------
# phase1 盘点（只读）
# ---------------------------------------------------------------------------
def phase1_inventory():
    print('== phase1 盘点（只读） ==')
    total, no_acct, orphan = fetch("""
        SELECT count(*),
               count(*) FILTER (WHERE payment_account_id IS NULL),
               count(*) FILTER (WHERE journal_id IS NULL)
        FROM account_payment_method_line""")[0]
    print('  method line 总数=%d  缺过渡科目=%d  孤儿行(journal空)=%d' % (
        total, no_acct, orphan))
    for ptype, n in fetch("""
            SELECT pm.payment_type, count(*)
            FROM account_payment_method_line l
            JOIN account_payment_method pm ON pm.id = l.payment_method_id
            GROUP BY pm.payment_type"""):
        print('    %s = %d' % (ptype or '(空)', n))
    refd_orphans = fetch("""
        SELECT l.id, pm.name
        FROM account_payment_method_line l
        JOIN account_payment_method pm ON pm.id = l.payment_method_id
        JOIN account_payment p ON p.payment_method_line_id = l.id
        WHERE l.journal_id IS NULL
        ORDER BY l.id""")
    print('  孤儿行中被 account.payment 引用的 = %d 行（只报告不删）' % len(refd_orphans))
    no_default = fetch("""
        SELECT j.id, j.code, j.name, count(*)
        FROM account_payment_method_line l
        JOIN account_journal j ON j.id = l.journal_id
        WHERE l.payment_account_id IS NULL
          AND j.default_account_id IS NULL
        GROUP BY j.id, j.code, j.name
        ORDER BY j.id""")
    print('  非孤儿缺科目行中 journal 无 default_account_id 的 = %d 行（只报告不回填）'
          % sum(r[3] for r in no_default))
    for jid, code, name, n in no_default:
        print('    !! journal#%s [%s] %s 无默认科目，%d 行无法回填' % (
            jid, code, zh(name), n))
    return total, no_acct, orphan, refd_orphans


# ---------------------------------------------------------------------------
# phase2 逐 journal 回填过渡科目
# ---------------------------------------------------------------------------
def phase2_backfill():
    print('== phase2 逐 journal 回填（payment_account_id ← journal.default_account_id） ==')
    rows = fetch("""
        SELECT j.id, j.code, j.name, j.default_account_id, count(*) AS n
        FROM account_payment_method_line l
        JOIN account_journal j ON j.id = l.journal_id
        WHERE l.payment_account_id IS NULL
          AND j.default_account_id IS NOT NULL
        GROUP BY j.id, j.code, j.name, j.default_account_id
        ORDER BY j.id""")
    total = sum(r[4] for r in rows)
    print('  待回填：%d 行 / %d 个 journal' % (total, len(rows)))
    for jid, code, name, defid, n in rows:
        print('    journal#%s [%s] %s → default_account_id#%s : %d 行' % (
            jid, code, zh(name), defid, n))
    if DRY_RUN:
        print('  [DRY-RUN] 跳过回填 UPDATE')
        return total
    for jid, code, name, defid, n in rows:
        env.cr.execute(
            "UPDATE account_payment_method_line "
            "   SET payment_account_id = %s, write_date = now() "
            " WHERE journal_id = %s AND payment_account_id IS NULL",
            (defid, jid))
        env.cr.commit()
    env.invalidate_all()
    print('  回填完成：%d 行' % total)
    return total


# ---------------------------------------------------------------------------
# phase3 孤儿行清理
# ---------------------------------------------------------------------------
def phase3_cleanup_orphans(refd_orphans):
    print('== phase3 孤儿行清理（journal_id IS NULL） ==')
    groups = fetch("""
        SELECT pm.name, pm.payment_type, count(*)
        FROM account_payment_method_line l
        JOIN account_payment_method pm ON pm.id = l.payment_method_id
        WHERE l.journal_id IS NULL
        GROUP BY pm.name, pm.payment_type
        ORDER BY count(*) DESC""")
    total = sum(r[2] for r in groups)
    # 孤儿行无 journal，「逐 journal」无从谈起 → 按付款方式列清
    print('  孤儿行合计 %d：%s' % (total, '；'.join(
        '%s(%s)×%d' % (zh(r[0]), r[1] or '方向空', r[2]) for r in groups)))
    if refd_orphans:
        print('  被付款引用 %d 行：%s（只报告不删）' % (
            len(refd_orphans), '；'.join(zh(r[1]) for r in refd_orphans)))
    if DRY_RUN:
        print('  [DRY-RUN] 跳过 DELETE')
        return total
    if refd_orphans:
        keep = [r[0] for r in refd_orphans]
        env.cr.execute(
            "DELETE FROM account_payment_method_line "
            "WHERE journal_id IS NULL AND id <> ALL(%s)", (keep,))
    else:
        env.cr.execute(
            "DELETE FROM account_payment_method_line WHERE journal_id IS NULL")
    deleted = env.cr.rowcount
    env.cr.commit()
    env.invalidate_all()
    print('  孤儿清理完成：删除 %d 行（保留被引用 %d 行）' % (deleted, len(refd_orphans)))
    return total


# ---------------------------------------------------------------------------
# phase4 结尾校验（幂等判据）
# ---------------------------------------------------------------------------
def phase4_verify():
    print('== phase4 校验 ==')
    remaining = scalar(
        "SELECT count(*) FROM account_payment_method_line "
        "WHERE payment_account_id IS NULL") or 0
    orphan_left = scalar(
        "SELECT count(*) FROM account_payment_method_line "
        "WHERE journal_id IS NULL") or 0
    print('  剩余空 payment_account_id 行数 = %d（修复后应为 0）' % remaining)
    print('  剩余孤儿行数 = %d（应为 0）' % orphan_left)
    print('  逐 journal 修复后方式行数（payment_account_id 非空）：')
    by_journal = fetch("""
        SELECT j.code, j.name, count(*)
        FROM account_payment_method_line l
        JOIN account_journal j ON j.id = l.journal_id
        WHERE l.payment_account_id IS NOT NULL
        GROUP BY j.code, j.name
        ORDER BY j.code""")
    for code, name, n in by_journal:
        print('    [%s] %s : %d 行' % (code, zh(name), n))
    return remaining, orphan_left


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print('MODE = %s' % ('DRY-RUN（只读预演，不落任何写）' if DRY_RUN else '正式修复'))
    phase0_backup_check()
    total, no_acct, orphan, refd_orphans = phase1_inventory()
    fixed = phase2_backfill()
    cleaned = phase3_cleanup_orphans(refd_orphans)
    remaining, orphan_left = phase4_verify()
    print('== 完成（%s）==' % ('dry-run 全程未写入' if DRY_RUN else '正式修复'))
    print('  预期变更：回填 %d 行、清理孤儿 %d 行；校验剩余空值 %d、孤儿 %d'
          % (fixed, cleaned, remaining, orphan_left))


# odoo shell 以 __name__=='__main__' 命名空间 exec 本文件（范式同 migrate_tms19_to_ta.py）
if __name__ == '__main__':
    main()
