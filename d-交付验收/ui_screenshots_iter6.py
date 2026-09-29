# -*- coding: utf-8 -*-
# 迭代6 数据迁移 UI 验收截图脚本（只读：仅导航/切视图/搜索过滤，不点任何动作按钮）
import os, time, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
OUT  = "/home/adai/tms/d-交付验收/截图-迭代6"
os.makedirs(OUT, exist_ok=True)
notes = []      # UI 异常记录
perf  = {}      # 每步耗时

def log(msg):
    print(msg, flush=True)

def settle(pg, secs=2.0):
    time.sleep(secs)

def wait_rows(pg, timeout=240, selector=".o_list_table tbody tr, .o_data_row, .o_pivot_table, table.o_pivot"):
    t0 = time.time()
    while time.time() - t0 < timeout:
        n = len(pg.query_selector_all(selector))
        if n:
            return time.time() - t0
        settle(pg, 1.0)
    return -1

def breadcrumb(pg):
    el = pg.query_selector(".o_menu_breadcrumb, .o_control_panel .breadcrumb, nav .breadcrumb")
    return (el.inner_text().replace("\n", " / ") if el else "")[:120]

def shot(pg, name, wait_selector=None, timeout=240, key=""):
    # 关闭新手引导/通知
    try:
        pg.evaluate("""() => {
            document.querySelectorAll('.o_dialog button.btn-close, .o-notification-close, .o_onboarding_close_btn').forEach(b=>{try{b.click()}catch(e){}});
        }""")
    except Exception:
        pass
    secs = -1
    if wait_selector:
        secs = wait_rows(pg, timeout, wait_selector)
    else:
        settle(pg, 2.0)
    t = time.time()
    page_errors = []
    pg.screenshot(path=os.path.join(OUT, name), full_page=False)
    if key:
        perf[key] = round(secs, 1)
    notes.append(f"{name}: url={pg.url} 面包屑='{breadcrumb(pg)}' 数据加载={'%.1fs'%secs if secs>=0 else '超时/不适用'}")
    log(f"saved {name} (load {secs:.1f}s) crumb='{breadcrumb(pg)}'")

def switch_pivot(pg):
    for sel in ["button.o-view-switch-button i.fa.fa-pivot", ".o-switch-view.o-pivot",
                "button:has(i.fa.fa-pivot)", ".o-control-buttons button:has(.fa-pivot)"]:
        b = pg.query_selector(sel)
        if b:
            b.click()
            return True
    return False

def search_term(pg, term):
    inp = pg.query_selector("input[type='search'], .o_searchview input, .search-input input")
    if not inp:
        return False
    inp.click(); inp.fill(term)
    settle(pg, 1.5)
    inp.press("Enter")
    return True

