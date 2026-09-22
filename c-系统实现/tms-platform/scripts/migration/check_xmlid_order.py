#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态检查：模块 data 文件里的 XMLID 引用，在被引用时是否已经装载。

为什么需要它：19 现网库是长年 `-u` 增量升上来的，「引用了后面才定义的 XMLID」
这种缺陷在现网永远不报（被引用的记录早就在库里）。20 是空库全新 `-i`，装载严格按
manifest 的 data 顺序（文件内则按元素顺序）走，同一份代码会当场
`ParseError: External ID not found`。B1 的「空库全绿」gate 必须先把这类问题找干净。

已知局限：只覆盖 XML 声明的 xid 与 manifest 顺序；Python 侧 `self.env.ref()` 是
运行期的，不受装载顺序影响（但记录缺失仍会报，见 --missing 输出）。

用法：
    python3 check_xmlid_order.py <addons目录> [模块名 ...] [--missing]
退出码非 0 = 存在顺序缺陷（可直接进 CI）。`--missing` 额外要求「全库查无此 xid」
也算失败（含 ORM 自动 xid `model_*`/`access_*` 之外的误报，默认不当失败）。
"""
import ast
import os
import re
import sys
import xml.etree.ElementTree as ET

XID = r'[A-Za-z0-9_.]+'
# 会存成 xid 的字段/属性（ref= 与 eval 里的字符串）
REF_ATTRS = ('ref', 'xml_id', 'groups', 'parent', 'action')
FMT_RE = re.compile(rf'%\(({XID}(?:\.{XID})?)\)')
EVAL_RE = re.compile(rf'["\']({XID})["\']')
# 逗号/空格分隔的 xid 列表（groups_id 之类）
LIST_RE = re.compile(XID)


def manifest_xml_files(path):
    with open(path, encoding='utf-8') as f:
        man = ast.literal_eval(f.read().strip())
    files = list(man.get('data') or []) + list(man.get('demo') or [])
    return [p for p in files if p.endswith('.xml') or p.endswith('.csv')]


def norm(raw, mod):
    """把一条引用文本规整成候选 xid 列表 (module, name)。"""
    out = []
    raw = raw.strip()
    if not raw or raw.startswith('$') or raw.startswith('/'):
        return out
    if '.' in raw:
        m, _, n = raw.partition('.')
        if n:
            out.append((m, n))
    else:
        out.append((mod, raw))
    return out


def scan_file(path, mod):
    """按文档顺序产出 (pos, kind, (module, name))：kind 'def' | 'ref'。"""
    events = []
    tree = ET.parse(path)
    root = tree.getroot()

    def add_refs(text, mode='list'):
        """mode: list=逗号/空格分隔的 xid；eval=字符串字面量；fmt=只取 %(xid)s。"""
        if not text:
            return
        if mode == 'fmt':
            toks = [m.group(1) for m in FMT_RE.finditer(text)]
        elif mode == 'eval':
            toks = [m.group(1) for m in EVAL_RE.finditer(text)]
        else:
            toks = re.split(r'[, ]+', text)
        for raw in toks:
            for mm, nn in norm(raw, mod):
                events.append(('ref', (mm, nn)))

    def visit(el):
        tag = el.tag.split('}')[-1]
        if tag in ('odoo', 'data'):
            for ch in el:
                visit(ch)
            return
        rid = (el.get('id') or '').strip()
        if tag == 'record' and rid:
            if el.get('model') == 'ir.ui.menu' and not (
                    (el.findtext('field[@name="name"]') or '').strip()
                    or any(f.get('name') == 'name' and f.get('ref')
                           for f in el.findall('field'))):
                # no_name 必须排在 def 之前，否则「此前已定义」会把自己算进去
                events.append(('no_name', (mod, rid)))
            events.append(('def', (mod, rid)))
        elif tag == 'menuitem' and rid:
            events.append(('def', (mod, rid)))
        elif tag == 'template' and rid:
            events.append(('def', (mod, rid)))
        for a in REF_ATTRS:
            if el.get(a):
                add_refs(el.get(a), 'list')
                add_refs(el.get(a), 'fmt')
        if tag == 'field':
            # ref= 已在 REF_ATTRS 里处理；这里只看 eval 字面量与内联 %(xid)s
            if el.get('eval'):
                add_refs(el.get('eval'), 'eval')
                add_refs(el.get('eval'), 'fmt')
            if el.text:
                add_refs(el.text, 'fmt')
        for ch in el:
            visit(ch)

    for ch in root:
        visit(ch)
    return events


def main(argv):
    flags = {a for a in argv if a.startswith('--')}
    argv = [a for a in argv if not a.startswith('--')]
    if len(argv) < 2:
        print(__doc__)
        return 2
    root_dir, only = argv[1], set(argv[2:])
    mods = sorted(d for d in os.listdir(root_dir)
                  if os.path.isfile(os.path.join(root_dir, d, '__manifest__.py'))
                  and (not only or d in only))

    all_defs, per_mod, auto_xids = {}, {}, set()
    for mod in mods:
        try:
            files = manifest_xml_files(os.path.join(root_dir, mod, '__manifest__.py'))
        except Exception as e:                                  # noqa: BLE001
            print(f'SKIP {mod}: manifest 解析失败 {e}')
            continue
        seq = []
        for rel in files:
            path = os.path.join(root_dir, mod, rel)
            if rel.endswith('.csv'):
                seq.append((rel, []))
                continue
            if not os.path.exists(path):
                seq.append((rel, [('MISSING', None)]))
                continue
            try:
                events = scan_file(path, mod)
            except ET.ParseError as e:
                seq.append((rel, [('PARSE_ERROR', str(e))]))
                continue
            seq.append((rel, events))
            for kind, xid in events:
                if kind == 'def':
                    all_defs.setdefault(xid, []).append((rel, len(all_defs.get(xid, []))))
        per_mod[mod] = seq
        # Python 声明的模型 → ORM 自动 xid（model_*、access_*），不算缺失
        for dirpath, _dn, fns in os.walk(os.path.join(root_dir, mod)):
            for fn in fns:
                if fn.endswith('.py'):
                    try:
                        src = open(os.path.join(dirpath, fn), encoding='utf-8').read()
                    except UnicodeDecodeError:
                        continue
                    for m in re.finditer(r"_name\s*=\s*['\"]([\w.]+)['\"]", src):
                        u = m.group(1).replace('.', '_')
                        auto_xids |= {(mod, f'model_{u}'), (mod, f'access_{u}')}

    n_bad = 0
    missing = []
    for mod, seq in per_mod.items():
        defined = []                       # 到目前为止已装载的 xid
        for rel, events in seq:
            for kind, payload in events:
                if kind in ('MISSING', 'PARSE_ERROR'):
                    print(f'[{mod}] {rel}: {kind} {payload or ""}')
                    n_bad += 1
                    continue
                if kind == 'def':
                    defined.append(payload)
                    continue
                if kind == 'no_name':
                    # ir.ui.menu 记录没写 name：只有「此前已定义」才成立（否则是 INSERT，
                    # 撞上 name not-null）。现网靠增量升级掩盖，空库必炸。
                    if payload not in defined and '.' not in payload[1]:
                        print(f'[{mod}] {rel}: ir.ui.menu 记录 {payload[1]} 缺 name，'
                              f'且此前未定义 → 空库装载必失败')
                        n_bad += 1
                    continue
                if payload in defined:
                    continue
                owner, name = payload
                key = f'{owner}.{name}'
                if owner != mod:
                    if (owner, name) in all_defs or payload in auto_xids:
                        continue           # 别的模块更早装载？跨模块靠依赖顺序，单独判
                    missing.append((mod, rel, key, '跨模块'))
                    continue
                cands = all_defs.get(payload)
                if not cands:
                    if payload in auto_xids:
                        continue
                    missing.append((mod, rel, key, '本模块无定义'))
                    continue
                def_file = cands[0][0]
                order = [r for r, _e in seq]
                if def_file == rel:
                    print(f'[{mod}] {rel}: 引用 {key} 早于同文件内的定义')
                else:
                    d, r = order.index(def_file), order.index(rel)
                    if d > r:
                        print(f'[{mod}] {rel}: 引用 {key} 早于定义（定义在 {def_file}）')
                    else:
                        continue
                n_bad += 1
    if missing:
        print(f'--- 查无此 xid（可能缺失/误报）共 {len(missing)} 条：')
        for mod, rel, key, note in missing[:60]:
            print(f'[{mod}] {rel}: {key} （{note}）')
        if len(missing) > 60:
            print(f'… 其余 {len(missing)-60} 条略')
        if '--missing' in flags:
            n_bad += len(missing)
    print(f'检查 {len(mods)} 模块 / {sum(len(s) for s in per_mod.values())} 文件：'
          f'{n_bad} 处顺序缺陷；{len(missing)} 条查无 xid')
    return 1 if n_bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
