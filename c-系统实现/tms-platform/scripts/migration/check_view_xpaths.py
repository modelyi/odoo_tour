#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态检查：视图继承的 xpath 锚点在目标库（20）里是否还能定位。

为什么需要它：`<xpath expr="…" position="…">` 定位失败时，19 现网永远不报
（库里存的是当年装上去的结果，长年 `-u` 也没人再碰），20 空库全新 `-i` 会当场
`ParseError: Element '<xpath …>' cannot be located in parent view`。
tour_* 有 77 个 xpath 锚点、Webkul 另有几十个，靠"装一次只炸一个"去排，
每个缺陷要 3–4 分钟；这个脚本一次跑完给出全清单。

判据来源是**目标库的 ir_ui_view.arch**（不是源码 XML）—— 真正的父 arch 可能是
Python 生成的（例：20 的 `website.contactus` 页面由 website 代码建，grep 源码找不到）。

不是"逐个 arch 试一下"那种近似：本脚本按 (priority, id) **重放继承**，把父视图连同
其祖先、同级修改合成成一份 arch 再定位 —— `//footer//a[href^=mailto]` 这类锚点的
「祖先元素」和「目标元素」常常来自两个不同的 arch，逐 arch 试必然误报。

**但重放不等于 Odoo**：实测 `tour_website.footer_contact_info`（继承 website.footer_custom）
合成后 `//footer//a[mailto:]` 定位不到（20 的 `div#footer` 直接挂在 `<body>` 下，
不在 `<footer>` 里），真机 `-i` 却装过了 —— 说明 Odoo 的合并 arch 还有本脚本没建模的
环节（qweb `t-call` 展开等）。**所以默认一律记为"待人工确认"，不计失败**；
只有 `--strict` 才把命中数当退出码。真判据始终是空库 `-i`。价值在于一次给出全量候选
（tour_* 77 个锚点），把"装一次只炸一个"的 3–4 分钟/个压缩成一次排序。

用法（第二个参数可以是库名，也可以是事先导出的视图清单文件；arch 含换行，
导出时统一压成单行、用 \\x1f 分隔）：
    python3 check_view_xpaths.py <addons目录> <目标库名|views.tsv> [模块 …]
        [--db-container=odoo20-db --db-user=odoo]      # 只有传库名时用

传库名时脚本走 `docker exec <容器> psql`（容器内 trust 认证，代码里不出现口令）。
等价的纯手工导出命令：
    docker exec odoo20-db psql -U odoo -d <db> -At -F $'\\x1f' -c "<VIEW_SQL>" > /tmp/b0/views.tsv

默认退出码 0（只给清单）；`--strict` 时把「定位不到」计为失败。
父视图不在库里（模块没装）只提示，不算缺陷。

已知局限：
* 只重放常见 position（inside/replace/replace_inner/after/before/attributes/
  invisible/move）；`<field name="x" position="…">` 形态的 spec 不重放（tour_* 未使用）。
