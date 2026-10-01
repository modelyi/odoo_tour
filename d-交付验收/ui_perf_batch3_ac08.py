# -*- coding: utf-8 -*-
# AC-08 / OBS-01 浏览器首屏实测：菜单点击 -> 列表首行可见 计时；每页重复2次，取第2次（排除冷缓存）
# 全程只读导航；口令仅经环境变量 ODOO_TEST_PASS 注入
import os, time, json, re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
OUT  = "/home/adai/tms/d-交付验收/截图-批3"
os.makedirs(OUT, exist_ok=True)
ROWS = ".o_list_table tbody tr, .o_data_row"
ROWS_OR_EMPTY = ROWS + ", .o_view_nocontent, .o_list_table"
CAP = 480  # 秒，等待余量（阈值60s，冷缓存首屏可能远超）

notes, results, rpclog = [], {}, []
current_page = ["home"]

def log(m): print(m, flush=True)
def settle(pg, s=1.2): time.sleep(s)

def dismiss(pg):
    try:
        pg.evaluate("""() => {
            document.querySelectorAll('.o_dialog button.btn-close, .o-notification-close, .o_onboarding_btn_close, .o_onboarding_close_btn')
              .forEach(b=>{try{b.click()}catch(e){}});
        }""")
    except Exception: pass

def wait_sel(pg, sel, cap=CAP):
    t0 = time.time()
    while time.time() - t0 < cap:
        if pg.query_selector_all(sel):
            return round(time.time() - t0, 1)
        time.sleep(0.25)
    return -1

def on_request(req):
    if "/web/dataset/" in req.url or "/web/call" in req.url:
        req._qa_t0 = time.time()

def on_finished(req):
    if hasattr(req, "_qa_t0"):
        ms = round((time.time() - req._qa_t0) * 1000)
        body = req.post_data or ""
        mdl = re.search(r'"model":\s*"([\w.]+)"', body)
        mth = re.search(r'"method":\s*"([\w_]+)"', body) or re.search(r'/web/dataset/(\w+)', req.url)
        rpclog.append({"page": current_page[0], "model": mdl.group(1) if mdl else "",
                       "method": mth.group(1) if mth else "?", "ms": ms,
                       "url": req.url.replace(BASE, "")})

def open_app(pg, app="旅行社"):
    pg.goto(BASE + "/odoo", wait_until="domcontentloaded")
    settle(pg, 1.5)
    el = pg.locator("a.o_app").filter(has_text=app)
    if not el.count():
        pg.click(".o_navbar_apps_menu button"); settle(pg, 1.2)
        el = pg.locator("a.o_app").filter(has_text=app)
    if el.count():
        el.first.click(); settle(pg, 2.5)

def click_menu_leaf(pg, sec, leaf):
    """点 section 下拉后用原生 click 触发 OWL 菜单导航（Playwright 坐标点击会被 popover 拦截）"""
    try:
        tog = pg.locator(".o_menu_sections button").filter(has_text=sec)
        if not tog.count():
            return False
        tog.first.click(); settle(pg, 0.7)
        return pg.evaluate("""(leaf) => {
            const x = [...document.querySelectorAll('.dropdown-menu a, .o-dropdown--menu a')]
                      .find(a => a.textContent.includes(leaf) && a.offsetParent);
            if (x) { x.click(); return true; }
            return false;
        }""", leaf)
    except Exception:
        return False

