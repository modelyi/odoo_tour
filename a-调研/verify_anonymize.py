#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 team_orders.csv guidelist JSON 脱敏前后明文敏感值泄露情况。"""
import csv
import json
import re

ID_RE = re.compile(r"\d{17}[\dXx]")            # 18位身份证（含 X 校验位）
MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")  # 11位手机
BANK_RE = re.compile(r"\d{16,19}")             # 银行卡 16-19 位


def scan_guidelist(path):
    """遍历 guidelist JSON 所有值，统计明文敏感值。返回统计 dict。"""
    stats = {
        "rows": 0,
        "json_ok": 0,
        "json_err": 0,
        "idnum_plaintext": 0,
        "mobile_plaintext": 0,
        "bank_plaintext": 0,
        "sample_id": None,
        "sample_mobile": None,
        "sample_bank": None,
    }
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["rows"] += 1
            gl = row.get("guidelist", "")
            if not gl or not gl.strip():
                continue
            try:
                obj = json.loads(gl)
            except Exception:
                stats["json_err"] += 1
                continue
            stats["json_ok"] += 1

            def walk(x):
                if isinstance(x, dict):
                    for v in x.values():
                        walk(v)
                elif isinstance(x, list):
                    for v in x:
                        walk(v)
                elif isinstance(x, str):
                    for m in ID_RE.finditer(x):
                        stats["idnum_plaintext"] += 1
                        if stats["sample_id"] is None:
                            stats["sample_id"] = m.group(0)
                    for m in MOBILE_RE.finditer(x):
                        stats["mobile_plaintext"] += 1
                        if stats["sample_mobile"] is None:
                            stats["sample_mobile"] = m.group(0)
                    for m in BANK_RE.finditer(x):
                        stats["bank_plaintext"] += 1
                        if stats["sample_bank"] is None:
                            stats["sample_bank"] = m.group(0)
            walk(obj)
    return stats


def check_top_level_guides():
    """检查 guides.csv 顶层敏感字段是否仍脱敏。"""
    results = {}
    for fname in ("guides.csv",):
        path = f"et_data_demo/{fname}"
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            leaks = {"IDNum": 0, "Mobile": 0, "Tel": 0}
            sample = {}
            for row in reader:
                for k in ("IDNum", "Mobile", "Tel"):
                    v = (row.get(k) or "").strip()
                    if v:
                        if k == "IDNum" and ID_RE.search(v):
                            leaks[k] += 1
                            sample.setdefault(k, v)
                        elif k in ("Mobile", "Tel") and MOBILE_RE.search(v):
                            leaks[k] += 1
                            sample.setdefault(k, v)
            results[fname] = (leaks, sample)
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("guidelist JSON 脱敏前后明文泄露对比")
    print("=" * 70)
    src = scan_guidelist("et_data/team_orders.csv")
    dst = scan_guidelist("et_data_demo/team_orders.csv")
    for label, s in (("源(明文)", src), ("目标(脱敏后)", dst)):
        print(f"\n[{label}]")
        print(f"  记录行数       : {s['rows']}")
        print(f"  含 guidelist JSON: {s['json_ok']}  (解析失败 {s['json_err']})")
        print(f"  明文身份证 18位 : {s['idnum_plaintext']}  (样例: {s['sample_id']})")
        print(f"  明文手机 11位   : {s['mobile_plaintext']}  (样例: {s['sample_mobile']})")
        print(f"  明文银行卡 16-19位: {s['bank_plaintext']}  (样例: {s['sample_bank']})")

    print("\n" + "=" * 70)
    print("guides.csv 顶层敏感字段（脱敏后）残留明文检查")
    print("=" * 70)
    for fname, (leaks, sample) in check_top_level_guides().items():
        print(f"\n[{fname}]")
        for k, n in leaks.items():
            print(f"  {k}: 明文残留 {n}  (样例: {sample.get(k)})")
