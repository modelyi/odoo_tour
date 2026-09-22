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

作用域由 `--scope-modules` 决定，只输出这些模型上的行。装载判据**不能**靠 model→module
归属推断（19 的归属在 20 会失配：`hr.contract.type` 在 19 记在 `hr` 名下、20 归独立的
`hr_contract`），必须传目标库实际的 `ir_model` 清单 `--target-models`；
不在其中的行写进 `<out>.deferred.csv` 并附原因 —— 是延后，不是丢弃，依赖就位后重跑即回收。
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
    ap.add_argument('--owner20', default=f'{sp}/model_owner20.psv',
                    help='20 侧 model|declaring module（`ir_model × ir_model_data(model=\'ir.model\')`）。'
                         '给定时自动算 depends 并写 manifest；核心模型的归属两侧会变'
                         '（如 res.partner.bank 在 19 属 base、20 属 account），只能以 20 为准')
    ap.add_argument('--target-models', default='',
                    help='目标库实际的 ir_model.model 清单（每行一个）。给定时作为唯一装载判据：'
                         '不在其中的行一律延后，因为 model→module 的归属推断在 20 会失配')
    ap.add_argument('--target-groups', default='',
                    help='目标库实际存在的组 xmlid 清单（module.name，每行一个）。'
                         '引用不存在的 group_id/id 会让整个 CSV 装载失败，所以同样要门控')
    ap.add_argument('--manifest-out', default='',
                    help='写出桥接模块 __manifest__.py 的路径（需 --owner20 可用）')
    ap.add_argument('--installed-modules', default='',
                    help='已装模块名清单（每行一个）。给定时按依赖把行切成"现在可装"和"待模块就位"两份，'
                         '避免手工裁剪（本次 129→46→188 的三次试错就是这个坑）')
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

    owner20 = {}
    if os.path.exists(args.owner20):
        for line in open(args.owner20):
            p = line.rstrip().split('|')
            if len(p) == 2:
                owner20[p[0]] = p[1]

    def req(r):
        """这一行装得上所需的最早模块集合：模型的 20 侧归属（查无则回落 19）+ 组的声明模块。"""
        mod = owner20.get(r['model_id']) or owner.get(r['model_id'])
        need = {mod} if mod else set()
        if r['group_id/id']:
            need.add(r['group_id/id'].split('.')[0])
        return need, mod

    # 归属推断不足以判定"装得上"：19 的 model→module 映射在 20 会失配
    # （`hr.contract.type` 在 19 属 hr、20 里 hr_contract 独立；`applicant.send.mail` 在 20 已删）。
    # 唯一可靠的判据是目标库**实际的 ir_model 注册表**，所以可选传入。
    target_models = None
    if args.target_models:
        target_models = {x for x in open(args.target_models).read().split() if x}
        print(f'目标库注册表 {len(target_models)} 个模型（作为唯一装载判据）')
    target_groups = None
    if args.target_groups:
        target_groups = {x for x in open(args.target_groups).read().split() if x}
        print(f'目标库现有组 {len(target_groups)} 个')

    keep, defer = rows, []
    if args.installed_modules or target_models is not None or target_groups is not None:
        installed = ({x for x in open(args.installed_modules).read().split() if x}
                     if args.installed_modules else None)
        keep, defer = [], []
        for r in rows:
            need, mod = req(r)
            grp = r['group_id/id']
            if target_models is not None and r['model_id'] not in target_models:
                r['_why'] = '目标库 ir_model 无此模型（20 已删/改名，或声明模块未装）'
            elif target_groups is not None and grp and grp not in target_groups:
                r['_why'] = '目标库无此组 xmlid（引用不存在的组会整批失败）'
            elif mod is None:
                r['_why'] = '模型在 20 侧查无归属（按 TDS-30 §4/§5 处置）'
            elif installed is not None and (miss := sorted(need - installed)):
                r['_why'] = '依赖未装：' + ','.join(miss)
            (defer if r.get('_why') else keep).append(r)

    out = args.out or os.path.join(args.eff, 'ir.access.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(keep)
    print(f'输出 {len(keep)} 行 → {out}（作用域外跳过 {n_skip} 行）')
    if defer:
        with open(out + '.deferred.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=HEADER + ['_why'])
            w.writeheader()
            w.writerows(defer)
        print(f'延后 {len(defer)} 行 → {out}.deferred.csv（依赖就位后再生成，不是丢弃）')

    if not owner20:
        print(f'未找到 {args.owner20}：跳过 depends 计算（桥接模块的依赖要人工给）')
        return 0
    depends, dangling = set(), []
    for r in keep:
        need, mod = req(r)
        if mod is None and r['model_id'] not in dangling:
            dangling.append(r['model_id'])
        depends |= need
    if dangling:
        print(f'⚠ {len(dangling)} 个模型在 20 侧查无归属（多半是 20 已删的模型，'
              f'必须按 TDS-30 §4/§5 先处置再装载）：{", ".join(sorted(dangling)[:8])}')
    print(f'自动 depends（{len(depends)}）：{", ".join(sorted(depends))}')
    if args.manifest_out:
        man = {'name': 'TMS 19→20 权限桥接层', 'version': '20.1.1.0.0', 'category': 'Hidden',
               'summary': '承载从 19 重建的有效权限（ir.access 行），由 security_19to20 生成',
               'depends': sorted(depends), 'data': ['security/ir.access.csv'],
               'installable': True, 'application': False, 'license': 'LGPL-3'}
        with open(args.manifest_out, 'w', encoding='utf-8') as f:
            f.write('# -*- coding: utf-8 -*-\n' + repr(man) + '\n')
        print(f'写 manifest → {args.manifest_out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
