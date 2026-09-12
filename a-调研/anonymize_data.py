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
    for pat, fn in FIELD_RULES:
        if re.search(pat, field):
            return fn
    return None


def anonymize_file(src_path, dst_path):
    with open(src_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    if SAMPLE > 0:
        rows = rows[:SAMPLE]

    # 确定每个字段的脱敏函数
    col_fn = {}
    for fld in fields:
        fn = rule_for(fld)
        if fn:
            col_fn[fld] = fn

    with open(dst_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for fld, fn in col_fn.items():
                if fld in row and row[fld]:
                    row[fld] = fn(row[fld])
            writer.writerow(row)

    return len(rows), len(col_fn)


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
