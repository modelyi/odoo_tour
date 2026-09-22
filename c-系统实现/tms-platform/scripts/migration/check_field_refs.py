#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态检查：XML 记录里写的 `<field name="X">`，在 20 的该模型上到底有没有这个字段。

为什么不能用 information_schema 代替：`ir.actions.report.report_file`、`res.users.groups_id`
这类**非存储字段没有数据库列**，B0 的 §4 列级 diff 看不见它们 —— 但装载时
`ValueError: Invalid field ...` 一样会红。正确口径是 20 registry 的 `ir_model_fields`。

清单导出（用尽量多模块已装的库，覆盖不到的模型本脚本按「未知」跳过，不报）：
    docker exec odoo20-db psql -U odoo -d <db> -Atc \\
      "select model||'|'||name from ir_model_fields" | sort -u > fields20.txt

用法：
    python3 check_field_refs.py <addons目录> fields20.txt [模块 ...]
"""
import ast
import os
import re
import sys
import xml.etree.ElementTree as ET

SELF_MODELS = {'ir.ui.view'}       # 视图 arch 里的字段由 Odoo 自己校验，模型名也可能带点


def load_fields(path):
    by_model = {}
    for line in open(path, encoding='utf-8'):
        if '|' not in line:
            continue
        model, name = line.rstrip('\n').split('|', 1)
        by_model.setdefault(model, set()).add(name)
    return by_model


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    addons, fields_txt = argv[1], argv[2]
    only = set(a for a in argv[3:] if not a.startswith('--'))
    by_model = load_fields(fields_txt)
    mods = sorted(d for d in os.listdir(addons)
                  if os.path.isfile(os.path.join(addons, d, '__manifest__.py'))
                  and (not only or d in only))
    # 本目录模块自己声明的字段（Python）也算存在
    for mod in mods:
        for dp, dn, fns in os.walk(os.path.join(addons, mod)):
            if '__pycache__' in dp:
                continue
            for fn in fns:
                if not fn.endswith('.py'):
                    continue
                try:
                    src = open(os.path.join(dp, fn), encoding='utf-8').read()
                except UnicodeDecodeError:
                    continue
                owner = None
                for m in re.finditer(r"^(\s*)(_name|_inherit)\s*=\s*['\"]([\w.]+)['\"]|"
                                     r"^\s{4}(\w+)\s*=\s*fields\.", src, re.M):
                    if m.group(3):
                        owner = m.group(3)
                    elif m.group(4) and owner:
                        by_model.setdefault(owner, set()).add(m.group(4))

    bad = []
    nfiles = 0
    for mod in mods:
        mdir = os.path.join(addons, mod)
        man = ast.literal_eval(open(os.path.join(mdir, '__manifest__.py'),
                                    encoding='utf-8').read().split('\n', 1)[1].strip())
        for rel in (man.get('data') or []) + (man.get('demo') or []):
            if not rel.endswith('.xml'):
                continue
            p = os.path.join(mdir, rel)
            if not os.path.exists(p):
                continue
            nfiles += 1
            try:
                root = ET.parse(p).getroot()
            except ET.ParseError:
                continue
            for rec in root.iter('record'):
                model = rec.get('model') or ''
                if not model or model not in by_model:
                    continue                       # 模型未知 → 不判（避免误报）
                for f in rec.findall('field'):
                    name = f.get('name') or ''
                    if not name or f.get('name') == 'type' and f.get('type') == 'xml':
                        continue
                    if name in by_model[model]:
                        continue
                    bad.append((f'{mod}/{rel}', model, name, rec.get('id') or ''))
    seen = set()
    for loc, model, name, rid in bad:
        key = (model, name)
        if key in seen:
            continue
        seen.add(key)
        where = [f'{l} ({r})' for l, _m, _n, r in bad if (l.split("/")[0], model, name)]
        print(f'字段不存在 → {model}.{name}   首次出现 {loc}')
        print(f'    共 {len([1 for x in bad if (x[1], x[2]) == key])} 处：'
              + '; '.join(sorted({l for l, _m, _n, _r in bad if (l.split("/")[0], model, name)}))[:400])
    print(f'扫描 {len(mods)} 模块 / {nfiles} 个 XML：{len(seen)} 个不存在字段')
    return 1 if seen else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
