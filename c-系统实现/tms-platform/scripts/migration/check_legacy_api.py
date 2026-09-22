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
    # 20 删掉了 `request.website`（19 由 website/models/ir_http.py:265 赋在 Request 上），
    # 改由 Environment 提供同名属性（20 `odoo/orm/environments.py:303`）→ 写法是
    # `request.env.website`。**这条是 20-only，不能回落到 19**（实测 19 的 Environment
    # 没有 website 属性）。装载与 GET 冒烟都看不见，只有真正走到那行的请求会 500。
    ('request.website(20 已删)',
     re.compile(r'\brequest\.website\b'), False, None),
    # portal 的 `pager()`（真名 `odoo.addons.portal.controllers.portal.pager`）返回字典
    # **两版都没有 `limit` 键**（实测 19/20 的返回体只有 page_count / offset / page /
    # page_first / page_previous / page_next / page_last）。`pager['limit']` 不是 19→20
    # 变更，是 19 现网潜伏缺陷（`KeyError: 'limit'` 直接 500）；页长本来就是调用方自己
    # 传进去的 `step=`，所以正确写法是用那个常量，不是从返回值里取。
    ('portal pager 无 limit 键(19/20 同)',
     re.compile(r'''\bpager\[\s*['"]limit['"]\s*\]'''), False, None),
    # 20 换了 read_group / _read_group 的**签名和返回**（两者同形状，只差 m2o 后处理）：
    #   19: read_group(domain, fields, groupby, offset, limit, orderby, lazy) -> list[dict]
    #   20: read_group(domain, groupby, aggregates, having, offset, limit, order) -> list[tuple]
    # 位置参数从第 2 个起就对调，且 20 的 aggregates 必须带聚合函数（`f:sum`，裸名只有 `__count`，
    # `orm/models.py:2086-2103`）。危险在于**多数情况下不报错、只是数错**。
    # 这几条**必须跨行匹配**（真实调用几乎都是 `read_group(\n domain,\n ['f'],\n ['f'])`），
    # 所以不在上表里，见 `_scan_read_group`（按行扫曾在 18 个真实缺陷上报 0，实测踩到）。
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


# 20 把 `odoo/http.py`（单文件，19 里 131 个公开名）拆成包 `odoo/http/`，
# `__init__.py` 只有 21 行，**不再重新导出**绝大多数旧名字。实测 20 运行时
# `odoo.http` 上可用的属性就是下面这些（`dir(odoo.http)` 去掉 dunder）：
#   Controller / Response / request / route            ← 唯一的四个"旧公开 API"
#   dispatcher / geoip / requestlib / response / retrying / router /
#   routing_map / server / server_log / session / stream  ← 子模块
# 其余一律 `ImportError` 或 `AttributeError`，例如 19 的
# `from odoo.http import content_disposition`、`http.serialize_exception(...)`
# 在 20 必须改成 `from odoo.http.stream import ...` /
# `from odoo.http.dispatcher import serialize_exception`（上游 20 自己就这么写，
# 见 `addons/web/controllers/report.py:10`）。
# 这类改法**只能在 20 分支做，不能回落到 19**（19 没有 odoo.http.dispatcher）。
HTTP20_OK = {
    'Controller', 'Response', 'request', 'route',
    'dispatcher', 'geoip', 'requestlib', 'response', 'retrying', 'router',
    'routing_map', 'server', 'server_log', 'session', 'stream',
}
HTTP_ATTR = re.compile(r'\bhttp\.([A-Za-z_][A-Za-z0-9_]*)')
HTTP_IMPORT = re.compile(r'\bfrom\s+odoo\.http\s+import\s+([^\n#]+)')