def timed_menu_nav(pg, key, sec, leaf, shot):
    """计时：点击菜单 -> 路由切换 -> 列表首行渲染。返回总秒数；-1 失败"""
    open_app(pg)
    settle(pg, 0.8); dismiss(pg)
    before = pg.evaluate("() => location.href")
    t0 = time.time()
    if not click_menu_leaf(pg, sec, leaf):
        notes.append(f"{key}: 菜单『{sec}』→『{leaf}』未找到")
        return -1
    # 注意：同步 API 中 pg.url 属性在 time.sleep 期间不处理事件，必须用 evaluate 轮询真实 URL
    while time.time() - t0 < CAP and pg.evaluate("() => location.href") == before:
        time.sleep(0.2)
    nav_s = round(time.time() - t0, 1)
    secs = wait_sel(pg, ".o_data_row, .o_view_nocontent", CAP)
    total = round(time.time() - t0, 1)
    rows = len(pg.query_selector_all(".o_data_row"))
    nocontent = len(pg.query_selector_all(".o_view_nocontent"))
    dismiss(pg)
    try: pg.screenshot(path=os.path.join(OUT, shot))
    except Exception: pass
    notes.append(f"{key} menu={sec}/{leaf} route_switch={nav_s}s data_visible={total}s rows={rows} nocontent={nocontent} url={pg.url}")
    log(f"[NAV] {key} route={nav_s}s total={total}s rows={rows}")
    return total

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    ctx = br.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    cerr = []
    pg.on("console", lambda m: cerr.append(m.text[:200]) if m.type == "error" else None)
    pg.on("pageerror", lambda e: cerr.append(f"pageerror:{e}"))
    pg.on("request", on_request)
    pg.on("requestfinished", on_finished)

    pg.goto(BASE + "/web/login", wait_until="domcontentloaded"); settle(pg, 1)
    pg.fill("#login", "admin"); pg.fill("#password", os.environ["ODOO_TEST_PASS"])
    pg.click("button[type=submit]")
    pg.wait_for_selector("nav", timeout=60000); settle(pg, 2)
    log("logged in: " + pg.url)

    PAGES = [
        ("①单团损益",       "计调",       "单团损益",         "AC-08-①-单团损益-首屏.png"),
        ("②应收账龄",       "财务",       "应收账龄",         "AC-08-②-应收账龄-首屏.png"),
        ("③供应商付款按团",  "财务",       "供应商付款(按团)",  "AC-08-③-供应商付款按团-首屏.png"),
        ("④订单列表",       "销售与报名",  "订单报名",         "AC-08-④-订单列表-首屏.png"),
        ("⑤银行流水",       "财务",       "收款登记",         "AC-08-⑤-银行流水-首屏.png"),
        ("⑤b收款认领(0行)",  "财务",       "收款认领",         "AC-08-⑤b-收款认领-空列表.png"),
    ]
    for key, sec, leaf, shot in PAGES:
        current_page[0] = key + "#run1"
        r1 = timed_menu_nav(pg, key + " run1", sec, leaf, shot)
        current_page[0] = key + "#run2"
        r2 = timed_menu_nav(pg, key + " run2", sec, leaf, f"{shot[:-4]}-r2.png")
        results[key] = {"run1_s": r1, "run2_s": r2}
        with open(os.path.join(OUT, "_perf_ac08.json"), "w") as f:
            json.dump({"results_s": results, "notes": notes, "console_errors": [],
                       "slow_dataset_requests": sorted([r for r in rpclog if r["ms"] > 1000], key=lambda x: -x["ms"])[:40],
                       "dataset_request_count": len(rpclog)}, f, ensure_ascii=False, indent=1)

    # ④ 订单搜索框输入订单号片段后的结果等待（第2轮口径）
    current_page[0] = "④订单搜索#run2"
    open_app(pg)
    if click_menu_leaf(pg, "销售与报名", "订单报名"):
        wait_sel(pg, ROWS); settle(pg, 1)
        inp = pg.query_selector(".o_searchview input, input[type='search']")
        if inp:
            t0 = time.time()
            inp.click(); inp.fill("35870"); settle(pg, 1.0); inp.press("Enter")
            secs = wait_sel(pg, ROWS_OR_EMPTY, cap=CAP)
            results["④订单列表"]["search_35870_run_s"] = round(time.time() - t0, 1)
            results["④订单列表"]["search_35870_rows"] = len(pg.query_selector_all(".o_data_row"))
            dismiss(pg); pg.screenshot(path=os.path.join(OUT, "AC-08-④-订单搜索35870.png"))
            log(f"[SEARCH] 35870 -> {results['④订单列表']['search_35870_run_s']}s")

    br.close()

slow = sorted([r for r in rpclog if r["ms"] > 1000], key=lambda x: -x["ms"])
with open(os.path.join(OUT, "_perf_ac08.json"), "w") as f:
    json.dump({"results_s": results, "notes": notes, "console_errors": cerr[:30],
               "slow_dataset_requests": slow[:40],
               "dataset_request_count": len(rpclog)}, f, ensure_ascii=False, indent=1)
log("RESULTS=" + json.dumps(results, ensure_ascii=False))
log("DONE")
