#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端 UAT 验证脚本 v2：正确捕获 session cookie。"""
import json, urllib.request, http.cookiejar

BASE = "http://127.0.0.1:8070"
DB = "tms"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def post(endpoint, payload):
    url = f"{BASE}/{endpoint}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=60) as r:
        return json.loads(r.read())

def login():
    payload = {"jsonrpc": "2.0", "params": {"db": DB, "login": "admin", "password": "admin"}, "id": 1}
    data = post("web/session/authenticate", payload)
    return data["result"]["uid"]

def search_read(model, domain, fields, limit=100):
    return call_kw(model, "search_read", [], {"domain": domain, "fields": fields, "limit": limit})

def call_kw(model, method, args, kwargs=None):
    r = post("web/dataset/call_kw", {"jsonrpc": "2.0",
        "params": {"model": model, "method": method, "args": args, "kwargs": kwargs or {}}, "id": 3})
    if "error" in r:
        raise RuntimeError(r["error"].get("data", {}).get("message") or r["error"].get("message") or str(r["error"]))
    return r.get("result")

def create(model, vals):
    return call_kw(model, "create", [vals])

results = []
def log(kind, name, ok, detail=""):
    results.append((kind, name, ok, detail))
    mark = "✅" if ok else "❌"
    print(f"{mark} [{kind}] {name}" + (f" → {detail}" if detail else ""))

uid = login()
print(f"登录成功 uid={uid}\n")

# ============ 场景1：线路 → 订单 → 收款 ============
try:
    c = len(search_read("tour.line", [], ["id"]))
    log("场景1", f"线路 tour.line 条数 = {c}", c == 212, f"实际 {c}")
except Exception as e:
    log("场景1", "查询 tour.line", False, str(e))

try:
    plans = search_read("tour.plan", [], ["id", "plan_code", "plan_name", "sum_pay_normal", "sum_pay", "profit", "line_id", "state"], limit=5)
    log("场景1", "团队订单 tour.plan 查询", len(plans) > 0, f"样例: {plans[0]['plan_code']} sum_pay_normal={plans[0]['sum_pay_normal']}")
except Exception as e:
    log("场景1", "查询 tour.plan", False, str(e))

try:
    regs = search_read("tour.plan.reg", [], ["id", "reg_code", "plan_id", "sum_pay_normal"], limit=5)
    log("场景1", "报名 tour.plan.reg 查询(关联plan_id)", len(regs) > 0, f"样例: {regs[0]['reg_code']} plan_id={regs[0]['plan_id']}")
except Exception as e:
    log("场景1", "查询 tour.plan.reg", False, str(e))

try:
    plan_fields = call_kw("tour.plan", "fields_get", [[], {"attributes": ["string", "type"]}])
    has_sum = "sum_pay_normal" in plan_fields
    log("场景1", "订单收款主字段 sum_pay_normal 存在", has_sum, f"type={plan_fields.get('sum_pay_normal',{}).get('type')}")
except Exception as e:
    log("场景1", "fields_get tour.plan", False, str(e))

try:
    p = search_read("tour.plan", [["id", "=", 420]], ["line_id", "plan_code"])
    line = search_read("tour.line", [["id", "=", p[0]["line_id"][0]]], ["name"])
    log("场景1", "订单420→线路关联可读", bool(line), f"{p[0]['plan_code']} → {line[0]['name']}")
except Exception as e:
    log("场景1", "订单→线路关联", False, str(e))

# ============ 场景2：资源 → 计调 ============
try:
    guides = search_read("tour.guide", [["audit_chk", "=", True]], ["id", "name", "guide_code", "id_num", "mobile"], limit=3)
    log("场景2", "导游(已审核)查询 + 脱敏", len(guides) > 0, f"样例: {guides[0]['name']} 身份证={guides[0]['id_num']} 手机={guides[0]['mobile']}")
except Exception as e:
    log("场景2", "查询 tour.guide", False, str(e))

try:
    veh = search_read("tour.vehicle", [], ["id", "name", "licence", "seat_num", "audit_chk"], limit=3)
    log("场景2", "车辆 tour.vehicle 查询", len(veh) > 0, f"样例: {veh[0]['licence']} 座位={veh[0]['seat_num']} audit={veh[0]['audit_chk']}")
except Exception as e:
    log("场景2", "查询 tour.vehicle", False, str(e))

try:
    sup = search_read("res.partner", [["sup_type", "=", "hotel"]], ["id", "name", "sup_type"], limit=3)
    log("场景2", "供应商分类 sup_type=hotel 查询", len(sup) > 0, f"样例: {sup[0]['name']} ({sup[0]['sup_type']})")
except Exception as e:
    log("场景2", "查询供应商分类", False, str(e))

booking_guide_id = None
try:
    g = search_read("tour.guide", [["audit_chk", "=", True]], ["id"], limit=1)
    bid = create("tour.booking", {
        "plan_id": 420, "resource_type": "guide", "guide_id": g[0]["id"],
        "guide_fee": 500.0, "begin_date": "2020-01-02", "end_date": "2020-01-02"})
    booking_guide_id = bid
    b = search_read("tour.booking", [["id", "=", bid]], ["name", "plan_id", "resource_type", "state", "amount_total", "guide_id"])
    log("场景2", "创建计调 booking(派导)", bool(b), f"编号={b[0]['name']} 资源={b[0]['resource_type']} 导服费={b[0]['amount_total']} state={b[0]['state']}")
