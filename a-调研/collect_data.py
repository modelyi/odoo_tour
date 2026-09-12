#!/usr/bin/env python3
"""易途系统调研 —— 数据采集（流式分页，接口地址均经浏览器 XHR 抓包验证）

产出:
    et_data/<表名>.csv      全量数据（UTF-8-BOM，可直接用 Excel/WPS 打开）
    et_data/<表名>.json     元信息 + 字段清单 + 前 50 行样例
    易途系统数据.db           SQLite，全量数据
    数据汇总.json            汇总
"""
import csv
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import et_login  # noqa: E402

BASE = "http://et.example.com"
HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "et_data")
DB = os.path.join(HERE, "易途系统数据.db")

PAGESIZE = 2000
SAMPLE_ROWS = 50

# (表名, 中文名, 归属页面, API路径, 参数)
ENDPOINTS = [
    ("line_products", "线路产品", "资源中心>线路模板",
     "/Line/GetSearchList/ResMng.LineList", {}),
    ("line_types", "线路分类", "资源中心>线路分类",
     "/LineType/GetSearchList/ResMng.LineTypeList", {}),
    ("customers", "客户档案", "资源中心>客户档案",
     "/Supplier/GetSearchList/ResMng.SupplierList", {"supTypeId": 1}),
    ("ditches", "地接社档案", "资源中心>地接社档案",
     "/Supplier/GetSearchList/ResMng.SupplierList2", {"supTypeId": 2}),
    ("hotels", "酒店档案", "资源中心>酒店档案",
     "/Supplier/GetSearchList/ResMng.HotelList", {"supTypeId": 4}),
    ("meals", "餐厅档案", "资源中心>餐厅档案",
     "/Supplier/GetSearchList/ResMng.MealList", {"supTypeId": 5}),
    ("vehicle_comps", "车辆公司", "资源中心>车辆公司",
     "/Supplier/GetSearchList/ResMng.VehicleList", {"supTypeId": 6}),
    ("tickets", "票务公司", "资源中心>票务公司",
     "/Supplier/GetSearchList/ResMng.TicketList", {"supTypeId": 7}),
    ("scenics", "景区景点", "资源中心>景区景点",
     "/Supplier/GetSearchList/ResMng.ScenicList", {"supTypeId": 8}),
    ("shops", "购物店", "资源中心>购物店档案",
     "/Supplier/GetSearchList/ResMng.ShopList", {"supTypeId": 9}),
    ("insurances", "保险公司", "资源中心>保险公司",
     "/Supplier/GetSearchList/ResMng.InsuranceList", {"supTypeId": 10}),
    ("visas", "签证公司", "资源中心>签证公司",
     "/Supplier/GetSearchList/ResMng.VisaList", {"supTypeId": 11}),
    ("self_fees", "自费公司", "资源中心>自费公司",
     "/Supplier/GetSearchList/ResMng.SelfFeeList", {"supTypeId": 13}),
    ("guides", "导游档案", "资源中心>导游档案",
     "/Guide/GetSearchList/ResMng.GuideList", {}),
    ("vehicles", "车辆档案", "资源中心>车辆档案",
     "/Driver/GetSearchList/ResMng.DriverList", {}),
    ("team_orders", "团队订单", "常规业务>团队订单",
     "/Plan/SearchPlanAndReg/Plan.List", {}),
    ("plan_regs", "订单报名", "地接散拼>订单",
     "/PlanReg/SearchReg/PlanMng.ListRegDSN", {}),
    ("pay_claims", "收款登记", "收款认领>收款登记",
     "/PayClaim/SearchPayClaim/PayClaim.List1", {}),
    ("accounts", "银行账户", "财务管理>银行账户管理",
     "/Account/GetSearchList/ResMng.AccountList", {}),
    ("pay_ways", "结算方式", "基础数据>结算方式",
     "/Item/SearchPayWayItemList/Item.PayWayItemList", {}),
    ("departments", "部门设置", "系统管理>部门设置",
     "/Department/GetSearchList/SysMng.DeptList", {}),
    ("users", "用户管理", "系统管理>用户管理",
     "/User/SearchUserList/SysMng.UserList", {}),
    ("companies", "公司信息", "系统管理>公司信息",
     "/Company/GetSearchList/SysMng.CmpList", {}),
    ("items_2", "基础数据-类型2", "基础数据",
     "/Item/GetItemByTypeID/ResMng.ItemList", {"itemType": 2}),
    ("items_3", "基础数据-类型3", "基础数据",
     "/Item/GetItemByTypeID/ResMng.ItemList", {"itemType": 3}),
    ("items_5", "基础数据-类型5", "基础数据",
     "/Item/GetItemByTypeID/ResMng.ItemList", {"itemType": 5}),
    ("items_11", "基础数据-职务", "基础数据",
     "/Item/GetItemByTypeID/ResMng.ItemList", {"itemType": 11}),
    ("items_57", "基础数据-业务类型", "基础数据",
     "/Item/GetItemByTypeID/ResMng.ItemList", {"itemType": 57}),
]

SKIPPED = [
    ("channels", "平台商档案", "/Supplier/List/ResMng.ChannelList?supTypeId=15",
     "当前账号无该模块权限（页面返回“未经授权，您无权访问该页”）"),
    ("cities", "区域维护", "/City/List/ResMng.CityList",
     "页面为空壳，未发起任何数据接口请求"),
]

DATE_RE = re.compile(r"^/Date\((-?\d+)\)/$")


def clean(v):
    if isinstance(v, str):
        m = DATE_RE.match(v)
        if m:
            try:
                return time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.localtime(int(m.group(1)) / 1000.0))
            except Exception:
                return v
        return v
    return v


