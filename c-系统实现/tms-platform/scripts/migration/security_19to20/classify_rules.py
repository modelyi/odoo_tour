# -*- coding: utf-8 -*-
"""19 权限语义 → 20 ir.access 行的「有效权限」重建器。

与 conv_security2.py 的差别：conv_security2 逐条平移 XML 声明，遇到
「记录规则挂在没有 access 行的组上」就判为 inert 丢弃。这在 19 的语义下是错的：

  19 组继承：group_sale_salesman_all_leads ⇒ group_sale_salesman ⇒ base.group_user
  → 属于子组的用户自动落在父组里，因此命中父组的 access 行；
  → 记录规则则按「用户所属的任意组」匹配，不要求该组自己有 access 行。

所以 crm.lead 的 "All Leads" 规则（挂在 all_leads，而 all_leads 没有 access 行）
是**生效**的：它把父组 salesman 的 "Personal Leads" 限制放宽回全部。
丢弃 = 静默收窄（功能回归）；反过来只把它当 restriction 平移 = 静默放宽。

本脚本按人群（population = 每个组）重建有效权限，输出 20 侧应当声明的行集合：
  有效域(人群 P, 模型 M) = AND(全局规则) ∧ OR(命中 P 的组规则)   —— 无组规则命中则不设限
20 侧 permission 行（带 group）之间是 OR，与 19 的组规则 OR 语义一致，
故每个 (M, P) 输出一行带 domain 的 permission 行即可等价复现。
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations

try:
    import domains20
    MERGE = True
except ImportError:      # 没带 odoo20 的 PYTHONPATH 时退化为"交人工合并"
    domains20, MERGE = None, False

OPS = [('perm_read', 'r'), ('perm_write', 'u'), ('perm_create', 'c'), ('perm_unlink', 'd')]
# 20 的 ir.access.operation 是 Selection，合法值只有 CRUD_SELECTION 的 15 个键，
# 且每个键内部按 'crud' 的字面顺序排列（'rud' 合法、'rucd' 不合法）。
# 19 的 perm_* 顺序是 r/u/c/d，直接拼接会生成非法值 → 落库时静默成 NULL 并撞 NOT NULL 约束。
CANON = 'crud'
# 与 odoo/addons/base/models/ir_access.py:16 CRUD_SELECTION 的键一致（15 个非空子集）；
# MERGE 可用时下面会 import 真值做交叉核对，本地这份保证无 odoo 环境也能拦住非法值。
CRUD_SELECTION = {'crud', 'cru', 'crd', 'cud', 'rud', 'cr', 'cu', 'cd', 'ru', 'rd', 'ud',
                  'c', 'r', 'u', 'd'}
assert CRUD_SELECTION == {''.join(sorted(c, key=CANON.index))
                          for n in range(1, 5) for c in combinations(CANON, n)}, 'CRUD_SELECTION 抄错'


def canon_ops(codes):
    return ''.join(sorted(set(codes), key=CANON.index))


# 19 里大量「See All」型规则的真实域就是恒真，命中它 = 该人群不受组规则限制
TRIVIAL = {s.replace(' ', '') for s in
           ("[(1,'=',1)]", "[(1, '=', 1)]", '[(True, "=", True)]', "[(1,'in',(1,))]")}


def is_trivial(dom):
    return bool(dom) and dom.replace(' ', '') in TRIVIAL


def combine(doms):
    """只自动合并「0 或 1 条 domain」的情形；多条一律交人工——
    扁平 domain 的 &/| 是前缀记法，机械拼接极易把 arity 接错，
    宁可留 NEEDS_DOMAIN_MERGE 让人判定，也不要生成一条静默错误的规则。"""
    doms = [d for d in doms if d and d not in ('[]', '[(1, \'=\', 1)]')]
    if len(doms) <= 1:
        return doms[0] if doms else '', False
    # 纯展示用（review 工件），故显式写 AND/OR 而非可加载的 domain 字面量
    return ' AND '.join(doms), True


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def build_hierarchy(rows):
    """parents 列 = implied_ids（本组隐含的父组）；成员自动属于父组。"""
    up = {r['xid']: [p for p in (r['parents'].split('|') if r['parents'] else [])] for r in rows}
    memo = {}

    def anc(g, seen=None):
        if g in memo:
            return memo[g]
        seen = seen or set()
        out = set()
        for p in up.get(g, []):
            if p in seen:
                continue
            seen.add(p)
            out.add(p)
            out |= anc(p, seen)
        memo[g] = out
        return out

    return up, anc


def main():
    ap = argparse.ArgumentParser()
    d = os.path.dirname(os.path.abspath(__file__))
    sp = os.environ.get('SEC20', '/tmp/b0/sec20')
    ap.add_argument('--acc', default=f'{sp}/acc19.csv')
    ap.add_argument('--rules', default=f'{sp}/rule19.csv')
    ap.add_argument('--groups', default=f'{sp}/group_xid.csv')
    ap.add_argument('--models', default='',
                    help='可选：model|xmlid 白名单文件，只处理列出的模型')
    ap.add_argument('--outdir', default=f'{sp}/eff')
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    acc, rules, groups = load_csv(args.acc), load_csv(args.rules), load_csv(args.groups)
    up, anc = build_hierarchy(groups)

    limit = None
    if args.models and os.path.exists(args.models):
        limit = {l.rstrip().split('|')[1] for l in open(args.models) if '|' in l}

    grants = defaultdict(lambda: defaultdict(set))   # model -> group(''=全体) -> ops
    for r in acc:
        if r['active'] != 't':
            continue
        if limit and r['model'] not in limit:
            continue
        ops = ''.join(code for k, code in OPS if r.get(k) == 't') or 'r'
        grants[r['model']][r['group_xid'] or ''].update(ops)

    mrules = defaultdict(list)
    for r in rules:
        if r['active'] != 't' or (limit and r['model'] not in limit):
            continue
        # 19 的一条记录规则可挂多个组；导出的分隔符是 ','（现网 25 条如此），
        # 20 的 ir.access 只有单个 group_id → 按组拆开，落成多行同 domain 的 permission 行（OR 语义等价）。
        gs = frozenset(x for x in re.split(r'[,|]', r['groups'] or '') if x)
        ops = ''.join(code for k, code in OPS if r.get(k) == 't') or 'crud'
        mrules[r['model']].append((r['xid'], r['global'] == 't', gs, r['domain'], set(ops)))

    rows, restrictions, review = [], [], []
    for model in sorted(grants):
        rl = mrules.get(model, [])
        globals_ = [x for x in rl if x[1]]
        grouped = [x for x in rl if not x[1]]
        # 19 的全局记录规则 = 对所有用户 AND 生效 —— 与 20 的 restriction（无 group）语义逐字对应，
        # 所以直接落成 restriction 行，不参与人群合并。
        for x in globals_:
            if x[3] and not is_trivial(x[3]) and x[3] != '[]':
                restrictions.append(dict(model=model, domain=x[3], source=x[0],
                                         ops=canon_ops(x[4])))
        populations = sorted({g for g in grants[model] if g} | {g for x in grouped for g in x[2]})
        for p in populations:
            member_of = {p} | anc(p)
            # 该人群拿到的 ops：本组 + 所有父组 + 无组授予
            ops = set()
            for g, o in grants[model].items():
                if g == '' or g in member_of:
                    ops |= o
            if not ops:
                review.append(('NO_GRANT_POP', model, p, '',
                               '组规则命中该人群，但整条继承链上没有任何 access 行'))
                continue
            mine = [x for x in grouped if x[2] and x[2] & member_of]
            if any(is_trivial(x[3]) for x in mine):
                mine = []          # 恒真组规则命中 → 该人群实际不受组规则限制
            dom_list = [x[3] for x in mine if x[3] and x[3] != '[]']
            if MERGE:
                domain = domains20.merge(dom_list, '|')
                merged = len(dom_list) > 1 and domain.startswith('UNPARSED')
            else:
                domain, merged = combine(dom_list)
            if merged:
                review.append(('NEEDS_DOMAIN_MERGE', model, p,
                               ','.join(x[0] for x in mine), domain))
            rows.append(dict(model=model, group=p,
                             ops=canon_ops(ops),
                             domain=domain, source=','.join(x[0] for x in mine)))
        # 组规则完全没有对应人群的（例如规则组不在任何授予的继承链上）
        for x in grouped:
            hit = any(x[2] & ({p} | anc(p)) for p in populations)
            if not hit:
                review.append(('UNCOVERED_RULE', model, '|'.join(sorted(x[2])), x[0],
                               '该组规则的人群拿不到任何 ops（真正 inert）'))

    # operation 是 Selection：非法值在 20 侧会被写成 NULL，装载时撞 NOT NULL 约束，
    # 所以这里无条件硬校验（不依赖 MERGE），不合法就直接失败，不留到装载阶段。
    illegal = sorted({r['ops'] for r in rows + restrictions} - CRUD_SELECTION)
    if illegal:
        raise SystemExit('operation 不是 20 的合法 Selection 值：' + ', '.join(illegal))

    bad = []
    if MERGE:
        # 出站自检：每一条写进 CSV 的 domain 必须能被 20 引擎重新解析
        for r in rows + restrictions:
            if not r['domain']:
                continue
            try:
                domains20.parse(r['domain'])
            except Exception as e:                      # noqa: BLE001
                bad.append((r['model'], r['domain'], str(e)[:120]))
                continue
            out = sorted(domains20.free_names(r['domain']))
            if out:
                review.append(('CTX_OUT_OF_20', r['model'], r.get('group', ''), '',
                              '20 的 access domain 只有 user/time/company_id/company_ids；'
                              '本条用到 ' + ','.join(out) + ' → B1 必须改写'))
        for m, d, e in bad:
            review.append(('BAD_DOMAIN_OUTPUT', m, '', '', e + ' :: ' + d[:160]))
    print(f'引擎自检：出站 domain 不可解析 {len(bad)} 条（MERGE={MERGE}）')
    with open(os.path.join(args.outdir, 'rows_effective.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['model', 'group', 'ops', 'domain', 'source'])
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(args.outdir, 'restrictions_effective.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['model', 'ops', 'domain', 'source'])
        w.writeheader()
        w.writerows(restrictions)
    with open(os.path.join(args.outdir, 'review.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['kind', 'model', 'group', 'xid', 'note'])
        w.writerows(sorted(set(review)))
    print(f'模型 {len(grants)} / permission 行 {len(rows)} / restriction 行 {len(restrictions)}'
          f' / 待复核 {len(set(review))}')
    for k, n in sorted(Counter(r[0] for r in set(review)).items()):
        print(f'  {k}: {n}')


if __name__ == '__main__':
    sys.exit(main())
