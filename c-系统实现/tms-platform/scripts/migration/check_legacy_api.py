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
]


def py_files(mod_dir):
    for dp, dn, fns in os.walk(mod_dir):
        if '__pycache__' in dp or '.git' in dp:
            continue
        for fn in sorted(fns):
            if fn.endswith('.py'):
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

    print('---- 合计（模块 %d 个）----' % len(mods))
    for name in sorted(total):
        print('  %-18s %d' % (name, total[name]))
    if apply_mode:
        print('  已改写文件数：%d' % changed_files)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
