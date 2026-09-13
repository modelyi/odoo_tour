#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TMS 调研数据脱敏脚本
====================
将 et_data/ 下的易途系统调研数据脱敏，输出到 et_data_demo/。

脱敏原则：保留结构（打码），可逆性低但保留业务特征
- 手机号：13697512314 → 136****2314（保留前3后4）
- 身份证：132440197602271023 → 132440********1023（保留前6后4）
- 银行卡：保留后4位，前面打 ****
- 姓名：替换为「姓氏 + 通用后缀」（如 刘虎 → 刘导）
- 生日：统一模糊到 1月1日，保留年份
- 地址：只保留省/市，详细地址打码
- 邮箱：保留 @ 和域名，用户名打码

用法：
    python3 anonymize_data.py [样本数]   # 样本数为 0 或省略 = 全量
"""

import csv
import json
import os
import re
import sys

SRC = os.path.join(os.path.dirname(__file__), "et_data")
DST = os.path.join(os.path.dirname(__file__), "et_data_demo")

# 样本数（0 = 全量）
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 0

# ── 敏感字段 → 脱敏函数 ──────────────────────────────

def mask_mobile(v):
    """手机/电话：保留前3后4"""
    v = str(v).strip()
    if not v:
        return v
    digits = re.sub(r"\D", "", v)
    if len(digits) >= 7:
        return digits[:3] + "****" + digits[-4:]
    return "***" + digits[-4:] if len(digits) >= 4 else "****"

def mask_idnum(v):
    """身份证：保留前6后4"""
    v = str(v).strip()
    if not v:
        return v
    digits = re.sub(r"\D", "", v)
    if len(digits) >= 14:
        return digits[:6] + "*" * (len(digits) - 10) + digits[-4:]
    return "****"

def mask_bank(v):
    """银行卡：保留后4位"""
    v = str(v).strip()
    if not v:
        return v
    digits = re.sub(r"\D", "", v)
    if len(digits) >= 4:
        return "****" + digits[-4:]
    return "****"

def mask_name(v):
    """姓名：保留姓氏，名打码"""
    v = str(v).strip()
    if not v:
        return v
    if len(v) >= 2:
        return v[0] + "**"
    return v + "*"

def mask_birthday(v):
    """生日：保留年份，月日统一 01-01"""
    v = str(v).strip()
    if not v:
        return v
    m = re.match(r"(\d{4})", v)
    if m:
        return m.group(1) + "-01-01"
    return "****-01-01"

def mask_addr(v):
    """地址：只保留前6字符（大致到区县），其余打码"""
    v = str(v).strip()
    if not v:
        return v
    if len(v) > 6:
        return v[:6] + "****"
    return v

def mask_email(v):
    """邮箱：保留 @域名，用户名打码"""
    v = str(v).strip()
    if not v or "@" not in v:
        return v
    name, domain = v.split("@", 1)
    return "***@" + domain

def mask_pwd(v):
    """密码/哈希：彻底替换"""
    v = str(v).strip()
    return "****" if v else v

def mask_account(v):
    """登录账号：打码"""
    v = str(v).strip()
    if not v:
        return v
    if len(v) >= 4:
        return v[:2] + "***" + v[-1:]
    return "***"

# 字段名 → 脱敏函数 的映射（按字段名模式匹配）
FIELD_RULES = [
    # (正则模式, 函数)
    (r"(?i)mobile", mask_mobile),
    (r"(?i)tel", mask_mobile),
    (r"(?i)phone", mask_mobile),
    (r"(?i)idnum", mask_idnum),
    (r"(?i)idcode", mask_idnum),
    (r"(?i)accountno", mask_bank),
    (r"(?i)bankaccount", mask_bank),
    (r"(?i)accountbank", mask_bank),   # 开户行（AccountBank）
    (r"(?i)birthday", mask_birthday),
    (r"(?i)email", mask_email),
    (r"(?i)addr", mask_addr),
    (r"(?i)pwd", mask_pwd),              # 密码/哈希
    (r"(?i)weixin", mask_account),       # 微信号
    (r"(?i)manager$", mask_name),          # CmpManager, GuideManager
    (r"(?i)accountname", mask_name),
    (r"(?i)guidename", mask_name),
    (r"(?i)opusername", mask_name),      # 操作员姓名
    (r"(?i)inusername", mask_name),      # 输入人姓名
    (r"(?i)username", mask_name),        # 用户名
    (r"(?i)salesname", mask_name),       # 销售姓名
    (r"(?i)guideaccount", mask_account), # 导游账号
    (r"(?i)useraccount", mask_account),  # 用户账号
]

def rule_for(field):
    for pat, fn in _COMPILED:
        if pat.search(field):
            return fn
    return None


# 预编译规则，避免每次 re.search 重新解析（大文件性能关键）
_COMPILED = [(re.compile(pat), fn) for pat, fn in FIELD_RULES]


# ── JSON 嵌套字段脱敏 ──────────────────────────────
# CSV 单元格值若是 JSON 字符串（list/dict/对象数组），递归遍历所有 key，
# 用同一套 FIELD_RULES 匹配 key 名做脱敏，保留 JSON 结构。

def mask_json_value(v):
    """若 v 是可解析的 JSON 容器（list/dict），递归脱敏并重新序列化。

    返回 (结果, 是否发生变化)。非 JSON 字符串原样返回。
    """
    if not isinstance(v, str):
        return v, False
    s = v.strip()
    if len(s) < 2 or s[0] not in "[{" or s[-1] not in "]}":
        return v, False
    try:
        obj = json.loads(s)
    except (ValueError, TypeError):
        return v, False
    if not isinstance(obj, (dict, list)):
        return v, False  # JSON 标量（数字/布尔/null 等）不处理
    masked, changed = _recurse_mask(obj)
    if not changed:
        return v, False  # 内部无敏感 key，保留原始字节
    return json.dumps(masked, ensure_ascii=False), True


def _recurse_mask(obj):
    """递归遍历 dict/list，对敏感 key 的值脱敏。返回 (新对象, 是否变化)。"""
    if isinstance(obj, dict):
        changed = False
        new = {}
        for k, val in obj.items():
            nv, c = _mask_field(k, val)
            new[k] = nv
            changed = changed or c
        return new, changed
    if isinstance(obj, list):
        changed = False
        new = []
        for val in obj:
            nv, c = _recurse_mask(val)
            new.append(nv)
            changed = changed or c
        return new, changed
    return obj, False


def _mask_field(key, value):
    """对单个 JSON 字段（key→value）脱敏：key 命中规则→按规则打码；
    否则若 value 是嵌套 dict/list 或 JSON 字符串→继续递归；
    否则对字符串值做「内嵌明文 PII」兜底打码（ReceiveTag/Brief 等自由文本）。"""
    if value is None:
        return value, False
    fn = rule_for(key)
    if fn is not None:
        nv = fn(value) if isinstance(value, str) else fn(str(value))
        return nv, (nv != value)
    if isinstance(value, dict):
        return _recurse_mask(value)
    if isinstance(value, list):
        return _recurse_mask(value)
    if isinstance(value, str):
        nv, c = mask_json_value(value)  # 嵌套 JSON
        if c:
            return nv, True
        nv2 = mask_embedded_pii(value)  # 值内嵌明文 PII 兜底
        return nv2, (nv2 != value)
    return value, False


# ── 值级内嵌 PII 兜底 ──────────────────────────────
# 某些 key 名不命中敏感规则，但值里拼接了明文身份证/手机/银行卡
# （如 ReceiveTag="夏海苹15995701621"、DownBrief 含身份证+手机）。
# 对这类自由文本做就地正则打码，保证 guidelist 内无明文敏感数字。

_EMBED_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")       # 18位身份证(含X)
_EMBED_MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")    # 11位手机
_EMBED_BANK = re.compile(r"(?<!\d)\d{16,19}(?!\d)")        # 银行卡16-19位


def mask_embedded_pii(v):
    """就地打码字符串值内嵌的明文身份证/手机/银行卡，返回新字符串。"""
    v = str(v)
    if not v:
        return v
    v = _EMBED_ID.sub(lambda m: mask_idnum(m.group(0)), v)
    v = _EMBED_MOBILE.sub(lambda m: mask_mobile(m.group(0)), v)
    v = _EMBED_BANK.sub(lambda m: mask_bank(m.group(0)), v)
    return v


def anonymize_file(src_path, dst_path):
    with open(src_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        # 确定每个字段的脱敏函数
        col_fn = {fld: rule_for(fld) for fld in fields if rule_for(fld)}
        with open(dst_path, "w", encoding="utf-8", newline="") as g:
            writer = csv.DictWriter(g, fieldnames=fields)
            writer.writeheader()
            n = 0
            for row in reader:
                if SAMPLE > 0 and n >= SAMPLE:
                    break
                for fld in row:
                    v = row.get(fld)
                    if not v:
                        continue
                    fn = col_fn.get(fld)
                    if fn is not None:
                        row[fld] = fn(v)
                    else:
                        masked, changed = mask_json_value(v)
                        if changed:
                            row[fld] = masked
                writer.writerow(row)
                n += 1

    return n, len(col_fn)


def main():
    os.makedirs(DST, exist_ok=True)
    files = sorted(f for f in os.listdir(SRC) if f.endswith(".csv"))
    total_rows = 0
    total_masked = 0
    print(f"脱敏模式：{'样本 ' + str(SAMPLE) + ' 条' if SAMPLE else '全量'}")
    print(f"源目录：{SRC}")
    print(f"目标目录：{DST}\n")
    print(f"{'文件':<28} {'记录数':>8} {'脱敏列数':>8}")
    print("-" * 50)
    for fn in files:
        n, m = anonymize_file(os.path.join(SRC, fn), os.path.join(DST, fn))
        total_rows += n
        total_masked += m
        print(f"{fn:<28} {n:>8} {m:>8}")
    print("-" * 50)
    print(f"{'合计':<28} {total_rows:>8} {total_masked:>8} 列")


if __name__ == "__main__":
    main()