def cell(v):
    """转成可写入 CSV/SQLite 的标量"""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return clean(v)


def post_page(session, path, extra, page, pagesize=PAGESIZE):
    params = {"page": page, "pagesize": pagesize, "rows": pagesize}
    params.update(extra)
    r = session.post(BASE + path, data=params, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    t = r.text.strip()
    if not t:
        raise RuntimeError("空响应")
    if not t.startswith(("{", "[")):
        raise RuntimeError(f"非JSON: {t[:100]}")
    data = json.loads(t)
    if isinstance(data, list):
        return data, len(data)
    rows = data.get("Rows") or data.get("rows") or data.get("data") or []
    if isinstance(rows, dict):
        rows = [rows]
    return rows, int(data.get("Total") or data.get("total") or 0)


class Pager:
    """带自适应页大小的分页取数器。

    部分接口（如 /Supplier/...）有 JSON 序列化长度上限，pagesize 过大时
    返回 HTTP 500。这里在失败时自动折半重试，取到后再沿用该页大小。
    """

    def __init__(self, session, path, extra, pagesize=PAGESIZE):
        self.s, self.path, self.extra = session, path, extra
        self.pagesize = pagesize

    def get(self, page):
        while True:
            try:
                return post_page(self.s, self.path, self.extra, page, self.pagesize)
            except RuntimeError as e:
                if "HTTP 500" in str(e) and self.pagesize > 50:
                    self.pagesize //= 2
                    print(f"      ↘ 调整页大小至 {self.pagesize}（接口序列化上限）", flush=True)
                    continue
                raise


def collect(session, table, cname, page_name, path, extra, db):
    """流式拉取一张表，边取边写 CSV / SQLite"""
    pager = Pager(session, path, extra)
    rows, total = pager.get(1)
    if not rows:
        return None

    fields, seen = [], set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                fields.append(k)

    csv_path = os.path.join(OUTDIR, f"{table}.csv")
    fh = open(csv_path, "w", newline="", encoding="utf-8-sig")
    w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
    w.writeheader()

    cols = ", ".join(f'"{c}"' for c in fields)
    db.execute(f'DROP TABLE IF EXISTS "{table}"')
    db.execute(f'CREATE TABLE "{table}" ({cols})')
    ph = ", ".join("?" * len(fields))
    ins = f'INSERT INTO "{table}" VALUES ({ph})'

    sample, count, page = [], 0, 1
    while True:
        if not rows:
            break
        w.writerows([{k: cell(r.get(k, "")) for k in fields} for r in rows])
        db.executemany(ins, [[cell(r.get(k, "")) for k in fields] for r in rows])
        if len(sample) < SAMPLE_ROWS:
            sample.extend(rows[:SAMPLE_ROWS - len(sample)])
        count += len(rows)

        if total and count >= total:
            break
        page += 1
        rows, total = pager.get(page)
        if page % 10 == 2:
            print(f"      ...{cname} {count:,}/{total:,} (页大小 {pager.pagesize})", flush=True)

    fh.close()

    with open(os.path.join(OUTDIR, f"{table}.json"), "w", encoding="utf-8") as f:
        json.dump({"表名": table, "中文名": cname, "归属页面": page_name,
                   "API": path, "参数": extra, "记录数": count,
                   "字段数": len(fields), "字段": fields,
                   "说明": f"完整数据见 {table}.csv 与 SQLite 库；此处仅存前 {len(sample)} 行样例",
                   "样例数据": sample},
                  f, ensure_ascii=False, indent=2, default=str)

    return {"表名": table, "归属页面": page_name, "API": path,
            "记录数": count, "字段数": len(fields)}


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    sess = et_login.login(verbose=False)
    print(f"登录成功  session={sess.cookies.get('ASP.NET_SessionId')}\n")

    summary, failed = {}, []
    db = sqlite3.connect(DB)
    db.execute("PRAGMA synchronous=OFF")

    for table, cname, page_name, path, extra in ENDPOINTS:
        try:
            info = collect(sess, table, cname, page_name, path, extra, db)
            db.commit()
        except Exception as e:
            failed.append((table, cname, path, str(e)[:90]))
            print(f"✗ {cname:16s} {path}  — {str(e)[:70]}", flush=True)
            continue

        if info is None:
            failed.append((table, cname, path, "接口正常返回 0 条记录（库中确无数据）"))
            print(f"○ {cname:16s} {path}  → 0 条", flush=True)
            continue

        summary[cname] = info
        print(f"✓ {cname:16s} {path}  → {info['记录数']:,} 条 / {info['字段数']} 字段",
              flush=True)

    db.commit()
    db.close()

    total_recs = sum(v["记录数"] for v in summary.values())
    with open(os.path.join(HERE, "数据汇总.json"), "w", encoding="utf-8") as f:
        json.dump({"采集时间": time.strftime("%Y-%m-%d %H:%M:%S"), "数据源": BASE,
                   "账号": et_login.USERNAME, "表单数": len(summary),
                   "总记录数": total_recs, "表单": summary,
                   "未采集": [{"表名": t, "中文名": c, "API": p, "原因": e}
                              for t, c, p, e in failed]
                             + [{"表名": t, "中文名": c, "位置": p, "原因": e}
                                for t, c, p, e in SKIPPED]},
                  f, ensure_ascii=False, indent=2)

    print(f"\n合计 {len(summary)} 张表 / {total_recs:,} 条记录 / "
          f"未采集 {len(failed) + len(SKIPPED)} 项")
    for t, c, p, e in failed:
        print(f"  未采集: {c} — {e}")
    for t, c, p, e in SKIPPED:
        print(f"  跳过:   {c} — {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
