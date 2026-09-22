#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态检查：20 删掉的旧 API 写法，全量列出来（而不是靠装载一次报一个）。

已实测的版本差异（不是猜测）：

    19 AbstractModel has _cr/_uid/_context : True
    20 AbstractModel has _cr/_uid/_context : False

也就是说 `self._cr` 这类写法在 19 现网跑得很好，在 20 会在 **registry 建模阶段**
直接 `AttributeError`（例如空库装 hr_custody 时报
`'report.custody' object has no attribute '_cr'`），连装载数据都到不了。

这些替换在 19 里同样合法（`self.env.cr` 19 就有），所以属于**双兼容改动**：
可以先回落到 19 分支、当天在现网预发验证，不必攒到最后一次性合并。

用法：
    python3 check_legacy_api.py <addons目录> [模块 ...]
    python3 check_legacy_api.py <addons目录> --apply      # 只做零风险的机械替换
"""
import os
import re
import sys

# (名称, 正则, 是否可机械自动替换, 替换)
# 只收录**已实测确认** 19 有 / 20 无 的写法，避免报一堆无害噪音：
#   19 AbstractModel._cr/_uid/_context = True ；20 = False
#   19 api.Self / api.deprecated 存在      ；20 dir(odoo.api) 里没有
#   Registry.get / __getitem__ / digits=tuple / osv / openerp / _pool / _columns
#   —— 19 与 20 一致，**不是**本期风险，已从下表删除（曾经误收过 digits 和 super(Cls,self)）。
PATTERNS = [
    ('self._cr', re.compile(r'\bself\._cr\b'), True, 'self.env.cr'),
    ('self._uid', re.compile(r'\bself\._uid\b'), True, 'self.env.uid'),
    ('self._context', re.compile(r'\bself\._context\b'), True, 'self.env.context'),
    ('X._cr', re.compile(r'(?<!\.)\b(?!self\b)\w+\._cr\b'), False, None),
    ('X._uid', re.compile(r'(?<!\.)\b(?!self\b)\w+\._uid\b'), False, None),
    ('X._context', re.compile(r'(?<!\.)\b(?!self\b)\w+\._context\b'), False, None),
    ('api.Self', re.compile(r'\bapi\.Self\b'), False, None),
    ('api.deprecated', re.compile(r'\bapi\.deprecated\b'), False, None),
    # 20 把 ir.config_parameter 改成带类型读写：get_str/get_bool/get_int/get_float
    # + set_*（`base/models/ir_config_parameter.py:66-131`），get_param/set_param 全删。
    # 不可机械替换：选哪个类型取决于**调用点**语义（值可能是布尔开关也可能是字符串）。
    # 好消息：20 的 value 仍是「字符串化后存 Text」，读时 _convert，所以 19 搬过来的
    # 'True'/'5000.0' 这类值仍能被 get_bool/get_float 正确解释（ETL 不需要改写）。
    ('ir.config_parameter.get_param',
     re.compile(r'\.get_param\('), False, None),
    ('ir.config_parameter.set_param',
     re.compile(r'\.set_param\('), False, None),
    # 20 的 odoo.tools.SQL 去掉 .code/.params，合并成 `_sql_tuple=(code,params,to_flush)`
    # （`tools/sql.py:96`）。19 里 `Query.from_clause`/`where_clause` 返回的就是这个对象。
    ('SQL.code/.params',
     re.compile(r'\b(from_sql|where_sql|from_clause|where_clause)\.(code|params)\b'),
     False, None),
    # 20 换了 read_group / _read_group 的**签名和返回**（两者同形状，只差 m2o 后处理）：
    #   19: read_group(domain, fields, groupby, offset, limit, orderby, lazy) -> list[dict]
    #   20: read_group(domain, groupby, aggregates, having, offset, limit, order) -> list[tuple]
    # 位置参数从第 2 个起就对调，且 20 的 aggregates 必须带聚合函数（`f:sum`，裸名只有 `__count`，
    # `orm/models.py:2086-2103`）。危险在于**多数情况下不报错、只是数错**。
    # 这三条**必须跨行匹配**（真实调用几乎都是 `read_group(\n domain,\n ['f'],\n ['f'])`），
    # 所以不在 PATTERNS 里，见 `_scan_read_group`（按行扫曾在 18 个真实缺陷上报 0，实测踩到）。
]


RG_CALL = re.compile(r'\b_?read_group\(')
RG_19_KWARG = re.compile(r'\b(fields|orderby|lazy)\s*=')
RG_KWARG_HEAD = re.compile(r'^\s*[a-z_]+\s*=')
RG_GB_KWARG = re.compile(r'\bgroupby\s*=\s*(\[[^\]]*\])')
RG_STR = re.compile(r'''['"]([^'"]*)['"]''')
# 19 的 dict 返回值取值：item['x_count'] / item.get('x_count')。末尾 `(?<!:)` 式排除
# 字面量 key（`{'lead_count': …}` 是 portal counter 约定，与 read_group 无关，实测误报过）。
RG_COUNT_KEY = re.compile(r'''(?:\.get\(\s*|\[\s*)['"]([A-Za-z0-9_.]+_count)['"](?!\s*:)''')
RG_BARE_NAME = re.compile(r'^[a-z_][a-z0-9_.]*$')
RG_DEF = re.compile(r'^\s*(?:async\s+)?def\s', re.M)


def _call_args(src, open_idx):
    """从 '(' 之后按括号配平取参数文本，并按顶层逗号切开。

    不处理字符串里的括号/逗号（read_group 的 domain 基本都是字面量，够用）；
    取不平时返回到文件尾，宁可多报也不漏。
    """
    depth, i = 1, open_idx
    while i < len(src):
        c = src[i]
        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
            if depth == 0:
                break
        i += 1
    text = src[open_idx:i]
    parts, depth, buf = [], 0, []
    for c in text:
        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        if c == ',' and depth == 0:
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(c)
    parts.append(''.join(buf))
    return text, parts


def _bad_aggregates(part):
    """aggregates 位上出现的「裸字段名」——20 会 ValueError，19 是合法 fields/groupby。"""
    out = []
    for m in RG_STR.finditer(part):
        spec = m.group(1)
        if spec in ('', '*', '__count') or ':' in spec:
            continue
        if RG_BARE_NAME.match(spec):
            out.append(spec)
    return out


def _spec_names(part):
    """groupby 参数文本 → 字段名集合（`'x:month'` 取 `x`）。"""
    out = set()
    for m in RG_STR.finditer(part):
        spec = m.group(1).split(':', 1)[0].strip()
        if RG_BARE_NAME.match(spec):
            out.add(spec)
    return out


def _for_targets(text):
    """`for a, b in var:` → [a, b]。"""
    names = []
    for part in re.split(r'[,\s]+', text.strip()):
        if re.fullmatch(r'[A-Za-z_]\w*', part or ''):
            names.append(part)
    return names


def _result_names(src, call_start):
    """read_group 结果被绑到的变量名（含随后的 for 元素名）。

    19 返回 list[dict]、20 返回 list[tuple]，所以"拿结果按字符串 key 取值"这种写法
    在 20 必炸（`TypeError: tuple indices must be integers`）。只认两种绑定：
    `var = Expr.read_group(` 和 `for x in Expr.read_group(`，够覆盖实测见到的形态。
    """
    head = src[max(0, call_start - 160):call_start]
    names = set()
    m = re.search(r'''(\w+)\s*=\s*[\w.\[\]"']*$''', head)
    if m:
        names.add(m.group(1))
    else:
        m = re.search(r'''for\s+([^\n:]+?)\s+in\s*[\w.\[\]"']*$''', head)
        if m:
            names.update(_for_targets(m.group(1)))
        else:
            return names
    var = next(iter(names))
    tail = src[call_start:call_start + 3000]
    fm = re.search(r'for\s+([^\n:]+?)\s+in\s+%s\s*:' % re.escape(var), tail)
    if fm:
        names.update(_for_targets(fm.group(1)))
    return names


def _dict_access_hits(src, names, after, before):
    """[(行号, 片段)]：对 read_group 结果做字符串 key 取值 = 19 的 dict 形状。

    只在**该调用所在函数体内**扫：变量名（`item` 之类）在别的函数里会被复用，
    全文件扫会炸出上百条误报（实测 165 条）。
    """
    out = []
    for name in names:
        rx = re.compile(r'''\b%s\b\s*(?:\[\s*\d+\s*\])?\s*(?:\[\s*|\.get\(\s*)(["'][A-Za-z0-9_.:]*["'])'''
                        % re.escape(name))
        for m in rx.finditer(src, after, before):
            out.append((src.count('\n', 0, m.start()) + 1,
                        m.group(0).strip()))
    return out


def _line_start(src, line):
    """第 line 行（1-based）的字符下标；越界返回文件尾。"""
    off = 0
    try:
        for _ in range(line - 1):
            off = src.index('\n', off) + 1
    except ValueError:
        return len(src)
    return off


def _body_bounds(src, defs, line):
    """函数体行区间 [start, end)：start = 所在 def 行，end = 下一个 def 行。"""
    starts = [d for d in defs if d <= line]
    if not starts:
        return None
    nxt = [d for d in defs if d > line]
    return starts[-1], nxt[0] if nxt else float('inf')


def _scan_read_group(src):
    """返回 [(行号, 规则名, 片段说明)]，只报已实测确认的 19 写法（4 条规则）。

    取值规则只认 **`<groupby 字段>_count`** 这一种 key（19 只对分组字段生成它），并且
    只在含 read_group 调用的那个函数体内生效：全文件扫会把 portal 的
    `_prepare_home_portal_values` 计数器（`values['xxx_count']`）误报进来（实测踩到）；
    只按 `_count` 后缀扫又会把我们自己构造的 `{'guest_count': …}` 误报进来。
    """
    hits = []
    calls = []   # (行号, groupby 字段名集合)
    defs = [src.count('\n', 0, m.start()) + 1 for m in RG_DEF.finditer(src)]
    for m in RG_CALL.finditer(src):
        line = src.count('\n', 0, m.start()) + 1
        text, parts = _call_args(src, m.end())
        kw = RG_19_KWARG.search(text)
        if kw:
            hits.append((line, 'read_group(19 kwarg)',
                         '%s= 在 20 已不存在 → TypeError' % kw.group(1)))
            calls.append((line, set()))
            continue
        positional = [p for p in parts if not RG_KWARG_HEAD.match(p)]
        if len(positional) >= 3:
            bare = _bad_aggregates(positional[2])
            if bare:
                hits.append((line, 'read_group(19 位置参数)',
                             "aggregates 位是裸字段 %s：20 报 Aggregate method is mandatory"
                             % ','.join(repr(b) for b in bare)))
        gb = _spec_names(positional[1]) if len(positional) >= 2 else set()
        kb = RG_GB_KWARG.search(text)
        if kb:
            gb |= _spec_names(kb.group(1))
        calls.append((line, gb))
        bounds = _body_bounds(src, defs, line)
        if bounds:
            end = bounds[1]
            end_off = len(src) if end == float('inf') else _line_start(src, end)
            names = _result_names(src, m.start())
            for ln, snip in _dict_access_hits(src, names, m.end(), end_off):
                hits.append((ln, 'read_group(19 dict 取值)',
                             snip + '… → 20 返回 tuple，字符串 key 必 TypeError'))
    if not any(gb for _l, gb in calls):
        return sorted(set(hits))

    for m in RG_COUNT_KEY.finditer(src):
        line = src.count('\n', 0, m.start()) + 1
        bounds = _body_bounds(src, defs, line)
        if not bounds:
            continue
        start, end = bounds
        base = m.group(1)[:-len('_count')]
        if any(start <= c < end and base in gb for c, gb in calls):
            hits.append((line, 'read_group(19 取值)', m.group(0).strip() + ' → 20 无此 key'))
    return sorted(set(hits))



def py_files(mod_dir):
    for dp, dn, fns in os.walk(mod_dir):
        if '__pycache__' in dp or '.git' in dp:
            continue
        for fn in sorted(fns):
            if fn.endswith('.py'):
                yield os.path.join(dp, fn)


# 服务端 QWeb：**20 删掉了 `t-esc` / `t-raw` 两个指令**。19 里有
# `_compile_directive_esc`/`_compile_directive_raw`（19 `ir_qweb.py:2487 / 2497`），
# 20 的 `ir_qweb.py` 全文只剩 `:2015` 一处读 `el.get('t-esc')` 的判断，指令分发是
# `getattr(self, "_compile_directive_%s" % ...)`（20 `:1924`）—— 取不到处理器**不报错**，
# 只在 `:2031` 打一条 "Unknown directives or unused attributes" 警告，然后
# **内容静默不渲染**。所以这是第二类"不报错、只是数错/缺东西"的变更（第一类见 read_group）。
#
# OWL 的 JS 模板编译器仍然支持 t-esc（20 core 里剩下的 3 处 t-esc 全在 `static/src/**.xml`），
# 所以扫描必须排除 `static/`，否则会把前端模板一起改错。
#
# `t-esc` → `t-out` 是**等价替换**（两者都转义）；`t-raw` 不是（`t-out` 只在值是
# Markup 时不转义），所以只有 `t-raw="0"` 这个"填空槽位"惯用法可以机械替换。
QWEB_XML_PATTERNS = [
    ('qweb t-esc(19)', re.compile(r'\bt-esc\s*='), True, 't-out='),
    ('qweb t-raw=0(19)', re.compile(r'\bt-raw="0"'), True, 't-out="0"'),
    ('qweb t-raw(19)', re.compile(r'\bt-raw\s*=(?!\s*"0")'), False, None),
]


def xml_files(mod_dir):
    for dp, dn, fns in os.walk(mod_dir):
        if '__pycache__' in dp or '.git' in dp or 'static' in dp.split(os.sep):
            continue
        for fn in sorted(fns):
            if fn.endswith('.xml'):
                yield os.path.join(dp, fn)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    addons = argv[1]
    apply_mode = '--apply' in argv
    only = {a for a in argv[2:] if not a.startswith('--')}

    mods = sorted(d for d in os.listdir(addons)
                  if os.path.isfile(os.path.join(addons, d, '__manifest__.py'))
                  and (not only or d in only))

    total = {}
    changed_files = 0
    for mod in mods:
        for path in py_files(os.path.join(addons, mod)):
            src = open(path, encoding='utf-8').read()
            lines = src.splitlines(True)
            hits = []
            for i, line in enumerate(lines, 1):
                code = line.split('#', 1)[0]
                for name, rx, auto, repl in PATTERNS:
                    if rx.search(code):
                        hits.append((i, name, line.rstrip()))
                        if name in ('other._cr',) and 'self._cr' in code:
                            pass
            hits += _scan_read_group(src)
            hits.sort()
            if not hits:
                continue
            for _, name, _l in hits:
                total[name] = total.get(name, 0) + 1
            print('%s/%s' % (mod, os.path.relpath(path, os.path.join(addons, mod))))
            for i, name, line in hits:
                print('    %4d  %-18s %s' % (i, name, line.strip()[:110]))
            if apply_mode:
                new = src
                for name, rx, auto, repl in PATTERNS:
                    if auto:
                        new = rx.sub(repl, new)
                if new != src:
                    open(path, 'w', encoding='utf-8').write(new)
                    changed_files += 1

        # 服务端模板（.xml）：只有 QWeb 指令这一类规则，不涉及 read_group。
        for path in xml_files(os.path.join(addons, mod)):
            src = open(path, encoding='utf-8').read()
            hits = [(i, name, line.rstrip())
                    for i, line in enumerate(src.splitlines(True), 1)
                    for name, rx, auto, repl in QWEB_XML_PATTERNS if rx.search(line)]
            if not hits:
                continue
            for _, name, _l in hits:
                total[name] = total.get(name, 0) + 1
            print('%s/%s' % (mod, os.path.relpath(path, os.path.join(addons, mod))))
            for i, name, line in hits:
                print('    %4d  %-18s %s' % (i, name, line.strip()[:110]))
            if apply_mode:
                new = src
                for name, rx, auto, repl in QWEB_XML_PATTERNS:
                    if auto:
                        new = rx.sub(repl, new)
                if new != src:
                    open(path, 'w', encoding='utf-8').write(new)
                    changed_files += 1

    print('---- 合计（模块 %d 个）----' % len(mods))
    for name in sorted(total):
        print('  %-18s %d' % (name, total[name]))
    if apply_mode:
        print('  已改写文件数：%d' % changed_files)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
