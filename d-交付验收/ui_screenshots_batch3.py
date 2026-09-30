# -*- coding: utf-8 -*-
# 批3（产品能力补齐）UI 验收截图 + OBS-01 性能复测（全程只读：仅导航/搜索/切视图/打开表单）
# 口令仅经环境变量 ODOO_TEST_PASS 注入，不落盘、不打印
import os, time, json, re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
OUT  = "/home/adai/tms/d-交付验收/截图-批3"
os.makedirs(OUT, exist_ok=True)
notes, perf, rpclog = [], {}, []
ROWS = ".o_list_table tbody tr, .o_data_row"
ROWS_OR_EMPTY = ROWS + ", .o_view_nocontent, .o_list_table"

def log(m): print(m, flush=True)
def settle(pg, s=1.5): time.sleep(s)

def wait_rows(pg, selector=ROWS, cap=620):
    t0 = time.time()
    while time.time() - t0 < cap:
        if pg.query_selector_all(selector):
            return round(time.time() - t0, 1)
        time.sleep(0.5)
    return -1

def dismiss(pg):
    try:
        pg.evaluate("""() => {
            document.querySelectorAll('.o_dialog button.btn-close, .o-notification-close, .o_onboarding_btn_close, .o_onboarding_close_btn')
              .forEach(b=>{try{b.click()}catch(e){}});
        }""")
    except Exception: pass

def rpc_timer(pg):
    pending = {}
    def on_req(req):
        if "/web/dataset/" in req.url:
            pending[req] = time.time()
    def on_fin(req):
        if req in pending:
            ms = round((time.time() - pending.pop(req)) * 1000)
            if ms > 800:
                body = req.post_data or ""
                mm = re.search(r'"method_name":\s*"(\w+)"', body)
                mdl = re.search(r'"model":\s*"([\w.]+)"', body)
                rpclog.append({"model": mdl.group(1) if mdl else "",
                               "method": mm.group(1) if mm else "?", "ms": ms})
    pg.on("request", on_req); pg.on("requestfinished", on_fin)

def goto_shot(pg, name, url, key, selector=ROWS, cap=620):
    t0 = time.time()
    pg.goto(url, wait_until="domcontentloaded")
    secs = wait_rows(pg, selector, cap)
    settle(pg, 1.2); dismiss(pg)
    pg.screenshot(path=os.path.join(OUT, name))
    perf[key] = secs if secs >= 0 else -1
    n_empty = len(pg.query_selector_all(".o_view_nocontent"))
    notes.append(f"{name} url={pg.url} load={secs}s total={round(time.time()-t0,1)}s rows={len(pg.query_selector_all('.o_data_row'))} nocontent={n_empty}")
    log(f"[SHOT] {name} key={key} load={secs}s")