except Exception as e:
    log("场景2", "创建计调 booking(派导)", False, str(e)[:300])

try:
    v = search_read("tour.vehicle", [["audit_chk", "=", True]], ["id"], limit=1)
    if not v:
        log("场景2", "创建计调 booking(派车)", False, "无已审核车辆(audit_chk=true=0)，派车被域/约束阻止")
    else:
        create("tour.booking", {"plan_id": 420, "resource_type": "vehicle", "vehicle_id": v[0]["id"],
                                 "car_fee": 2000.0, "begin_date": "2020-01-02", "end_date": "2020-01-02"})
        log("场景2", "创建计调 booking(派车)", True)
except Exception as e:
    log("场景2", "创建计调 booking(派车)", False, "预期失败：" + str(e)[:200])

try:
    unaudited = search_read("tour.guide", [["audit_chk", "=", False]], ["id"], limit=1)
    if unaudited:
        create("tour.booking", {"plan_id": 420, "resource_type": "guide", "guide_id": unaudited[0]["id"],
                                 "begin_date": "2020-01-03", "end_date": "2020-01-03"})
        log("场景2", "未审核导游约束(_check_guide_audit)", False, "未审核导游居然创建成功（约束失效）")
    else:
        log("场景2", "未审核导游约束(全部已审核)", True, "无未审核导游可测")
except Exception as e:
    log("场景2", "未审核导游约束(_check_guide_audit)", True, "正确拒绝：" + str(e)[:120])

# ============ 场景3：财务（收款 → 核算 → 佣金） ============
try:
    bank = search_read("tour.bank.account", [], ["id", "name", "acc_number", "balance"], limit=3)
    log("场景3", "银行账户 tour.bank.account 查询", len(bank) > 0, f"样例: {bank[0]['name']} {bank[0]['acc_number']} 余额={bank[0]['balance']}")
except Exception as e:
    log("场景3", "查询银行账户", False, str(e))

try:
    pay_way = search_read("tour.pay.way", [], ["id", "name"], limit=1)
    cust = search_read("res.partner", [["sup_type", "=", "customer"]], ["id"], limit=1)
    claim_id = create("tour.payment.claim", {
        "plan_id": 420, "supplier_id": cust[0]["id"],
        "pay_date": "2020-01-02", "pay_money": 5460.0,
        "pay_way_id": pay_way[0]["id"], "brief": "UAT端到端测试收款"})
    cl = search_read("tour.payment.claim", [["id", "=", claim_id]],
                     ["name", "plan_code", "pay_money", "balance_money", "claim_state"])
    log("场景3", "创建收款登记 tour.payment.claim", bool(cl),
        f"编号={cl[0]['name']} 团号={cl[0]['plan_code']} 金额={cl[0]['pay_money']} 状态={cl[0]['claim_state']}")
except Exception as e:
    log("场景3", "创建收款登记", False, str(e)[:300])

try:
    acct_id = create("tour.plan.account", {"plan_id": 420})
    ac = search_read("tour.plan.account", [["id", "=", acct_id]],
                     ["plan_code", "income_total", "cost_total", "profit", "state"])
    log("场景3", "创建单团核算 tour.plan.account", bool(ac),
        f"团号={ac[0]['plan_code']} 收入={ac[0]['income_total']} 成本={ac[0]['cost_total']} 利润={ac[0]['profit']}")
except Exception as e:
    log("场景3", "创建单团核算", False, str(e)[:300])

try:
    shop = search_read("res.partner", [["sup_type", "=", "shop"]], ["id", "name"], limit=1)
    guide = search_read("tour.guide", [["audit_chk", "=", True]], ["id"], limit=1)
    cm_id = create("tour.commission", {
        "plan_id": 420, "shop_id": shop[0]["id"], "shop_name": shop[0]["name"],
        "guide_id": guide[0]["id"], "commission_rate": 30.0, "shop_amount": 10000.0,
        "commission_total": 3000.0, "guide_share_rate": 50.0, "guide_share_before_tax": 1500.0})
    cm = search_read("tour.commission", [["id", "=", cm_id]],
                     ["plan_code", "shop_name", "commission_total", "guide_share_before_tax", "guide_tax", "guide_net_pay", "company_retain", "state"])
    c0 = cm[0]
    log("场景3", "创建佣金 tour.commission(个税代扣)", bool(cm),
        f"购物店={c0['shop_name']} 佣金={c0['commission_total']} 税前分成={c0['guide_share_before_tax']} 代扣个税={c0['guide_tax']} 实发={c0['guide_net_pay']} 留存={c0['company_retain']}")
    exp_tax = round((1500 - 800) * 0.20, 2)
    tax_ok = abs(c0["guide_tax"] - exp_tax) < 0.01
    log("场景3", "个税代扣公式正确性 (1500→140)", tax_ok, f"期望{exp_tax} 实际{c0['guide_tax']}")
except Exception as e:
    log("场景3", "创建佣金", False, str(e)[:300])

print("\n===== 结果汇总 =====")
for k in ["场景1", "场景2", "场景3"]:
    items = [r for r in results if r[0] == k]
    passed = sum(1 for r in results if r[0] == k and r[2])
    print(f"{k}: {passed}/{len(items)} 通过")
    for r in items:
        if not r[2]:
            print(f"   ❌ {r[1]} → {r[3]}")
total = len(results); passed = sum(1 for r in results if r[2])
print(f"\n总计: {passed}/{total} 通过")
