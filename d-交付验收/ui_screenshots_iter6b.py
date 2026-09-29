# -*- coding: utf-8 -*-
# 迭代6 UI 截图（第二批：账龄pivot + 绩效/景点/资产/费用/订单/发团/损益）
import os, time, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
OUT  = "/home/adai/tms/d-交付验收/截图-迭代6"
os.makedirs(OUT, exist_ok=True)
notes, perf, cerr = [], {}, []

def log(m): print(m, flush=True)
def settle(pg, s=2.0): time.sleep(s)

def wait_for(pg, selector, timeout=600):
    t0=time.time()
    while time.time()-t0 < timeout:
        if pg.query_selector(selector): return round(time.time()-t0,1)
        time.sleep(1)
    return -1

def dismiss(pg):
    try:
        pg.evaluate("""()=>{document.querySelectorAll('.o_dialog .btn-close,.o-notification-close,.o_onboarding_close_btn').forEach(b=>{try{b.click()}catch(e){}});}""")
    except Exception: pass

def crumb(pg):
    el = pg.query_selector(".breadcrumb")
    return el.inner_text().replace("\n"," / ") if el else ""

def rows_n(pg):
    return len(pg.query_selector_all("table.o_list_table tbody tr, .o_list_table tbody tr"))

def shot(pg, name, key, wait_sel=None, timeout=600):
    dismiss(pg)
    secs = wait_for(pg, wait_sel, timeout) if wait_sel else 2
    settle(pg, 2)
    pg.screenshot(path=os.path.join(OUT, name))
    perf[key]=secs
    notes.append(f"{name} | url={pg.url} | crumb={crumb(pg)} | wait={secs}s")
    log(f"saved {name} wait={secs}s rows={rows_n(pg)}")

def pivot(pg):
    b = pg.query_selector("button.o_switch_view.o_pivot")
    if b:
        b.click(); return True
    return False

def search(pg, term):
    inp = pg.query_selector(".o_searchview input")
    if not inp: return False
    inp.click(); inp.fill(term); settle(pg,1.5); inp.press("Enter")
    t0=time.time()
    while time.time()-t0<120:
        settle(pg,1)
        if pg.evaluate("()=>{const el=document.querySelector('.o_loading_indicator');return !el||getComputedStyle(el).display==='none'}"):
            break
    return True

