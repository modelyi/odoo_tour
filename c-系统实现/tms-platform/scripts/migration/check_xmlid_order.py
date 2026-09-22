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
    python3 check_xmlid_order.py <addons目录> [模块名 ...] [--missing] [--xid-db=PATH]

退出码非 0 = 存在顺序缺陷（可直接进 CI）。`--missing` 额外要求「全库查无此 xid」
也算失败（含 ORM 自动 xid `model_*`/`access_*` 之外的误报，默认不当失败）。

`--xid-db=PATH`：目标库 ir_model_data 导出（每行 `module.name`），用来把「跨模块引用」
从"只报不计错"升级成硬失败 —— 20 把上游 xid 挪走/删掉的正是这一类
（例：19 的 `website.default_website` 在 20 变成惰性登记的 `base.default_website`，
空库装载时报 `External ID not found: website.default_website`）：

    docker exec odoo20-db psql -U odoo -d <db> -Atc \
      "select module||'.'||name from ir_model_data" | sort -u > /tmp/b0/xids20.txt

有了它还会顺带扫 Python 里的 `env.ref('mod.name')`（运行期才会炸的那一类）。
"""
import ast
import os
import re
import sys
import xml.etree.ElementTree as ET

XID = r'[A-Za-z0-9_.]+'
# 会存成 xid 的字段/属性（ref= 与 eval 里的字符串）。inherit_id 例外：
# <template inherit_id="…"> 在 _tag_template 里被转成 <field name="inherit_id" ref="…">
# （convert.py:529），是**装载期**解析，不是渲染期。
REF_ATTRS = ('ref', 'xml_id', 'groups', 'parent', 'action', 'inherit_id')
FMT_RE = re.compile(rf'%\(({XID}(?:\.{XID})?)\)')
# eval 里只有 `ref('...')` 才是 xid；直接抓所有字符串字面量会把
# {'view_mode': 'list'} 这类字典值全误判成 xid
REF_CALL_RE = re.compile(r"ref\(\s*['\"]([^'\"]+)['\"]")
# 逗号/空格分隔的 xid 列表（groups_id 之类）
LIST_RE = re.compile(XID)
# Python 侧 env.ref('mod.name') / self.env.ref("mod.name")
PY_REF_RE = re.compile(r"env\.ref\(\s*['\"]([\w.]+)['\"]")
# 这些字段的内容是 arch/QWeb 子树：里面的 groups= 等**渲染期**才解析
ARCH_FIELDS = {'arch', 'arch_base', 'template_content', 'custom_code'}
# 这些字段是 Python 表达式，`'…' % (object.name)` 会被 %(x)s 误判成 xid
SKIP_FMT_FIELDS = {'print_report_name', 'code', 'python_value'}


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
    # groups="-mod.xid" 里的前导 '-' 是「从 groups_id 移除」，仍要求 xid 存在
    raw = raw[1:].strip() if raw.startswith('-') else raw
    if '.' in raw:
        m, _, n = raw.partition('.')
        if n:
            out.append((m, n))
    else:
        out.append((mod, raw))
    return out


def scan_file(path, mod):
    """按文档顺序产出 (pos, kind, (module, name))：kind 'def' | 'ref' | 'ref_render'。"""
    events = []
    tree = ET.parse(path)
    root = tree.getroot()

    def add_refs(text, mode='list', render=False):
        """mode: list=逗号/空格分隔的 xid；eval=只取 ref('…')；fmt=只取 %(xid)s。"""
        if not text:
            return
        if mode == 'fmt':
            toks = [m.group(1) for m in FMT_RE.finditer(text)]
        elif mode == 'eval':
            toks = [m.group(1) for m in REF_CALL_RE.finditer(text)]
        else:
            toks = re.split(r'[, ]+', text)
        for raw in toks:
            for mm, nn in norm(raw, mod):
                events.append(('ref_render' if render else 'ref', (mm, nn)))

    def visit(el, render=False):
        tag = el.tag.split('}')[-1]
        if tag in ('odoo', 'data'):
            for ch in el:
                visit(ch, render)
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
            # 模板 = ir.ui.view(qweb) 记录：自身属性（inherit_id）装载期解析，
            # 子树里的 groups=/t-out/… 全在渲染期，判成装载期缺陷会误报。
            events.append(('def', (mod, rid)))
            for a in REF_ATTRS:
                if el.get(a):
                    add_refs(el.get(a), 'list', False)
            for ch in el:
                visit(ch, True)
            return
        # arch 子树里的 groups=/t-ref 是**渲染期**才解析的，不是装载期（判错会毁掉信任）
        if tag == 'field' and (el.get('name') or '') in ARCH_FIELDS:
            render = True
        for a in REF_ATTRS:
            if el.get(a):
                add_refs(el.get(a), 'list', render)
                add_refs(el.get(a), 'fmt', render)
        # eval= 不只在 <field> 上：<function eval="[ref('…'), …]"/> 同样引用 xid
        if el.get('eval'):
            add_refs(el.get('eval'), 'eval', render)
            add_refs(el.get('eval'), 'fmt', render)
        fname = el.get('name') or ''
        if tag == 'field' and el.text and fname not in SKIP_FMT_FIELDS:
            add_refs(el.text, 'fmt', render)
        for ch in el:
            visit(ch, render)

    for ch in root:
        visit(ch)
    return events


def main(argv):
    flags = {a for a in argv if a.startswith('--')}
    xid_db = None
    for a in list(flags):
        if a.startswith('--xid-db='):
            xid_db = a.split('=', 1)[1]
            flags.discard(a)
    argv = [a for a in argv if not a.startswith('--')]
    if len(argv) < 2:
        print(__doc__)
        return 2
    root_dir, only = argv[1], set(argv[2:])
    db_xids = set()
    if xid_db:
        with open(xid_db, encoding='utf-8') as f:
            db_xids = {ln.strip() for ln in f if ln.strip()}
        print(f'目标库 xid 清单：{len(db_xids)} 条（{xid_db}）')
    mods = sorted(d for d in os.listdir(root_dir)
                  if os.path.isfile(os.path.join(root_dir, d, '__manifest__.py'))
                  and (not only or d in only))

    all_defs, per_mod, auto_xids = {}, {}, set()
    py_refs = []
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
                    pypath = os.path.join(dirpath, fn)
                    try:
                        src = open(pypath, encoding='utf-8').read()
                    except UnicodeDecodeError:
                        continue
                    for m in re.finditer(r"_name\s*=\s*['\"]([\w.]+)['\"]", src):
                        u = m.group(1).replace('.', '_')
                        auto_xids |= {(mod, f'model_{u}'), (mod, f'access_{u}')}
                    for ln, line in enumerate(src.splitlines(), 1):
                        for m in PY_REF_RE.finditer(line):
                            if 'raise_if_not_found' in line:
                                continue     # 调用点自己容错了
                            if '.' not in m.group(1):
                                continue     # 裸 xid 的归属在运行期取决于当前模块，跳过
                            py_refs.append((mod, os.path.relpath(pypath, root_dir),
                                            ln, m.group(1)))

    n_bad = 0
    missing = []
    render_bad = []
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
                if kind == 'ref_render':
                    key = f'{payload[0]}.{payload[1]}'
                    if (payload not in all_defs and payload not in auto_xids
                            and db_xids and key not in db_xids):
                        render_bad.append((mod, rel, key))
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
                    if db_xids and key in db_xids:
                        continue           # 目标库里确实有这个 xid
                    if db_xids:
                        print(f'[{mod}] {rel}: 跨模块引用 {key} 在目标库不存在'
                              f'（20 已删除/改名的上游 xid）')
                        n_bad += 1
                        continue
                    missing.append((mod, rel, key, '跨模块'))
                    continue
                cands = all_defs.get(payload)
                if not cands:
                    if payload in auto_xids or (db_xids and key in db_xids):
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
    if render_bad:
        print(f'--- 渲染期引用不存在的 xid（不影响空库装载，但渲染时会炸/静默失效）'
              f'{len(render_bad)} 处：')
        for mod, rel, key in render_bad[:30]:
            print(f'[{mod}] {rel}: {key}')
        if '--missing' in flags:
            n_bad += len(render_bad)
    if py_refs and db_xids:
        undef = [r for r in py_refs
                 if r[3].split('.')[-1]           # 'tour_accounting.' + 变量拼接 → 不算
                 and r[3] not in db_xids
                 and tuple(r[3].split('.', 1)) not in all_defs]
        if undef:
            print(f'--- Python env.ref 指向目标库不存在的 xid（运行期才炸）{len(undef)} 处：')
            for mod, rel, ln, key in undef[:40]:
                print(f'[{mod}] {rel}:{ln}: {key}')
            n_bad += len(undef) if '--missing' in flags else 0
            print(f'    （不计入缺陷，除非 --missing）' if '--missing' not in flags else '    （计入缺陷）')
    print(f'检查 {len(mods)} 模块 / {sum(len(s) for s in per_mod.values())} 文件：'
          f'{n_bad} 处顺序缺陷；{len(missing)} 条查无 xid')
    return 1 if n_bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
