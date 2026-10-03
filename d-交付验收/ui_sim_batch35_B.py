# -*- coding: utf-8 -*-
"""批3.5 用户仿真测试 · UI 只读取证脚本（最终版）
数据层仿真已由 scripts/sim_batch35.py 完成并提交 tour20（用户授权保留），本脚本只读：
登录 / 导航 / 搜索 / 列排序 / 截图 + RPC 断言，不创建不修改任何单据。

各视图搜索能力差异（均已实测）：
- 计调单/供应商付款/导游绩效/借款/报账/佣金/固定资产/订单：搜索框全文搜索可用
- 单团损益 ta.team.pnl：无搜索视图 → 不搜索，date_start desc 首屏滚动定位
- 应收账龄 ta.receivable.aging：全文搜索失效（SQL 视图无 _rec_name）→ 账龄锚点列降序定位
- 银行流水/收款认领：无搜索视图 → 表单直开取证
口令经环境变量 SIM_ADMIN_PW 传入（默认 admin），不落盘、不打印。
"""
import os, time, json, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
SHOT = "/home/adai/tms/d-交付验收/截图-用户仿真"
ADMIN_PW = os.environ.get("SIM_ADMIN_PW", "admin")

T0 = time.time()
STEPS = []

def log(msg):
    print(f"[{int(time.time()-T0):4d}s] {msg}", flush=True)

def rec(tag, status, detail=""):
    STEPS.append((tag, status, detail))
    log(f"STEP {tag}: {status} {detail}")

def shot(pg, name):
    path = os.path.join(SHOT, name)
    try:
        pg.screenshot(path=path)
        log(f"[SHOT] {name}")
    except Exception as e:
        log(f"[SHOT FAIL] {name}: {e}")

