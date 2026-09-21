# -*- coding: utf-8 -*-
"""用 **20 自己的 domain 引擎** 合并 19 记录规则的域，产出可落 `ir.access.domain` 的字面量。

为什么必须借引擎：20 的扁平 domain 是前缀记法（`'|'` 弹两个操作数），
手写字符串拼接会把 arity 接错 —— 而接错的后果是**静默越权或静默失权**，
不是报错。`odoo.orm.domains.Domain` 是纯 AST 工具，离线可用、不需要 DB：

    Domain(d1) | Domain(d2)   →   list(...)  # 展平回正确 arity 的前缀 list

19 的 domain 里带上下文符号（`user.id` / `company_ids` / `time.strftime(...)`），
`ast.literal_eval` 吃不下，故用 `Tok` 哨兵对象求值：它只保留**结构**并在 `repr()`
时把 token 原样吐回，20 侧真正求值时用的正是同名上下文变量。

必须用 odoo20 的解释器跑：
    PYTHONPATH=/home/adai/odoo20 /home/adai/odoo20/.venv/bin/python classify_rules.py
"""
from odoo.orm.domains import Domain


class Tok:
    """上下文符号哨兵：保留表达式结构，repr 回原 token。"""
    __slots__ = ('t',)

    def __init__(self, t):
        object.__setattr__(self, 't', t)

    def __getattr__(self, k):
        return Tok(f'{self.t}.{k}')

    def __call__(self, *a):
        return Tok(f'{self.t}({", ".join(_lit(x) for x in a)})')

    def __add__(self, o):
        return Tok(f'({_lit(self)} + {_lit(o)})')

    def __radd__(self, o):
        return Tok(f'({_lit(o)} + {_lit(self)})')

    def __repr__(self):
        return self.t


def _lit(v):
    return v if isinstance(v, Tok) else repr(v)


CTX = {n: Tok(n) for n in ('user', 'time', 'company_id', 'company_ids', 'uid', 'obj',
                           'object', 'website', 'context', 'allowed_company_ids')}

# 20 的 ir.access.domain 只有这 4 个符号可求值
# （odoo/addons/base/models/ir_access.py:312 `_eval_context` = user/time/company_ids/company_id）。
# 19 记录规则里出现的其它符号（`website`、`uid`、`object`…）落库后 safe_eval 直接 NameError，
# 属于"20 无等价载体"，必须在 B1 显式改写，不能被工具默默带过去。
CTX_20 = {'user', 'time', 'company_id', 'company_ids'}


def free_names(dom_str):
    """返回 domain 里用到的自由符号名（用于判定是否超出 20 的可求值上下文）。"""
    import ast
    try:
        tree = ast.parse((dom_str or '').strip(), mode='eval')
    except SyntaxError:
        return {'<unparsable>'}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - CTX_20


def parse(dom_str):
    """19 的 domain 字符串 → 20 的 Domain AST。"""
    dom_str = (dom_str or '').strip()
    if not dom_str or dom_str in ('[]', '[(1, \'=\', 1)]', '[(1, "=", 1)]'):
        return Domain.TRUE
    return Domain(eval(dom_str, {'__builtins__': {}}, dict(CTX)))


def merge(dom_list, how='|'):
    """把多条 domain 按 how（'|' 放宽 / '&' 收紧）合成一条；返回可直接写 CSV 的字符串。"""
    parts = [parse(d) for d in dom_list if d]
    parts = [p for p in parts if not p.is_true()] if how == '|' else parts
    if not parts:
        return ''
    acc = parts[0]
    for p in parts[1:]:
        acc = (acc | p) if how == '|' else (acc & p)
    return repr(list(acc))
