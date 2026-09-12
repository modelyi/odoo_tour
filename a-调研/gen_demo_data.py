#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TMS demo 数据生成脚本
=====================
从脱敏后的 et_data_demo/ 生成 Odoo demo XML，输出到 tour_base/demo/ 目录。

映射关系：
  line_types.csv  → tour.line.type   (线路分类)
  pay_ways.csv    → tour.pay.way     (结算方式)
  items_57.csv    → tour.biz.type    (业务类型)
  items_2/3/5/11  → tour.base.item   (通用基础数据)
  line_products   → tour.line        (线路产品，样本)

用法：
    python3 gen_demo_data.py
"""

import csv
import os
import re
import html

SRC = os.path.join(os.path.dirname(__file__), "et_data_demo")
DST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "c-系统实现", "tms-platform", "addons", "tour_base", "demo",
)

# 样本数（0 = 全量）
SAMPLE_LINE = 30   # 线路产品取 30 条样本
SAMPLE_OTHER = 0   # 基础数据全量


def read_csv(name):
    path = os.path.join(SRC, name)
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def esc(v):
    return html.escape(str(v or ""), quote=True)


def xml_records(xml_id_prefix, rows, field_map, sample=0):
    """生成 <record> 节点列表"""
    out = []
    if sample > 0:
        rows = rows[:sample]
    for i, r in enumerate(rows):
        fields = ""
        for src, dst in field_map.items():
            val = esc(r.get(src, ""))
            if val:
                fields += f'\n            <field name="{dst}">{val}</field>'
        out.append(
            f'    <record id="{xml_id_prefix}_{i+1}" model="{field_map["__model__"]}">'
            f'{fields}\n    </record>'
        )
    return out


def main():
    os.makedirs(DST, exist_ok=True)
    parts = []
    parts.append('<?xml version="1.0" encoding="utf-8"?>')
    parts.append('<odoo>')
    parts.append('    <!-- 由 gen_demo_data.py 从脱敏调研数据自动生成 -->')
    parts.append('')

    # 1. 线路分类
    types = read_csv("line_types.csv")
    parts.append('    <!-- ===== 线路分类 tour.line.type ===== -->')
    # 建立 LineTypeID -> xml id 映射
    type_id_to_xml = {}
    for i, r in enumerate(types):
        type_id_to_xml[r.get("LineTypeID", "")] = f"line_type_{i+1}"
    parts += xml_records("line_type", types, {
        "__model__": "tour.line.type",
        "TypeName": "name",
        "TypeCode": "code",
        "TypeBrief": "description",
        "OrderNum": "sequence",
    })
    parts.append('')

    # 2. 结算方式
    payways = read_csv("pay_ways.csv")
    parts.append('    <!-- ===== 结算方式 tour.pay.way ===== -->')
    parts += xml_records("pay_way", payways, {
        "__model__": "tour.pay.way",
        "PayWayName": "name",
        "PayWay": "code",
        "SortID": "sequence",
    })
    parts.append('')

    # 3. 业务类型
    biztypes = read_csv("items_57.csv")
    parts.append('    <!-- ===== 业务类型 tour.biz.type ===== -->')
    parts += xml_records("biz_type", biztypes, {
        "__model__": "tour.biz.type",
        "ItemName": "name",
        "HelpCode": "help_code",
        "Brief": "brief",
    })
    parts.append('')

    # 4. 通用基础数据（类型2/3/5/11）
    item_map = {
        "items_2.csv": ("type2", "type2_"),
        "items_3.csv": ("type3", "type3_"),
        "items_5.csv": ("type5", "type5_"),
        "items_11.csv": ("duty", "duty_"),
    }
    parts.append('    <!-- ===== 通用基础数据 tour.base.item ===== -->')
    for fn, (itype, prefix) in item_map.items():
        items = read_csv(fn)
        for i, r in enumerate(items):
            name = esc(r.get("ItemName", ""))
            help_code = esc(r.get("HelpCode", ""))
            brief = esc(r.get("Brief", ""))
            fields = f'\n            <field name="item_type">{itype}</field>'
            if name:
                fields += f'\n            <field name="name">{name}</field>'
            if help_code:
                fields += f'\n            <field name="help_code">{help_code}</field>'
            if brief:
                fields += f'\n            <field name="brief">{brief}</field>'
            parts.append(
                f'    <record id="{prefix}{i+1}" model="tour.base.item">{fields}\n    </record>'
            )
    parts.append('')

    # 5. 线路产品（样本 30 条，含分类引用）
    lines = read_csv("line_products.csv")
    parts.append('    <!-- ===== 线路产品 tour.line（样本）===== -->')
    if SAMPLE_LINE > 0:
        lines = lines[:SAMPLE_LINE]
    for i, r in enumerate(lines):
        name = esc(r.get("LineName", ""))
        code = esc(r.get("LineCode", ""))
        help_code = esc(r.get("HelpCode", ""))
        day_num = esc(r.get("DayNum", ""))
        send_place = esc(r.get("SendPlace", ""))
        end_place = esc(r.get("EndPlace", ""))
        send_traffic = esc(r.get("SendTraffic", ""))
        end_traffic = esc(r.get("EndTraffic", ""))
        self_paid = esc(r.get("SelfPaidItem", ""))
        warm_hint = esc(r.get("WarmHint", ""))
        fields = ""
        if name:
            fields += f'\n            <field name="name">{name}</field>'
        # 分类引用（required）
        tid = r.get("LineTypeID", "")
        xml_ref = type_id_to_xml.get(tid)
        if xml_ref:
            fields += f'\n            <field name="line_type_id" ref="{xml_ref}"/>'
        if code:
            fields += f'\n            <field name="code">{code}</field>'
        if help_code:
            fields += f'\n            <field name="help_code">{help_code}</field>'
        if day_num:
            fields += f'\n            <field name="day_num">{day_num}</field>'
        if send_place:
            fields += f'\n            <field name="send_place">{send_place}</field>'
        if end_place:
            fields += f'\n            <field name="end_place">{end_place}</field>'
        if send_traffic:
            fields += f'\n            <field name="send_traffic">{send_traffic}</field>'
        if end_traffic:
            fields += f'\n            <field name="end_traffic">{end_traffic}</field>'
        if self_paid:
            fields += f'\n            <field name="self_paid_item">{self_paid}</field>'
        if warm_hint:
            fields += f'\n            <field name="warm_hint">{warm_hint}</field>'
        parts.append(
            f'    <record id="line_{i+1}" model="tour.line">{fields}\n    </record>'
        )
    parts.append('')

    parts.append('</odoo>')

    out_path = os.path.join(DST, "tour_base_demo.xml")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"生成完成: {out_path}")
    print(f"  线路分类: {len(types)} 条")
    print(f"  结算方式: {len(payways)} 条")
    print(f"  业务类型: {len(biztypes)} 条")
    print(f"  基础数据: 4 类")
    print(f"  线路产品: {SAMPLE_LINE} 条（样本）")


if __name__ == "__main__":
    main()