def rpc(model, method, args, kwargs=None):
    payload = {"jsonrpc": "2.0",
               "params": {"service": "object", "method": "execute_kw",
                          "args": ["tour20", 2, ADMIN_PW, model, method, args, kwargs or {}]},
               "id": 7}
    req = urllib.request.Request(BASE + "/jsonrpc", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    if d.get("error"):
        raise RuntimeError(str(d["error"].get("data", {}).get("message") or d["error"].get("message")))
    return d.get("result")

def sr(model, domain, fields, limit=50, order=""):
    return rpc(model, "search_read", [domain, fields, 0, limit, order])

def goto(pg, url, settle=2.5):
    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_selector(".o_control_panel, .o_view_controller, .o_form_view", timeout=20000)
    time.sleep(settle)

def dismiss(pg):
    try:
        pg.evaluate("""() => { document.querySelectorAll('.o_notification_close, .o_onboarding_btn_close, .o_onboarding_close_btn, .modal.show').forEach(b=>{try{b.click()}catch(e){}}); }""")
        pg.keyboard.press("Escape")
    except Exception:
        pass

def search_freetext(pg, text, settle=2.5):
    """全文搜索（仅对搜索框可用的视图使用）"""
    inp = pg.locator(".o_searchview_input").first
    inp.click(); inp.fill(text); time.sleep(1.2); inp.press("Enter")
    time.sleep(settle)
    dismiss(pg)
    return len(pg.query_selector_all(".o_data_row"))

def scroll_row(pg, text):
    try:
        r = pg.locator(f"tr:has-text('{text}')").first
        r.scroll_into_view_if_needed(timeout=8000)
        time.sleep(0.8)
        return True
    except Exception:
        return False

def sort_header(pg, label):
    th = pg.locator(".o_list_table thead th", has_text=label).first
    th.click(); time.sleep(3.5)
    th.click(); time.sleep(3.5)   # 升序→降序

def main():
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        ctx = br.new_context(viewport={"width": 1680, "height": 1000})
        ctx.set_default_timeout(20000)
        pg = ctx.new_page()
        pg.goto(BASE + "/web/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.5)
        pg.fill("#login", "admin"); pg.fill("#password", ADMIN_PW)
        pg.click("button[type=submit]")
        try:
            pg.wait_for_selector("nav", timeout=30000); ok = True
        except Exception:
            ok = False
        time.sleep(2.5)
        rec("login", "PASS" if ok else "FAIL", "admin 登录" )
        if not ok:
            br.close(); return

        # 03 计调单列表：4 条仿真条目 + 账单状态/已付列 + 底部合计
        goto(pg, f"{BASE}/odoo/action-541")
        n = search_freetext(pg, "仿真")
        scroll_row(pg, "仿真|团餐")
        shot(pg, "03-计调单-列表-账单状态已付列.png")
        it = sr("ta.dispatch.item", [["note", "=", "仿真|批3.5"]],
                ["kind", "amount", "bill_state", "paid_amount", "paid_date"], 10)
        tot = round(sum(x["amount"] for x in it), 2); paid = round(sum(x["paid_amount"] for x in it), 2)
        rec("s3-计调单", "PASS" if n == 4 and abs(tot-5360) < 0.01 and abs(paid-3960) < 0.01 and all(x["bill_state"] == "posted" for x in it) else "FAIL",
            f"UI行数={n} RPC total={tot} paid={paid} bills={[x['bill_state'] for x in it]}")

        # 04 供应商付款(按团)
        goto(pg, f"{BASE}/odoo/action-557")
        n = search_freetext(pg, "仿真")
        scroll_row(pg, "仿真|环岛车队")
        shot(pg, "04-供应商付款按团-仿真4行.png")
        rows = sr("ta.supplier.payable", [["departure_id", "=", 92519]],
                  ["supplier_id", "item_total", "paid_total", "open_amount"], 10)
        it2 = round(sum(r["item_total"] for r in rows), 2)
        pd2 = round(sum(r["paid_total"] for r in rows), 2)
        op2 = round(sum(r["open_amount"] for r in rows), 2)
        rec("s4-供应商付款", "PASS" if n == 4 and (abs(it2-5360) < 0.01 and abs(pd2-3960) < 0.01 and abs(op2-1400) < 0.01) else "FAIL",
            f"UI行数={n} RPC total={it2} paid={pd2} open={op2}")

        # 05 银行流水（表单直开：认领明细页签含认领单）
        for bid, ref in [(256119, "0001"), (256120, "0002")]:
            goto(pg, f"{BASE}/odoo/action-543/{bid}")
            shot(pg, f"05-银行流水-网银{ref}-表单.png")
        bls = sr("ta.bank.line", [["ref", "like", "仿真|网银-%"]], ["ref", "amount", "state"], 5, "id desc")
        rec("s5-银行流水", "PASS" if len(bls) == 2 and all(b["state"] == "claimed" for b in bls) else "FAIL",
            f"RPC={[(b['ref'], b['amount'], b['state']) for b in bls]}")

        # 05 收款认领（表单直开两单）
        for cid, cname in [(408, "RL000408"), (409, "RL000409")]:
            goto(pg, f"{BASE}/odoo/action-544/{cid}")
            shot(pg, f"05-收款认领-{cname}-已审核.png")
        cls = sr("ta.payment.claim", [["id", "in", [408, 409]]], ["name", "state", "amount", "approved_by"], 5)
        rec("s5-收款认领", "PASS" if len(cls) == 2 and all(c["state"] == "approved" and c["approved_by"][1] == "DEMO|会计" for c in cls) else "FAIL",
            f"RPC={[(c['name'], c['amount'], c['state'], c['approved_by'][1]) for c in cls]}")

        # 05 订单（表单直开 O1 + 列表按单号搜索）
        goto(pg, f"{BASE}/odoo/action-540/434855")
        shot(pg, "05-订单-DD000229-已收5000未收3000.png")
        goto(pg, f"{BASE}/odoo/action-540")
        n = search_freetext(pg, "DD000242")
        scroll_row(pg, "DD000242")
        shot(pg, "05-订单-列表-仿真3单.png")
        ords = sr("ta.order", [["departure_id", "=", 92519], ["state", "=", "confirmed"]],
                  ["name", "amount_total", "amount_paid"], 10, "id asc")
        exp = {"DD000229": 5000.0, "DD000241": 3200.0, "DD000242": 0.0}
        ok = len(ords) == 3 and all(abs(o["amount_paid"] - exp[o["name"]]) < 0.01 for o in ords)
        rec("s5-订单核对", "PASS" if ok else "FAIL",
            f"UI搜索行数={n} RPC={[(o['name'], o['amount_total'], o['amount_paid']) for o in ords]}")

        # 06 单团损益（无搜索视图：首屏滚动定位，date_start desc 且 ≥2026-10-03 仅 63 行）
        goto(pg, f"{BASE}/odoo/action-542")
        ok = scroll_row(pg, "BQ00266")
        shot(pg, "06-单团损益-BQ00266.png")
        pnl = sr("ta.team.pnl", [["code", "=", "BQ00266"]],
                 ["code", "income", "order_total", "cost_total", "cost_net", "profit"], 3)
        p = pnl[0] if pnl else {}
        rec("s6-单团损益", "PASS" if ok and p and abs(p["income"]-8200) < 0.01 and abs(p["cost_total"]-5360) < 0.01 and abs(p["cost_net"]-5960) < 0.01 and abs(p["profit"]-2240) < 0.01 else "FAIL",
            f"UI定位={ok} RPC={p}")

        # 06 应收账龄（全文搜索失效：账龄锚点列降序 → 仿真 2 行置顶）
        goto(pg, f"{BASE}/odoo/action-554")
        sort_header(pg, "账龄锚点")
        ok = scroll_row(pg, "DD000242")
        shot(pg, "06-应收账龄-仿真2行b0_30.png")
        ag = sr("ta.receivable.aging", [["departure_id", "=", 92519]],
                ["order_name", "amount_open", "bucket"], 10)
        ok2 = len(ag) == 2 and all(a["bucket"] == "b0_30" for a in ag) and \
            sorted([round(a["amount_open"], 2) for a in ag]) == [3000.0, 5600.0]
        rec("s6-应收账龄", "PASS" if ok and ok2 else "FAIL",
            f"UI定位={ok} RPC={[(a['order_name'], a['amount_open'], a['bucket']) for a in ag]}")

        # 06 导游绩效
        goto(pg, f"{BASE}/odoo/action-555")
        n = search_freetext(pg, "林海")
        shot(pg, "06-导游绩效-林海2026-11.png")
        perf = sr("ta.guide.performance", [["guide_id", "=", 6394]],
                  ["ym", "income", "cost_total", "profit", "commission_net", "loan_outstanding"], 5, "ym desc")
        pk = perf[0] if perf else {}
        rec("s6-导游绩效", "PASS" if n == 1 and pk and abs(pk["income"]-8200) < 0.01 and abs(pk["cost_total"]-5960) < 0.01 and abs(pk["profit"]-2240) < 0.01 else "FAIL",
            f"UI行数={n} RPC={pk}")

        # 07 导游三件套
        goto(pg, f"{BASE}/odoo/action-545")
        n = search_freetext(pg, "JK00112")
        scroll_row(pg, "JK00112")
        shot(pg, "07-导游借款-JK00112未结1800.png")
        ln = sr("ta.guide.loan", [["name", "=", "JK00112"]], ["name", "state", "amount", "outstanding"], 3)
        l = ln[0] if ln else {}
        rec("s7-导游借款", "PASS" if n == 1 and l and l["state"] == "paid" and abs(l["outstanding"]-1800) < 0.01 else "FAIL",
            f"UI行数={n} RPC={l}")

        goto(pg, f"{BASE}/odoo/action-546")
        search_freetext(pg, "仿真")
        scroll_row(pg, "600")
        shot(pg, "07-导游报账-600已审核.png")
        ge = sr("ta.guide.expense", [["id", "=", 72]], ["state", "amount_total", "approved_by"], 3)
        g = ge[0] if ge else {}
        rec("s7-导游报账", "PASS" if g and g["state"] == "approved" and abs(g["amount_total"]-600) < 0.01 else "FAIL",
            f"RPC={g}")

        goto(pg, f"{BASE}/odoo/action-547")
        n = search_freetext(pg, "YJ00065")
        scroll_row(pg, "YJ00065")
        shot(pg, "07-导游佣金-YJ00065已结算.png")
        cm = sr("ta.guide.commission", [["name", "=", "YJ00065"]],
                ["name", "state", "allowance", "net_amount", "payable_rest"], 3)
        c = cm[0] if cm else {}
        rec("s7-导游佣金", "PASS" if n == 1 and c and c["state"] == "settled" and abs(c["net_amount"]-1200) < 0.01 and abs(c["payable_rest"]) < 0.01 else "FAIL",
            f"UI行数={n} RPC={c}")

        # 08 费用报销 / 固定资产
        goto(pg, f"{BASE}/odoo/action-549/334")
        shot(pg, "08-费用报销-FY26000234已审核.png")
        ex = sr("ta.expense", [["id", "=", 334]], ["name", "state", "amount"], 3)
        e = ex[0] if ex else {}
        rec("s8-费用报销", "PASS" if e and e["state"] == "approved" and abs(e["amount"]-400) < 0.01 else "FAIL",
            f"RPC={e}")

        goto(pg, f"{BASE}/odoo/action-551")
        n = search_freetext(pg, "仿真")
        scroll_row(pg, "对讲机")
        shot(pg, "08-固定资产-对讲机折旧211.png")
        aset = sr("ta.asset", [["id", "=", 175]], ["name", "state", "cost", "book_value"], 3)
        a = aset[0] if aset else {}
        rec("s8-固定资产", "PASS" if n == 1 and a and a["state"] == "in_use" and abs(a["book_value"]-7788.89) < 0.01 else "FAIL",
            f"UI行数={n} RPC={a}")

        # 01 发团计划（余位 12/20）
        goto(pg, f"{BASE}/odoo/action-539")
        n = search_freetext(pg, "BQ00266")
        scroll_row(pg, "BQ00266")
        shot(pg, "01-发团计划-BQ00266余位12-20.png")
        dep = sr("ta.departure", [["code", "=", "BQ00266"]], ["code", "state", "seats_used", "seats_total"], 3)
        d = dep[0] if dep else {}
        rec("s1-发团计划", "PASS" if n == 1 and d and d["state"] == "confirmed" and d["seats_used"] == 12 else "FAIL",
            f"UI行数={n} RPC={d}")

        br.close()

    fails = sum(1 for _, st, _ in STEPS if st == "FAIL")
    print("\n===== SUMMARY =====")
    for tag, st, dt in STEPS:
        print(f"{st:5s} | {tag:12s} | {dt}")
    print(f"\n共 {len(STEPS)} 步，FAIL={fails}")

if __name__ == "__main__":
    main()