def open_row(pg, idx=0):
    loc = pg.locator("table.o_list_table tbody tr").nth(idx)
    loc.locator("td").nth(2).click(timeout=15000)
    settle(pg,3)

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    pg = br.new_context(viewport={"width":1440,"height":1000}).new_page()
    pg.on("console", lambda m: cerr.append(m.text[:200]) if m.type=="error" else None)
    pg.on("pageerror", lambda e: cerr.append(f"pageerror:{e}"))
    pg.goto(BASE+"/web/login", wait_until="domcontentloaded"); settle(pg,1)
    pg.fill("#login","admin"); pg.fill("#password", os.environ.get("ODOO_TEST_PASS","admin")); pg.click("button[type=submit]")
    pg.wait_for_selector("nav", timeout=40000); settle(pg,2)
    log("logged in")

    # 02 账龄 pivot（等 read_group 完成：加载圈消失 + 出现 pivot 表）
    pg.goto(BASE+"/odoo/action-554", wait_until="domcontentloaded")
    wait_for(pg, "table.o_list_table tbody tr", 600)   # 先等 list 数据
    pivot(pg)
    wait_for(pg, ".o_pivot table, table.o_pivot, .o_pivot_view", 60)
    # 等 pivot 数据行出现（非加载态）
    t0=time.time()
    while time.time()-t0<600:
        n = pg.evaluate("()=>document.querySelectorAll('.o_pivot tbody tr, table.o_pivot tbody tr').length")
        if n and n>1: break
        time.sleep(2)
    perf["aging_pivot_rows"]=pg.evaluate("()=>document.querySelectorAll('.o_pivot tbody tr, table.o_pivot tbody tr').length")
    shot(pg, "02-应收账龄-pivot.png", "aging_pivot")
    log("aging pivot rows: %s" % perf["aging_pivot_rows"])

    # 03/04 导游绩效
    pg.goto(BASE+"/odoo/action-555", wait_until="domcontentloaded")
    shot(pg, "03-导游绩效-list.png", "perf_list", "table.o_list_table tbody tr", 120)
    pivot(pg)
    shot(pg, "04-导游绩效-pivot.png", "perf_pivot", ".o_pivot tbody tr", 120)

    # 05/05b/06 景点毛利贡献
    pg.goto(BASE+"/odoo/action-556", wait_until="domcontentloaded")
    shot(pg, "05-景点毛利贡献-list.png", "scenic_list", "table.o_list_table tbody tr", 120)
    search(pg, "半坡")
    shot(pg, "05b-景点毛利贡献-半坡森林公园.png", "scenic_demo", "table.o_list_table tbody tr", 120)
    pivot(pg)
    shot(pg, "06-景点毛利贡献-pivot.png", "scenic_pivot", ".o_pivot tbody tr", 120)

    # 07/08 固定资产
    pg.goto(BASE+"/odoo/action-551", wait_until="domcontentloaded")
    shot(pg, "07-固定资产-list.png", "asset_list", "table.o_list_table tbody tr", 120)
    search(pg, "DEMO|FA001")
    open_row(pg)
    shot(pg, "08-固定资产-卡片.png", "asset_form", ".o_form_view", 60)
    pg.evaluate("""()=>{const els=[...document.querySelectorAll('.o-notebook-page, .o-group, section, .o-inner_group')];const el=els.find(x=>/折旧/.test(x.innerText||''));if(el)el.scrollIntoView({block:'center'});}""")
    settle(pg,1); pg.screenshot(path=os.path.join(OUT,"08b-固定资产-折旧表.png")); log("saved 08b")

    # 09/10 费用报销
    pg.goto(BASE+"/odoo/action-549", wait_until="domcontentloaded")
    shot(pg, "09-费用报销-list.png", "expense_list", "table.o_list_table tbody tr", 120)
    search(pg, "DEMO|EXP052")
    open_row(pg)
    shot(pg, "10-费用报销-approved草稿凭证.png", "expense_form", ".o_form_view", 60)
    pg.evaluate("""()=>{const els=[...document.querySelectorAll('.o-notebook-page, section, .o-group')];const el=els.find(x=>/凭证|会计/.test(x.innerText||''));if(el)el.scrollIntoView({block:'center'});}""")
    settle(pg,1); pg.screenshot(path=os.path.join(OUT,"10b-费用报销-凭证区.png")); log("saved 10b")

    # 11 ETM 订单表单
    pg.goto(BASE+"/odoo/action-540", wait_until="domcontentloaded")
    search(pg, "ETM|P35870")
    open_row(pg)
    shot(pg, "11-ETM订单-表单名单.png", "order_form", ".o_form_view", 120)
    tab = pg.query_selector(".o-notebook .nav-link:has-text('收款期次'), .o-notebook .nav-link:has-text('期次'), .o-notebook .nav-link:has-text('收款')")
    if tab:
        tab.click(); settle(pg,3)
        pg.screenshot(path=os.path.join(OUT,"11b-ETM订单-收款期次页签.png")); log("saved 11b")
    else:
        notes.append("11b: 未找到收款期次页签")

    # 12 发团计划表单
    pg.goto(BASE+"/odoo/action-539", wait_until="domcontentloaded")
    search(pg, "ETM|D|811|2026-06-17")
    open_row(pg)
    shot(pg, "12-发团计划-表单.png", "dep_form", ".o_form_view", 120)
    pg.evaluate("""()=>{const els=[...document.querySelectorAll('.o-notebook-page, section, .o-group')];const el=els.find(x=>/计调|派工|条目/.test(x.innerText||''));if(el)el.scrollIntoView({block:'center'});}""")
    settle(pg,1); pg.screenshot(path=os.path.join(OUT,"12b-发团计划-计调条目.png")); log("saved 12b")

    # 13 单团损益
    pg.goto(BASE+"/odoo/action-542", wait_until="domcontentloaded")
    shot(pg, "13-单团损益-list.png", "pnl_list", "table.o_list_table tbody tr", 600)
    # 找有导游/费用的行：搜 DEMO 关联团 79814 对应 code
    search(pg, "ETM|D|811|2026-06-17")
    shot(pg, "13b-单团损益-DEMO团.png", "pnl_row", "table.o_list_table tbody tr", 600)

    br.close()

with open(os.path.join(OUT,"_notes.json"),"w") as f:
    json.dump({"perf":perf,"notes":notes,"console_errors":cerr[:60]}, f, ensure_ascii=False, indent=1)
log("ALL DONE")