def _scan_http(src):
    hits = []
    for line_no, line in enumerate(src.splitlines(), 1):
        code = line.split('#', 1)[0]
        m = HTTP_IMPORT.search(code)
        if m:
            for nm in m.group(1).replace('(', '').replace(')', '').split(','):
                nm = nm.strip().split(' as ')[0].strip()
                if nm and nm not in HTTP20_OK:
                    hits.append((line_no, 'odoo.http 导出变更(19)',
                                 'from odoo.http import %s → 20 需改子模块路径' % nm))
        for attr in HTTP_ATTR.findall(code):
            if attr in HTTP20_OK:
                continue
            hits.append((line_no, 'odoo.http 导出变更(19)',
                         'http.%s → 20 的 odoo.http 不再导出该名字' % attr))
    return hits


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
# 下面三条**不是 19→20 变更**，而是"19 现网同样会炸、只是没人访问到"的潜伏缺陷：
# 两条规则都经实测在 19 与 20 的 `ir_qweb.py` 里字节级等价（19 `:2532/:2550`、
# 20 `:2640/:2658`），所以放在这里一起扫，好处是**同一份补丁两版都能回落**。
#
#   * `<div t-call="…">` —— 两版都 `raise SyntaxError("t-call must be on a <t> element")`。
#     正则要求 `<tag` 与 `t-call=` 之间不出现引号，避免把
#     `<xpath expr="//t[@t-call='…']"` 这种继承定位误报成违规。
#   * `context_today()` 出现在 **`t-att-*` 表达式**里 —— 服务端 QWeb 的渲染上下文
#     （19 `ir_qweb.py:1303-1327` / 20 `:1373-1397`）两版都**不注入** `context_today`，
#     运行时 `KeyError`。而后端表单视图的 `domain="[('x','=',context_today()…)]"`
#     走的是客户端 `expression_eval_context`（`tools/view_validation.py:27` 白名单里有），
#     合法。所以只用 `t-att-` 前缀做判据。
QWEB_XML_PATTERNS = [
    ('qweb t-esc(19)', re.compile(r'\bt-esc\s*='), True, 't-out='),
    ('qweb t-raw=0(19)', re.compile(r'\bt-raw="0"'), True, 't-out="0"'),
    ('qweb t-raw(19)', re.compile(r'\bt-raw\s*=(?!\s*"0")'), False, None),
    ('qweb t-call 非 <t> 元素(19/20 同)',
     re.compile(r'<(?!(?:t|t:)[\s/>])[\w.:_-]+(?:\s+[^<>"\']*)?\bt-call\s*='), False, None),
    ('qweb t-att 里 context_today(19/20 同)',
     re.compile(r'\bt-att-[\w.:_-]+\s*=\s*"[^"]*\bcontext_today\s*\('), False, None),
]


def xml_files(mod_dir):
    for dp, dn, fns in os.walk(mod_dir):
        if '__pycache__' in dp or '.git' in dp or 'static' in dp.split(os.sep):
            continue
        for fn in sorted(fns):
            if fn.endswith('.xml'):
                yield os.path.join(dp, fn)


# 前端 JS（`static/src/**/*.js`）：20 **整层删掉了 `web.public.widget`**，实测
# `addons/web/static/src/` 全树已无 `public.widget`（19 还留着 legacy 层）。
# 后果和 `t-esc` 那类一样是"不报错、只是不工作"，但更隐蔽：
# Python 装载期不 import JS，页面 HTTP 状态码也照样 200，**只有浏览器控制台看得见**，
# 所以装载全绿 + 冒烟 0 个 500 都不能证明前端没坏 —— 必须单独静态扫。
# `odoo.define(...)` 是旧的 AMD 包装，20 全面改成 ES module（`import`/`export`）。
# 移植说明本身会提到这些旧名字，所以扫描前先剥掉 `//` 行注释（`://` 里的斜杠不算注释；
# 块注释 `/* */` 未处理 —— 别把命中写在块注释里）。
JS_PATTERNS = [
    ('js web.public.widget(20 已删)',
     re.compile(r"""['"]web\.public\.widget['"]|\bpublicWidget\b"""), False, None),
    ('js odoo.define AMD 包装(20 已改 ES module)',
     re.compile(r'\bodoo\.define\('), False, None),
    ('js 旧 jQuery 插件式 $.fn',
     re.compile(r'\bjQuery\.fn\.|\$\.fn\.'), False, None),
]


JS_LINE_COMMENT = re.compile(r'(?<!:)//.*')


def js_files(mod_dir):
    for dp, dn, fns in os.walk(mod_dir):
        if '__pycache__' in dp or '.git' in dp or os.sep + 'tests' in dp:
            continue
        if 'static' + os.sep not in dp + os.sep:
            continue
        for fn in sorted(fns):
            if fn.endswith('.js'):
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
            hits += _scan_http(src)
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

        # 前端 JS（static/src/**/*.js）：装载与 HTTP 冒烟都看不见这一类，只能静态扫。
        # 三条规则都不是零风险机械替换（改法取决于组件怎么写），所以 --apply 不动 JS。
        for path in js_files(os.path.join(addons, mod)):
            src = open(path, encoding='utf-8').read()
            hits = [(i, name, line.rstrip())
                    for i, line in enumerate(src.splitlines(True), 1)
                    for name, rx, auto, repl in JS_PATTERNS
                    if rx.search(JS_LINE_COMMENT.sub('', line))]
            if not hits:
                continue
            for _, name, _l in hits:
                total[name] = total.get(name, 0) + 1
            print('%s/%s' % (mod, os.path.relpath(path, os.path.join(addons, mod))))
            for i, name, line in hits:
                print('    %4d  %-18s %s' % (i, name, line.strip()[:110]))

    print('---- 合计（模块 %d 个）----' % len(mods))
    for name in sorted(total):
        print('  %-18s %d' % (name, total[name]))
    if apply_mode:
        print('  已改写文件数：%d' % changed_files)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