* 表达式只翻译 xpath 函数 `hasclass()`（现网只用到它），其它自定义函数会 SKIP。
* 合成 arch 用的是 en_US 单一语言，译文里独有的锚点测不到。
"""
import ast
import json
import os
import re
import subprocess
import sys
import copy

from lxml import etree as letree

HASCLASS_RE = re.compile(r"hasclass\(\s*([^)]*?)\s*\)")
SEP = '\x1f'
VIEW_SQL = """
select coalesce(d.module||'.'||d.name, '#'||v.id::text),
       coalesce(p.module||'.'||p.name, ''),
       v.priority,
       v.id,
       v.active,
       btrim(regexp_replace(coalesce(v.arch_db->>'en_US', v.arch_db #>> '{}', ''),
                            '[[:space:]]+', ' ', 'g'))
  from ir_ui_view v
  left join ir_model_data d on d.model = 'ir.ui.view' and d.res_id = v.id
  left join ir_ui_view iv on iv.id = v.inherit_id
  left join ir_model_data p on p.model = 'ir.ui.view' and p.res_id = iv.id
"""


def _hasclass(m):
    args = [a.strip().strip("'\"") for a in m.group(1).split(',') if a.strip()]
    parts = ["contains(concat(' ', normalize-space(@class), ' '), ' %s ')" % a for a in args]
    return '(' + ' and '.join(parts) + ')'


def parse_arch(text):
    """arch 文本 → lxml 树（包一层根，允许多顶层/片段）。解析不了返回 None。"""
    if not text:
        return None
    try:
        return letree.fromstring(('<root>' + text + '</root>').encode('utf-8'))
    except letree.XMLSyntaxError:
        return None


def specs_of(tree):
    """arch 树里的继承 spec：带 expr + position 的元素。"""
    out = []
    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        if el.get('expr') and el.get('position'):
            out.append(el)
    return out


def apply_spec(target_tree, spec, memo):
    """把一条 spec 施加到 target_tree 上；定位不到就当没发生（真机会报错，
    但本脚本的职责是「报哪条定位不到」，由调用方在合成之前先判过）。"""
    expr = HASCLASS_RE.sub(_hasclass, spec.get('expr'))
    try:
        hits = target_tree.xpath(expr)
    except letree.XPathEvalError:
        return
    pos = spec.get('position')
    kids = [copy.deepcopy(c) for c in spec.iter() if isinstance(c.tag, str)] \
        if pos != 'attributes' else []
    for tgt in hits:
        parent = tgt.getparent()
        if parent is None:
            continue
        idx = parent.index(tgt)
        if pos == 'replace':
            parent.remove(tgt)
            for i, k in enumerate(kids):
                parent.insert(idx + i, k)
        elif pos == 'replace_inner':
            for c in list(tgt):
                tgt.remove(c)
            tgt.text = (spec.text or '').strip() or None
            for k in kids:
                tgt.append(k)
        elif pos == 'inside':
            for k in kids:
                tgt.append(k)
        elif pos == 'after':
            for i, k in enumerate(kids):
                parent.insert(idx + 1 + i, k)
        elif pos == 'before':
            for i, k in enumerate(kids):
                parent.insert(idx + i, k)
        elif pos == 'attributes':
            for a in spec.findall('attribute'):
                if a.get('remove'):
                    tgt.attrib.pop(a.get('name'), None)
                else:
                    tgt.set(a.get('name'), (a.text or '').strip())
        elif pos in ('invisible', 'move'):
            pass                      # 对锚点存在性影响很小，先不重放


def load_views(src, opts):
    """→ ({xid: {parent, priority, id, arch}}, {parent: [(priority, id, xid), …]})"""
    if os.path.exists(src):
        raw = open(src, encoding='utf-8', errors='replace').read()
    else:
        cmd = ['docker', 'exec', opts.get('db_container', 'odoo20-db'),
               'psql', '-U', opts.get('db_user', 'odoo'), '-d', src,
               '-At', '-F', SEP, '-c', VIEW_SQL]
        raw = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    views, rows = {}, []
    for ln in raw.splitlines():
        parts = ln.split(SEP) if SEP in ln else ln.split('\t')
        if len(parts) < 6 or not parts[0]:
            continue
        xid, parent, prio, vid, active = parts[0], parts[1], parts[2], parts[3], parts[4]
        arch = SEP.join(parts[5:])
        if arch.startswith('{'):                       # jsonb 对象且没有 en_US 键
            try:
                vals = [v for v in json.loads(arch).values() if isinstance(v, str)]
                arch = vals[0] if vals else ''
            except json.JSONDecodeError:
                pass
        try:
            prio = int(prio)
        except ValueError:
            prio = 16
        # 停用视图不参与合并：20 的 layout 有 40+ 个页脚/页头变体（只有 1 个 active），
        # 一起重放会把 div#footer 之类替换到错误的节点上 → 假失效。
        on = active in ('t', 'true', 'True', '1')
        views[xid] = {'parent': parent or None, 'prio': prio, 'id': int(vid),
                      'arch': arch, 'on': on}
        if parent and on:
            rows.append((parent, prio, int(vid), xid))
    children = {}
    for parent, prio, vid, xid in rows:
        children.setdefault(parent, []).append((prio, vid, xid))
    return views, children


def combined(views, children, xid, memo, depth=0):
    """xid 视图的**合并后** arch 树：父链合并 → 施加自己的 spec → 施加子视图的 spec。
    （子视图一起算，是为了让「祖先元素来自同级修改」这种真实可定位不算失效；
    代价是忽略了继承顺序，可能把少数「晚于自己生效的同级新增节点」也认下来。）"""
    if xid in memo:
        return memo[xid]
    if depth > 16:
        return None
    info = views.get(xid)
    if not info:
        return None
    own = parse_arch(info['arch'])
    if own is None:
        return None
    base = None
    if info['parent'] and info['parent'] in views:
        parent_tree = combined(views, children, info['parent'], memo, depth + 1)
        if parent_tree is not None:
            base = copy.deepcopy(parent_tree)
            for sp in specs_of(own):
                apply_spec(base, sp, memo)
    if base is None:                       # 主视图 / 父视图缺 arch
        base = own
    for _p, _i, kid in sorted(children.get(xid, [])):
        kid_info = views.get(kid)
        ktree = parse_arch(kid_info['arch']) if kid_info else None
        if ktree is None:
            continue
        for sp in specs_of(ktree):
            apply_spec(base, sp, memo)
    memo[xid] = base
    return base


def find(root_dir, mods):
    """待检记录：(模块, 文件, 行号, 自身 xid, 父 xid, [expr…])。"""
    out = []
    for mod in sorted(mods):
        mpath = os.path.join(root_dir, mod, '__manifest__.py')
        if not os.path.isfile(mpath):
            continue
        try:
            man = ast.literal_eval(open(mpath, encoding='utf-8').read().strip())
        except Exception as e:                                  # noqa: BLE001
            print(f'SKIP {mod}: manifest {e}')
            continue
        for rel in list(man.get('data') or []) + list(man.get('demo') or []):
            if not rel.endswith('.xml'):
                continue
            path = os.path.join(root_dir, mod, rel)
            if not os.path.exists(path):
                continue
            try:
                tree = letree.parse(path)
            except letree.XMLSyntaxError:
                continue
            for el in tree.getroot().iter():
                if not isinstance(el.tag, str):
                    continue
                tag = el.tag.split('}')[-1]
                if tag == 'template':
                    parent, specs = el.get('inherit_id'), el
                elif tag == 'record' and el.get('model') == 'ir.ui.view':
                    parent, specs = None, None
                    for f in el.findall('field'):
                        if f.get('name') == 'inherit_id':
                            parent = f.get('ref')
                        elif f.get('name') == 'arch':
                            specs = f
                    if specs is None:
                        continue
                else:
                    continue
                if not parent or specs is None:
                    continue
                exprs = [c.get('expr') for c in specs.iter()
                         if isinstance(c.tag, str)
                         and c.tag.split('}')[-1] == 'xpath' and c.get('expr')]
                if exprs:
                    out.append((mod, rel, el.sourceline, f"{mod}.{el.get('id')}", parent, exprs))
    return out


def main(argv):
    positional = [a for a in argv if not a.startswith('--')]
    opts = dict(a[2:].split('=', 1) for a in argv if a.startswith('--') and '=' in a)
    if len(positional) < 2:
        print(__doc__)
        return 2
    root_dir, src = positional[1], positional[2]
    only = set(positional[3:])
    mods = [d for d in sorted(os.listdir(root_dir))
            if os.path.isfile(os.path.join(root_dir, d, '__manifest__.py'))
            and (not only or d in only)]
    views, children = load_views(src, opts)
    print(f'视图清单 {src}：{len(views)} 个 arch（{len(children)} 个有子视图）')
    memo = {}

    n_bad = n_skip = 0
    for mod, rel, line, self_xid, parent, exprs in find(root_dir, mods):
        if parent not in views:
            print(f'SKIP [{mod}] {rel}:{line} {self_xid} → 父视图 {parent} 不在库里（模块未安装）')
            n_skip += 1
            continue
        base = combined(views, children, parent, memo)
        if base is None:
            print(f'SKIP [{mod}] {rel}:{line} 父视图 {parent} 的 arch 解析失败')
            n_skip += 1
            continue
        for expr in exprs:
            xpath = HASCLASS_RE.sub(_hasclass, expr)
            try:
                if base.xpath(xpath):
                    continue
            except letree.XPathEvalError as e:
                print(f'SKIP [{mod}] {rel}:{line} 表达式无法静态求值（{e}）：{expr}')
                n_skip += 1
                continue
            print(f'? [{mod}] {rel}:{line}: {self_xid} 的锚点在 {parent} 的合成 arch 里'
                  f'定位不到（待人工确认，多半要改锚）：{expr}')
            n_bad += 1
    print(f'检查 {len(mods)} 模块：{n_bad} 处锚点待确认；{n_skip} 条跳过'
          f'{"（--strict：计入失败）" if "--strict" in opts or "--strict" in argv else ""}')
    return (1 if n_bad else 0) if '--strict' in argv else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
