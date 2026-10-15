# -*- coding: utf-8 -*-
"""批6 P0-6 纠偏：已过账 41 代订供应商账单行科目 6401 → 2241.01 代收代付（幂等）。

背景：批6 起 41 代订模式的供应商成本经 2241.01 代收代付转出（不进损益），
历史已过账账单仍记在 6401 主营业务成本上，需红冲重记。

处理（仅针对 departure.biz_mode=41 且账单已过账、行科目为 6401 的条目）：
  1. _reverse_moves 红冲原账单（ref='批6-41成本科目纠偏红冲'，date=当日）并过账；
  2. 按产品代码 _create_supplier_bill() 重建账单（自动落 2241.01）并过账；
  3. item.move_id 指向新账单；新账单 ref 追加「（批6科目纠偏重记）」审计标记。
幂等判重：以账单行科目现状为准 —— 已无 6401 行的账单直接跳过（重复执行零副作用）。
草稿账单不在此脚本范围（列出提示，可人工改行科目）。

运行（只读演练，默认 DRY_RUN=1）：
    cd c-系统实现/odootour && source .env
    docker compose run --rm odoo python3 /usr/lib/odoo/odoo-server/odoo-bin \
        shell -c /etc/odoo/odoo.conf --db_host=db --db_user=odoo \
        --db_password=$POSTGRES_PASSWORD -d tour20 --no-http \
        < scripts/fix_dd41_bills.py
正式执行（备份门禁后）：
    DRY_RUN=0 docker compose run --rm odoo python3 ... < scripts/fix_dd41_bills.py
"""
import os

DRY_RUN = os.environ.get('DRY_RUN', '1') != '0'

items = env['ta.dispatch.item'].search([
    ('move_id', '!=', False),
    ('departure_id.biz_mode_id.code', '=', '41'),
], order='id')

targets, drafts = [], []
for item in items:
    move = item.move_id
    if not move:
        continue
    if move.state != 'posted':
        drafts.append((item, move))
        continue
    if any(line.account_id.code == '6401' for line in move.line_ids):
        targets.append((item, move))

print(f"41 代订计调条目（有账单）：{len(items)} 个")
print(f"待纠偏（已过账且含 6401 行）：{len(targets)} 个")
print(f"草稿账单（不在本脚本范围）：{len(drafts)} 个")
for item, move in drafts:
    print(f"  - {item.name} move={move.id} {move.ref}")

done = 0
for item, move in targets:
    print(f"{'DRY' if DRY_RUN else 'FIX'}  {item.name} move={move.id} "
          f"amount={move.amount_total:.2f} ref={move.ref}")
    if DRY_RUN:
        continue
    try:
        rev = move._reverse_moves(default_values_list=[{
            'ref': '批6-41成本科目纠偏红冲',
            'date': fields.Date.context_today(item),
        }])
        rev.action_post()
        new_bill = item._create_supplier_bill()
        new_bill.ref = f"{new_bill.ref}（批6科目纠偏重记）"
        new_bill.action_post()
        item.move_id = new_bill
        env.cr.commit()
        done += 1
        print(f"  OK 红冲 move={rev.id}，新账单 move={new_bill.id}")
    except Exception as exc:
        env.cr.rollback()
        print(f"  ! 失败：{exc}")

if not DRY_RUN:
    print(f"\n已纠偏：{done}/{len(targets)}")
print("DRY_RUN=%s" % ('1（只读演练，未写库）' if DRY_RUN else '0（已正式执行）'))
