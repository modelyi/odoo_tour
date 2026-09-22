#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态检查：XML 里引用的模型，在目标库里到底存不存在。

配合 check_xmlid_order.py 用：后者管「装载顺序」，本脚本管「模型是否存在」。
B1 的真实节奏是「装一次只暴露一个错」，而视图/动作里的模型引用可以离线全量扫出来
（20 删了 19 的模型，例如 `account.group`、`res.bank`，都会以
`Model not found: …` 的形式在建库时装载失败）。

用法：
    python3 check_model_refs.py <addons目录> <目标库已有模型清单.txt> [模块 ...]
目标库清单导出（不含本目录将要新装的模块，所以 Python 里声明的模型也算存在）：
    docker exec odoo20-db psql -U odoo -d <db> -Atc "select model from ir_model" | sort -u > models.txt
"""
import ast
import os
import re
import sys
import xml.etree.ElementTree as ET

# XML 中出现模型名的位置：record model= / 视图 field[name=model] / 动作 res_model
# / 报表 report_model / ir.sequence 的 implementation? 以及 function 标签的 model=
MODEL_SLOTS = re.compile(r'^model$|^res_model$|^report_model$|^model_id$', re.I)
IGNORE_PREFIX = ('mail.thread', 'mail.activity.mixin')   # mixin 不是真模型


def python_models(mod_dir):
    names = set()
    for dp, _dn, fns in os.walk(mod_dir):
        if '__pycache__' in dp:
            continue
        for fn in fns:
            if not fn.endswith('.py'):
                continue
            try:
                src = open(os.path.join(dp, fn), encoding='utf-8').read()
            except UnicodeDecodeError:
                continue
            for m in re.finditer(r"^\s*_name\s*=\s*['\"]([\w.]+)['\"]", src, re.M):
                names.add(m.group(1))
    return names


def xml_model_refs(mod_dir, rel):
    out = []
    root = ET.parse(os.path.join(mod_dir, rel)).getroot()
    for el in root.iter():
        tag = el.tag.split('}')[-1]
        if tag == 'record':
            m = el.get('model')
            if m and not m.startswith('ir.'):        # ir.ui.view 等元模型肯定在
                out.append(('record model=', m))
            for f in el.findall('field'):
                if MODEL_SLOTS.match(f.get('name') or '') and (f.text or '').strip():
                    out.append(('field ' + f.get('name'), f.text.strip()))
        elif tag in ('menuitem', 'function'):
            if el.get('model'):
                out.append((tag + ' model=', el.get('model')))
        elif tag == 'field' and (el.get('name') or '') in ('model', 'res_model') \
                and el.get('ref'):
            out.append(('field ref=', el.get('ref')))
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    addons, models_txt = argv[1], argv[2]
    only = set(a for a in argv[3:] if not a.startswith('--'))
    known = {l.strip() for l in open(models_txt) if l.strip()}
    mods = sorted(d for d in os.listdir(addons)
                  if os.path.isfile(os.path.join(addons, d, '__manifest__.py'))
                  and (not only or d in only))
    for mod in mods:
        known |= python_models(os.path.join(addons, mod))

    hits, files = {}, 0
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
            files += 1
            try:
                refs = xml_model_refs(mdir, rel)
            except ET.ParseError:
                continue
            for where, m in refs:
                if m in IGNORE_PREFIX or m in known or m.startswith('x_'):
                    continue
                hits.setdefault(m, []).append(f'{mod}/{rel} ({where})')
    print(f'扫描 {len(mods)} 模块 / {files} 个 XML；'
          f'目标库已知模型 {len(known)} 个')
    for m in sorted(hits):
        print(f'  模型不存在 → {m}   （{len(hits[m])} 处，例：{hits[m][0]}）')
    print(f'合计 {len(hits)} 个悬空模型')
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
