# -*- coding: utf-8 -*-
"""回填 tour.line.adult_price：用 team_orders.csv 历史成交数据推导每条线路成人价。

公式：adult_price = round( Σ InCom_QuoSum / Σ SumAdultNum )
  - 排除 LineID=0 或空（未关联线路的脏数据，约 3.5 万条）
  - 净额口径：负数(退款)与 0 值一并计入求和，与迁移入库 tour.plan 的口径一致，
    保证推导出的「历史成交均价」与调研样例一致（LineID 314→466 / 305→570 / 315→651 / 312→318）
  - 仅回填 ΣInCom_QuoSum>0 且 ΣSumAdultNum>0 的线路（否则均价非正，无意义）

映射：team_orders.LineID --(line_products.csv)--> HelpCode --(tour.line.help_code)--> tour.line
幂等：结果由静态 CSV 确定性推导，重跑结果一致（覆盖式更新）。

运行（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms --no-http < scripts/backfill_line_price.py
"""
import csv
import os

DATA_DIR = '/mnt/et_data'


def _num(v):
    """兼容 '2400.0000' / '' / 含 ',' '*' 的数字，与 migrate_et_data.to_float 语义一致。"""
    t = (v or '').replace(',', '').replace('*', '').strip()
    if not t:
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


def build_line_id_map():
    """line_products.csv -> {源 LineID: (HelpCode, LineName)}"""
    m = {}
    with open(os.path.join(DATA_DIR, 'line_products.csv'),
              encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh):
            lid = (r.get('LineID') or '').strip()
            if not lid:
                continue
            m[lid] = ((r.get('HelpCode') or '').strip(),
                      (r.get('LineName') or '').strip())
    return m


def aggregate_orders():
    """team_orders.csv 按 LineID 聚合 ΣInCom_QuoSum / ΣSumAdultNum（流式）。"""
    agg = {}          # LineID -> [sum_q, sum_a]
    skipped_lid0 = 0
    with open(os.path.join(DATA_DIR, 'team_orders.csv'),
              encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh):
            lid = (r.get('LineID') or '').strip()
            if not lid or lid == '0':
                skipped_lid0 += 1
                continue
            q = _num(r.get('InCom_QuoSum'))
            a = _num(r.get('SumAdultNum'))
            e = agg.setdefault(lid, [0.0, 0.0])
            e[0] += q
            e[1] += a
    return agg, skipped_lid0


def main():
    Line = env['tour.line']

    # help_code -> record（help_code 在 line_products.csv 中 212 条全唯一非空）
    by_help = {}
    for rec in Line.with_context(active_test=False).search([]):
        if rec.help_code:
            by_help[rec.help_code] = rec

    id_map = build_line_id_map()
    agg, skipped_lid0 = aggregate_orders()

    updated = 0
    no_line = 0      # LineID 未出现在 line_products.csv
    no_help = 0      # HelpCode 未匹配到 tour.line
    invalid = 0      # 净额 <=0，跳过
    samples = []

    for lid, (sum_q, sum_a) in agg.items():
        if sum_q <= 0 or sum_a <= 0:
            invalid += 1
            continue
        info = id_map.get(lid)
        if info is None:
            no_line += 1
            continue
        help_code, line_name = info
        rec = by_help.get(help_code)
        if rec is None:
            no_help += 1
            continue
        price = round(sum_q / sum_a)
        rec.write({'adult_price': float(price)})
        updated += 1
        samples.append((lid, help_code, line_name,
                        round(sum_q / sum_a, 2), price))

    env.cr.commit()

    print('========== 线路历史成交均价回填结果 ==========')
    print('聚合 LineID 数（排除 0/空）: %d' % len(agg))
    print('跳过 LineID=0/空 行: %d' % skipped_lid0)
    print('净额<=0 跳过（无法推导均价）: %d' % invalid)
    print('LineID 未映射到 line_products: %d' % no_line)
    print('HelpCode 未匹配 tour.line: %d' % no_help)
    print('成功回填 tour.line: %d' % updated)
    print('---------- 抽查样例（调研基准） ----------')
    for lid, hc, name, raw, p in samples:
        if hc in ('XCZYLY', 'DGLY', 'XCZYZX9R', 'GYJC'):
            print('  LineID=%s  %s(%s)  净额均价=%.2f -> adult_price=%d'
                  % (lid, name, hc, raw, p))
    priced = Line.search_count([('adult_price', '>', 0)])
    total = Line.search_count([])
    print('---------- 回填后统计 ----------')
    print('tour.line 有价线路数: %d / %d' % (priced, total))


if __name__ == '__main__':
    main()
