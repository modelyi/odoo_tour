#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 `security/ir.access.csv` 每一行的 `domain` 在目标库是否还走得通。

为什么需要它（实测踩到的）：19 的 `ir.rule.domain_force` **装载时不校验字段**，
一条引用了不存在字段的死规则可以在现网躺很多年（求值时才炸，且只在触发那条规则
的读写时炸）。20 把记录规则并进 `ir.access.domain`，`convert_csv_import` 装载时会
用真实 registry 求值域：

    Invalid domain [('plan_id.reg_ids.partner_id', '=', user.partner_id.id)]:
    Invalid field tour.plan.reg.partner_id in condition ('partner_id', '=', 2)

后果不是"这行装不上"，而是**整个 CSV 抛异常 → 模块装载失败**。转换工具是批量生成
的，所以 19 里任何一条死规则都会变成 20 侧的装载阻塞。本脚本把这种行**隔离**出来
（不是静默删除），交人工决定改域还是砍规则。

域是 20 的扁平前缀记法，`'|'`/`'&'` 是裸字符串、叶子是 3 元组。只用 `ast` 走树取叶子，
不 `eval`（域里带 `user.partner_id.id` 这类上下文符号，literal_eval 吃不下，而 eval
等于执行任意代码）。

用法：
    # 1) 从目标库导出字段目录（容器内 trust 认证，本机不留口令）
    docker exec odoo20-db psql -U odoo -d <db> -AtF'|' -c "
      select m.model, f.name, coalesce(f.relation,'')
        from ir_model_fields f join ir_model m on m.id = f.model_id" > /tmp/fields.psv
    # 2) 校验（默认只报告）；--split 才把坏行拆到 <csv>.baddomains.csv
    python3 check_domains.py <ir.access.csv> --fields /tmp/fields.psv [--split]

退出码非 0 = 存在走不通的域。`--split` 会重写原 CSV（先备份 .bak）。
"""
import argparse
import ast
import csv
import os
import sys

# 20 的 ir.access 装载入口除了字段存在性，还要求域能求值成 domain；
# 这里只做静态可达性检查，覆盖实测到的那一类（字段不存在）。
LEAF_OPS = frozenset('=!<>in not in like ilike')  # 仅可读性参考，不参与判定


def load_catalog(path):
    """(model, field) -> relation；以及 model 集合。"""
    fields, models = {}, set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            p = line.rstrip('\n').split('|')
            if len(p) < 2 or not p[0]:
                continue
            model, name = p[0], p[1]
            relation = p[2] if len(p) > 2 else ''
            models.add(model)
            fields[(model, name)] = relation
    return fields, models


def leaves(domain_text):
    """从扁平前缀域里取出所有 (path, op, value_node)。不执行任何代码。"""
    if not domain_text or not domain_text.strip():
        return []
    try:
        tree = ast.parse(domain_text.strip(), mode='eval')
    except SyntaxError as e:
        return [('<无法解析>', str(e), None)]
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) == 3:
            first = node.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                out.append((first.value,
                            getattr(node.elts[1], 'value', '?'),
                            node.elts[2]))
    return out


def resolve(path, model, fields, models):
    """沿点号路径走字段目录，返回 (ok, 断在哪一段, 提示)。"""
    hops = path.split('.')
    cur = model
    for i, hop in enumerate(hops):
        if cur not in models:
            return False, '.'.join(hops[:i + 1]), f'{cur} 不是目标库已注册模型'
        rel = fields.get((cur, hop))
        if rel is None:
            return False, '.'.join(hops[:i + 1]), f'{cur}.{hop} 不存在'
        if i < len(hops) - 1:
            if not rel:
                return False, '.'.join(hops[:i + 1]), f'{cur}.{hop} 不是关联字段，不能继续下钻'
            cur = rel
    return True, path, ''


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path')
    ap.add_argument('--fields', required=True)
    ap.add_argument('--split', action='store_true',
                    help='把坏行拆到 <csv>.baddomains.csv 并重写原文件（先存 .bak）')
    args = ap.parse_args(argv[1:])

    fields, models = load_catalog(args.fields)

    with open(args.csv_path, newline='', encoding='utf-8') as f:
        rdr = csv.DictReader(f)
        header, rows = rdr.fieldnames, list(rdr)
    if 'domain' not in (header or []):
        print(f'{args.csv_path} 没有 domain 列，跳过')
        return 0

    bad = []
    for row in rows:
        model = row.get('model_id') or ''
        for path, op, _val in leaves(row.get('domain', '')):
            ok, where, why = resolve(path, model, fields, models)
            if not ok:
                bad.append((row, path, where, why))
                break
    print(f'校验 {len(rows)} 行（目标库 {len(models)} 个模型）：'
          f'{len(bad)} 行域走不通')
    for row, path, where, why in bad:
        print(f'  ✗ {row["id"]}\n      模型 {row["model_id"]} 域路径 {path}'
              f' → 断在 {where}：{why}')
    if args.split and bad:
        bad_ids = {row['id'] for row, *_ in bad}
        os.replace(args.csv_path, args.csv_path + '.bak')
        keep = [r for r in rows if r['id'] not in bad_ids]
        with open(args.csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(keep)
        with open(args.csv_path + '.baddomains.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=header + ['_why'])
            w.writeheader()
            for row, _p, where, why in bad:
                w.writerow({**row, '_why': f'{why}（断在 {where}）'})
        print(f'  已重写：{len(keep)} 行留在 {os.path.basename(args.csv_path)}，'
              f'{len(bad)} 行隔离到 {os.path.basename(args.csv_path)}.baddomains.csv')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
