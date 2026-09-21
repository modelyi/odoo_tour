# -*- coding: utf-8 -*-
"""v3 有效权限（eff/*.csv）→ 20 的 `security/ir.access.csv`。

20 侧格式（实测 235 个 core 文件完全一致）：
    id,name,model_id,group_id/id,operation,domain
  * 文件名必须是 `ir.access.csv`（`convert_csv_import` 用文件名 `split('-')[0]` 反推模型 →
    决定行内 `model_id` 的解析方式），且 **不能**与 19 的 `ir.model.access.csv` 同名共存；
  * `model_id` 放**技术模型名**（不是 xmlid）；
  * `operation` 是 `crud` 的非空子集，但字面值必须是 20 的 Selection 键 —— 内部顺序固定为
    `crud`（`rud` 合法、`rucd` 不合法），不是任意排列；
  * `group_id/id` 留空 = restriction（对全体用户 AND 生效），填组 xmlid = permission（彼此 OR）。

作用域由 `--scope-models` 决定，只输出这些模型上的行 —— 装载到只装了部分模块的库时，
越界的 `model_id` 会让 ir.access 解析不到 `ir.model` 而整批失败，这是**故意让它失败**：
桥接模块必须按"随包依赖可选"切分，不能一把梭。
"""
import argparse
import csv
import os
import re
import sys

HEADER = ['id', 'name', 'model_id', 'group_id/id', 'operation', 'domain']
# odoo/addons/base/models/ir_access.py:16 —— operation 是 Selection，
# 不在这 15 个键里的值（例如按 r/u/c/d 顺序拼出的 'rucd'）会被写成 NULL，
# 装载时撞 NOT NULL 约束整批失败，所以出站前无条件校验。
CRUD_SELECTION = {'crud', 'cru', 'crd', 'cud', 'rud', 'cr', 'cu', 'cd', 'ru', 'rd', 'ud',
                  'c', 'r', 'u', 'd'}


def sanitize(s):
    return re.sub(r'[^a-z0-9_]', '_', s.lower())


def load(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sp = os.environ.get('SEC20', '/tmp/b0/sec20')
    ap = argparse.ArgumentParser()
    ap.add_argument('--eff', default=os.path.join(here, 'eff'))
    ap.add_argument('--model-xid', default=f'{sp}/model_xid.psv')
    ap.add_argument('--scope-modules', default='',
                    help='逗号分隔：只输出这些模块声明的模型（按 19 的 ir.model xmlid 前缀判定）')
    ap.add_argument('--also-custom-groups', default='',
                    help='逗号分隔：这些模块声明的组，即使在 core 模型上也要输出（跨模块授权）')
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    owner = {}
    for line in open(args.model_xid):
        p = line.rstrip().split('|')
        if len(p) == 2:
            owner[p[1]] = p[0].split('.')[0]
    scope_models = {m for m, mod in owner.items()
                    if mod in {x for x in args.scope_modules.split(',') if x}}

    rows, seen = [], set()

    def add(model, group, ops, domain, src):
        key = (model, group, ops)
        if key in seen:
            return
        seen.add(key)
        rid = 'access_%s_%s_%s' % (sanitize(model), sanitize(group or 'restriction'), sanitize(ops))
        rows.append({'id': rid,
                     'name': '%s / %s / %s' % (model, group or '(restriction)', ops),
                     'model_id': model,
                     'group_id/id': group,
                     'operation': ops,
                     'domain': domain})

    n_skip = 0
    for r in load(os.path.join(args.eff, 'rows_effective.csv')):
        in_scope = r['model'] in scope_models
        custom = args.also_custom_groups and \
            r['group'].split('.')[0] in {x for x in args.also_custom_groups.split(',') if x}
        if not (in_scope or custom):
            n_skip += 1
            continue
        add(r['model'], r['group'], r['ops'], r['domain'], r['source'])
    for r in load(os.path.join(args.eff, 'restrictions_effective.csv')):
        if r['model'] not in scope_models:
            n_skip += 1
            continue
        add(r['model'], '', r['ops'], r['domain'], r['source'])

    bad_ops = sorted({r['operation'] for r in rows} - CRUD_SELECTION)
    if bad_ops:
        sys.exit('operation 非法（20 是 Selection，内部顺序必须是 crud）：' + ', '.join(bad_ops))
    ids = [r['id'] for r in rows]
    if len(set(ids)) != len(ids):
        sys.exit('存在重复 xmlid，装载时会互相覆盖')

    out = args.out or os.path.join(args.eff, 'ir.access.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    print(f'输出 {len(rows)} 行 → {out}（作用域外跳过 {n_skip} 行）')


if __name__ == '__main__':
    sys.exit(main())
