# -*- coding: utf-8 -*-
"""批6 P0-6 存量收入确认补全（发团日口径 BS-10 §7.2，幂等）。

范围：state in (departed, settled) 且无已过账收入确认记录的发团计划。
口径完全复用产品代码：
  DRY_RUN 走 ta.departure._ta_revenue_recognition_amounts()（纯计算，零写入）；
  正式执行走 ta.departure.action_recognize_revenue()（含幂等与凭证落账）。
  - 总额法（1/12/13/14/15/21/31）：Σ有效订单含税金额，按公司 ta_vat_rate 拆
    贷 6001.01 净额 + 2221.01 销项税，借客户应收科目（与收款认领自然核销）。
  - 净额法（41）：差价 = Σ订单 − Σ已确认计调单，≤0 跳过；
    借 2241.01 代收代付 / 贷 6001.03（公司拆税开关打开时拆销项税）。
  - 其余模式或无有效订单：自动跳过。
幂等：departure_id 存在已过账确认记录即跳过（unique 判重兜底）。

运行（只读演练，默认 DRY_RUN=1）：
    cd c-系统实现/odootour && source .env
    docker compose run --rm odoo python3 /usr/lib/odoo/odoo-server/odoo-bin \
        shell -c /etc/odoo/odoo.conf --db_host=db --db_user=odoo \
        --db_password=$POSTGRES_PASSWORD -d tour20 --no-http \
        < scripts/backfill_revenue_recognition.py
正式执行（备份门禁后）：
    DRY_RUN=0 docker compose run --rm odoo python3 ... < scripts/backfill_revenue_recognition.py
"""
import os
from collections import defaultdict

DRY_RUN = os.environ.get('DRY_RUN', '1') != '0'

deps = env['ta.departure'].search([
    ('state', 'in', ('departed', 'settled')),
    '!', ('recognition_ids.state', '=', 'posted'),
], order='date_start, id')

stats = defaultdict(lambda: {'n': 0, 'gross': 0.0, 'net': 0.0, 'tax': 0.0})
skips = []
created = 0

for dep in deps:
    amounts = dep._ta_revenue_recognition_amounts()
    if not amounts:
        stats['跳过（无金额/非确认模式）']['n'] += 1
        continue
    key = f"{amounts['mode']} / 模式 {amounts['mode_code'] or '?'}"
    stats[key]['n'] += 1
    stats[key]['gross'] += amounts['gross']
    stats[key]['net'] += amounts['net']
    stats[key]['tax'] += amounts['tax']
    if not DRY_RUN:
        try:
            recs = dep.action_recognize_revenue()
            if recs:
                rec = recs[0]
                created += 1
                print(f"OK  {dep.code or dep.name} [{key}] "
                      f"base={amounts['gross']:.2f} net={amounts['net']:.2f} "
                      f"tax={amounts['tax']:.2f} rec={rec.id} move={rec.move_id.id}")
            env.cr.commit()
        except Exception as exc:
            env.cr.rollback()
            skips.append(f"{dep.code or dep.name}: {exc}")

print(f"\n=== 补记范围：{len(deps)} 个发团（已发团/已结算且无已过账确认） ===")
if not DRY_RUN:
    print(f"已创建收入确认记录：{created}")
for key, s in sorted(stats.items()):
    print(f"{key}: {s['n']} 个，base={s['gross']:.2f} net={s['net']:.2f} tax={s['tax']:.2f}")
for msg in skips[:20]:
    print(f"  ! {msg}")

print("DRY_RUN=%s" % ('1（只读演练，未写库）' if DRY_RUN else '0（已正式执行）'))