def search_term(pg, term, cap=620):
    inp = pg.query_selector(".o_searchview input, input[type='search']")
    if not inp: return False
    t0 = time.time()
    inp.click(); inp.fill(term); settle(pg, 1.0); inp.press("Enter")
    secs = wait_rows(pg, ROWS_OR_EMPTY, cap)
    perf[f"search::{term}"] = round(time.time() - t0, 1)
    log(f"[SEARCH] '{term}' done in {round(time.time()-t0,1)}s rows={len(pg.query_selector_all('.o_data_row'))}")
    return True

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    ctx = br.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page(); rpc_timer(pg)
    cerr = []
    pg.on("console", lambda m: cerr.append(m.text[:200]) if m.type == "error" else None)
    pg.on("pageerror", lambda e: cerr.append(f"pageerror:{e}"))

    pg.goto(BASE + "/web/login", wait_until="domcontentloaded"); settle(pg, 1)
    pg.fill("#login", "admin"); pg.fill("#password", os.environ["ODOO_TEST_PASS"])
    pg.click("button[type=submit]")
    pg.wait_for_selector("nav", timeout=60000); settle(pg, 2)
    log("logged in: " + pg.url)

    # AC-01 线路 + 详细行程
    goto_shot(pg, "AC-01-线路列表-ZY搜索.png", BASE + "/odoo/action-537", "ac01_route_list")
    search_term(pg, "杭杭6天")  # 线路212：交通/三餐/住宿 6/6/6 全有值，且含6条批3前空白占位stop
    settle(pg, 1)
    row = pg.query_selector(".o_data_row .o_data_cell")
    if row:
        row.click(); settle(pg, 3)
        tab = pg.query_selector(".o_notebook .nav-link:has-text('详细行程'), .nav-link:has-text('行程')")
        if tab:
            tab.click(); settle(pg, 2)
            pg.screenshot(path=os.path.join(OUT, "AC-01-线路-详细行程页签-空白占位行.png"))
            n_stops = len(pg.query_selector_all(".o_notebook .o_list_table tbody tr, .o_notebook .o_data_row"))
            notes.append(f"AC-01 form url={pg.url} stop_rows={n_stops}")
            log(f"[SHOT] AC-01 详细行程页签 stops={n_stops}")
            pg.evaluate("() => {const t=document.querySelectorAll('.o_notebook .o_list_table tbody tr'); if(t.length>4)t[Math.floor(t.length/2)].scrollIntoView();}")
            settle(pg, 1)
            pg.screenshot(path=os.path.join(OUT, "AC-01-线路-详细行程页签-下半-交通三餐住宿.png"))
        else:
            notes.append("AC-01 未找到详细行程页签")
            pg.screenshot(path=os.path.join(OUT, "AC-01-线路-表单.png"))

    # OBS-01 性能首屏（冷导航）
    goto_shot(pg, "OBS01-单团损益-list首屏.png", BASE + "/odoo/action-542", "perf_pnl_list")
    goto_shot(pg, "OBS01-应收账龄-list首屏.png", BASE + "/odoo/action-554", "perf_aging_list", cap=610)
    goto_shot(pg, "OBS01-供应商付款按团-list首屏.png", BASE + "/odoo/action-557", "perf_supplier_list")
    goto_shot(pg, "OBS01-收款认领-list首屏.png", BASE + "/odoo/action-544", "perf_claim_list", selector=ROWS_OR_EMPTY)
    goto_shot(pg, "OBS01-银行流水-list首屏.png", BASE + "/odoo/action-543", "perf_bank_list")
    goto_shot(pg, "OBS01-订单列表-首屏.png", BASE + "/odoo/action-540", "perf_order_list")
    search_term(pg, "35870", cap=600)
    settle(pg, 1); dismiss(pg)
    pg.screenshot(path=os.path.join(OUT, "OBS01-订单模糊搜索-35870.png"))

    # AC-02 list + pivot
    pg.goto(BASE + "/odoo/action-557", wait_until="domcontentloaded")
    wait_rows(pg); settle(pg, 1); dismiss(pg)
    pg.screenshot(path=os.path.join(OUT, "AC-02-供应商付款按团-list.png"))
    for label in ["条目合计", "已付", "合计"]:
        h = pg.query_selector(f"th:has-text('{label}')")
        if h:
            h.click(); settle(pg, 2.5); break
    pg.screenshot(path=os.path.join(OUT, "AC-02-供应商付款按团-list-排序.png"))
    b = pg.query_selector("button:has(i.fa.fa-pivot), .o-switch-view:has(.fa-pivot), [data-view-type='pivot']")
    if b:
        t0 = time.time(); b.click()
        wait_rows(pg, ".o_pivot_table, table.o_pivot tbody tr, .o_pivot", 300)
        perf["perf_supplier_pivot"] = round(time.time() - t0, 1)
        settle(pg, 1)
        pg.screenshot(path=os.path.join(OUT, "AC-02-供应商付款按团-pivot.png"))
        log(f"[SHOT] AC-02 pivot {perf['perf_supplier_pivot']}s")
    else:
        notes.append("AC-02 pivot 按钮未找到")

    # AC-03 ETM 团
    pg.goto(BASE + "/odoo/action-542", wait_until="domcontentloaded")
    wait_rows(pg, ROWS, 610); settle(pg, 1); dismiss(pg)
    n_ac03 = search_term(pg, "ETM|D|856|2023-04-29", cap=600)
    settle(pg, 1); dismiss(pg)
    n_rows_ac03 = len(pg.query_selector_all(".o_data_row"))
    notes.append(f"AC-03 search rows={n_rows_ac03}")
    pg.screenshot(path=os.path.join(OUT, "AC-03-单团损益-ETM团.png"))
    if n_rows_ac03 == 0 or n_rows_ac03 > 8:
        # 兜底：清搜索后按成本列降序排序，首屏即报告抽样的3个高成本ETM团
        try:
            for chip in pg.query_selector_all(".o_searchview .o_searchview_facet .o_searchview_facet_label"):
                chip.click(); settle(pg, 0.5)
            h = pg.query_selector("th:has-text('成本（含税）'), th:has-text('成本')")
            if h:
                h.click(); settle(pg, 2); h.click(); settle(pg, 2)
            pg.screenshot(path=os.path.join(OUT, "AC-03-单团损益-按成本降序兜底.png"))
            notes.append("AC-03 使用了成本降序兜底截图")
        except Exception as e:
            notes.append(f"AC-03 兜底失败: {e}")

    # AC-04 / AC-05 / AC-06
    goto_shot(pg, "AC-04-景点毛利贡献-list.png", BASE + "/odoo/action-556", "ac04_scenic")
    goto_shot(pg, "AC-05-导游绩效-list.png", BASE + "/odoo/action-555", "ac05_perf")
    goto_shot(pg, "AC-06-导游借支-list.png", BASE + "/odoo/action-545", "ac06_loan")
    search_term(pg, "ETM", cap=120)
    settle(pg, 1); dismiss(pg)
    pg.screenshot(path=os.path.join(OUT, "AC-06-导游借支-ETM过滤.png"))

    br.close()

with open(os.path.join(OUT, "_notes.json"), "w") as f:
    json.dump({"perf_s": perf, "notes": notes, "console_errors": cerr[:50],
               "slow_rpc": sorted(rpclog, key=lambda x: -x["ms"])[:25]}, f, ensure_ascii=False, indent=1)
log("PERF=" + json.dumps(perf, ensure_ascii=False))
log("DONE")