def open_first_row(pg):
    row = pg.query_selector(".o_list_table tbody tr .o_data_cell, .o_list_table tbody tr td a, .o_data_row .o_data_cell")
    if row:
        row.click()
        settle(pg, 3)
        return True
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width":1440,"height":1000})
    pg = ctx.new_page()
    console_errors = []
    pg.on("console", lambda m: console_errors.append(m.text[:300]) if m.type == "error" else None)
    pg.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

    # --- login ---
    pg.goto(BASE + "/web/login", wait_until="domcontentloaded")
    settle(pg, 1)
    pg.fill("#login", "admin"); pg.fill("#password", "admin")
    pg.click("button[type=submit]")
    pg.wait_for_selector("nav", timeout=40000)
    settle(pg, 2)
    log("logged in: " + pg.url)

    # --- 1/2 应收账龄 list+pivot ---
    pg.goto(BASE + "/odoo/action-554", wait_until="domcontentloaded")
    shot(pg, "01-应收账龄-list.png", ".o_list_table tbody tr, .o_data_row", 300, "aging_list")
    ok = switch_pivot(pg)
    log("pivot switch aging: " + str(ok))
    shot(pg, "02-应收账龄-pivot.png", ".o_pivot, table tbody tr", 300, "aging_pivot")

    # --- 3/4 导游绩效 ---
    pg.goto(BASE + "/odoo/action-555", wait_until="domcontentloaded")
    shot(pg, "03-导游绩效-list.png", ".o_list_table tbody tr, .o_data_row", 120, "perf_list")
    switch_pivot(pg)
    shot(pg, "04-导游绩效-pivot.png", ".o_pivot, table tbody tr", 120, "perf_pivot")

    # --- 5/6 景点毛利贡献 ---
    pg.goto(BASE + "/odoo/action-556", wait_until="domcontentloaded")
    shot(pg, "05-景点毛利贡献-list.png", ".o_list_table tbody tr, .o_data_row", 120, "scenic_list")
    search_term(pg, "半坡")
    shot(pg, "05b-景点毛利贡献-半坡样本.png", ".o_list_table tbody tr, .o_data_row", 60, "scenic_demo")
    # 清过滤再切 pivot
    try:
        rm = pg.query_selector(".o_searchview_facet .facet_clear, .o_searchview .facets .clear")
        if rm: rm.click(); settle(pg, 1.5)
    except Exception: pass
    switch_pivot(pg)
    shot(pg, "06-景点毛利贡献-pivot.png", ".o_pivot, table tbody tr", 120, "scenic_pivot")

    # --- 7/8 固定资产 list + 卡片折旧 ---
    pg.goto(BASE + "/odoo/action-551", wait_until="domcontentloaded")
    shot(pg, "07-固定资产-list.png", ".o_list_table tbody tr, .o_data_row", 120, "asset_list")
    search_term(pg, "DEMO|FA001")
    open_first_row(pg)
    shot(pg, "08-固定资产-卡片折旧明细.png", ".o_form_view", 60, "asset_form")
    # 尝试滚到折旧表
    pg.evaluate("""() => { const el=[...document.querySelectorAll('.o-form-sheet-group,.note, .o_inner_group, .o_note_page')].find(x=>/折旧/.test(x.innerText||'')); if(el) el.scrollIntoView(); }""")
    settle(pg, 1)
    pg.screenshot(path=os.path.join(OUT, "08b-固定资产-折旧表.png"))
    log("saved 08b-固定资产-折旧表.png")

    # --- 9/10 费用报销 list + approved 单草稿凭证 ---
    pg.goto(BASE + "/odoo/action-549", wait_until="domcontentloaded")
    shot(pg, "09-费用报销-list.png", ".o_list_table tbody tr, .o_data_row", 120, "expense_list")
    search_term(pg, "DEMO|EXP052")
    open_first_row(pg)
    shot(pg, "10-费用报销-approved凭证.png", ".o_form_view", 60, "expense_form")

    # --- 11 ETM 订单表单 ---
    pg.goto(BASE + "/odoo/action-540", wait_until="domcontentloaded")
    search_term(pg, "ETM|P35870")
    open_first_row(pg)
    shot(pg, "11-ETM订单-名单.png", ".o_form_view", 120, "order_form")
    # 收款/期次页签
    for tab in ["收款", "期次", "收款期次"]:
        t = pg.query_selector(f".o_notebook .nav-link:has-text('{tab}'), .o-tab a:has-text('{tab}')")
        if t:
            try:
                t.click(); settle(pg, 2)
                pg.screenshot(path=os.path.join(OUT, f"11b-ETM订单-{tab}页签.png"))
                log(f"saved 11b-ETM订单-{tab}页签.png")
                break
            except Exception:
                pass

    # --- 12 发团计划表单（导游 + DEMO|V scenic 条目）---
    pg.goto(BASE + "/odoo/action-539", wait_until="domcontentloaded")
    search_term(pg, "ETM|D|811|2026-06-17")
    open_first_row(pg)
    shot(pg, "12-发团计划-DEMO条目.png", ".o_form_view", 120, "dep_form")

    # --- 13 单团损益 ---
    pg.goto(BASE + "/odoo/action-542", wait_until="domcontentloaded")
    shot(pg, "13-单团损益-list.png", ".o_list_table tbody tr, .o_data_row", 300, "pnl_list")

    browser.close()

with open(os.path.join(OUT, "_notes.json"), "w") as f:
    json.dump({"notes": notes, "perf_s": perf, "console_errors": console_errors[:100]}, f, ensure_ascii=False, indent=1)
log("ALL DONE perf=" + json.dumps(perf))
