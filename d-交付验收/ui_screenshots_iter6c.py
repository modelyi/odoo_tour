# -*- coding: utf-8 -*-
# 迭代6 UI 截图（第三批：账龄pivot重拍 + 资产/费用/订单/发团/损益）
import os, time, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
OUT  = "/home/adai/tms/d-交付验收/截图-迭代6"
notes, perf, cerr = [], {}, []

def log(m): print(m, flush=True)
def settle(pg, s=2.0): time.sleep(s)

def wait_pred(pg, js, timeout=600, interval=2):
    t0=time.time()
    while time.time()-t0 < timeout:
        try:
            if pg.evaluate(js): return round(time.time()-t0,1)
        except Exception: pass
        time.sleep(interval)
    return -1

def dismiss(pg):
    try:
        pg.evaluate("""()=>{document.querySelectorAll('.o_dialog .btn-close,.o-notification-close,.o_onboarding_close_btn').forEach(b=>{try{b.click()}catch(e){}});}""")
    except Exception: pass

def shot(pg, name, key, wait_js=None, timeout=600):
    dismiss(pg)
    secs = wait_pred(pg, wait_js, timeout) if wait_js else 2
    settle(pg, 2); dismiss(pg)
    pg.screenshot(path=os.path.join(OUT, name))
    perf[key]=secs
    notes.append(f"{name} | {pg.url} | wait={secs}s")
    log(f"saved {name} wait={secs}s")

def pivot(pg):
    b = pg.query_selector("button.o_switch_view.o_pivot")
    if b: b.click(); return True
    return False

def search(pg, term):
    inp = pg.query_selector(".o_searchview input")
    if not inp: return False
    inp.click(); inp.fill(term); settle(pg,1.5); inp.press("Enter")
    wait_pred(pg, """()=>{const el=document.querySelector('.o_loading_indicator'); return !el || getComputedStyle(el).display==='none'}""", 300)
    settle(pg,1)
    return True

def row_count(pg):
    return pg.evaluate("()=>document.querySelectorAll('table.o_list_table tbody tr').length")

def open_first_row(pg):
    n = row_count(pg)
    if not n:
        log("no rows to open")
        return False
    cell = pg.locator("table.o_list_table tbody tr").first.locator(".o_data_cell").first
    cell.click(timeout=20000)
    wait_pred(pg, "()=>!!document.querySelector('.o_form_view')", 60)
    return True

def step(fn, *a, **k):
    try: return fn(*a, **k)
    except Exception as e:
        log(f"STEP FAIL: {type(e).__name__}: {str(e)[:150]}")
        return None

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    pg = br.new_context(viewport={"width":1440,"height":1000}).new_page()
    pg.on("console", lambda m: cerr.append(m.text[:200]) if m.type=="error" else None)
    pg.on("pageerror", lambda e: cerr.append(f"pageerror:{e}"))
    step(lambda: (pg.goto(BASE+"/web/login", wait_until="domcontentloaded"), settle(pg,1),
                  pg.fill("#login","admin"), pg.fill("#password", os.environ.get("ODOO_TEST_PASS","admin")), pg.click("button[type=submit]"),
                  pg.wait_for_selector("nav", timeout=40000), settle(pg,2)))
    log("logged in")

    # --- 02 账龄 pivot 重拍：等 pivot 总计行数字稳定 ---
    step(lambda: pg.goto(BASE+"/odoo/action-554", wait_until="domcontentloaded"))
    step(wait_pred, pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 600)
    step(pivot, pg)
    step(wait_pred, pg, "()=>{const t=document.querySelector('.o_pivot'); return t && t.innerText.includes('总计') && !document.querySelector('.o_loading_indicator')}", 600)
    # 数字稳定判定：连续两次取总计行文本相同
    prev=None
    for _ in range(10):
        cur = pg.evaluate("()=>{const r=document.querySelector('.o_pivot tr'); return r?r.innerText.replace(/\\s+/g,' '):''}")
        if cur and cur==prev: break
        prev=cur; settle(pg,3)
    perf["aging_pivot_total_row"]=prev
    log("pivot total row: "+str(prev))
    shot(pg, "02-应收账龄-pivot.png", "aging_pivot2")

    # --- 07/08 固定资产 ---
    step(lambda: pg.goto(BASE+"/odoo/action-551", wait_until="domcontentloaded"))
    step(wait_pred, pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 120)
    step(open_first_row, pg)
    shot(pg, "08-固定资产-卡片.png", "asset_form", "()=>!!document.querySelector('.o_form_view')", 60)
    pg.evaluate("""()=>{const els=[...document.querySelectorAll('.o-notebook-page, section, .o-group, .o-inner_group')];const el=els.find(x=>/折旧/.test(x.innerText||''));if(el)el.scrollIntoView({block:'center'});}""")
    settle(pg,1); pg.screenshot(path=os.path.join(OUT,"08b-固定资产-折旧表.png")); log("saved 08b")

    # --- 09/10 费用报销 ---
    step(lambda: pg.goto(BASE+"/odoo/action-549", wait_until="domcontentloaded"))
    step(wait_pred, pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 120)
    step(search, pg, "EXP052")
    log("expense rows after search: %s" % row_count(pg))
    step(open_first_row, pg)
    shot(pg, "10-费用报销-approved草稿凭证.png", "expense_form", "()=>!!document.querySelector('.o_form_view')", 60)
    pg.evaluate("""()=>{const els=[...document.querySelectorAll('.o-notebook-page, section, .o-group')];const el=els.find(x=>/凭证|会计分录|日记账/.test(x.innerText||''));if(el)el.scrollIntoView({block:'center'});}""")
    settle(pg,1); pg.screenshot(path=os.path.join(OUT,"10b-费用报销-凭证区.png")); log("saved 10b")

    # --- 11 ETM 订单表单 ---
    step(lambda: pg.goto(BASE+"/odoo/action-540", wait_until="domcontentloaded"))
    step(wait_pred, pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 300)
    step(search, pg, "ETM|P35870")
    log("order rows after search: %s" % row_count(pg))
    step(open_first_row, pg)
    shot(pg, "11-ETM订单-表单名单.png", "order_form", "()=>!!document.querySelector('.o_form_view')", 120)
    tabs = pg.query_selector_all(".o-notebook .nav-link, .o-inner_group .nav-link")
    names = [t.inner_text() for t in tabs]
    log("order tabs: %s" % names)
    for want in ["收款期次", "期次", "收款"]:
        for t in tabs:
            if want in (t.inner_text() or ""):
                step(lambda: t.click()); settle(pg,3)
                pg.screenshot(path=os.path.join(OUT, f"11b-ETM订单-{want}页签.png")); log("saved 11b "+want)
                break
        else: continue
        break

    # --- 12 发团计划表单 ---
    step(lambda: pg.goto(BASE+"/odoo/action-539", wait_until="domcontentloaded"))
    step(wait_pred, pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 300)
    step(search, pg, "ETM|D|811|2026-06-17")
    log("dep rows after search: %s" % row_count(pg))
    step(open_first_row, pg)
    shot(pg, "12-发团计划-表单.png", "dep_form", "()=>!!document.querySelector('.o_form_view')", 120)
    tabs2 = pg.query_selector_all(".o-notebook .nav-link")
    log("dep tabs: %s" % [t.inner_text() for t in tabs2])
    for want in ["计调", "派工", "条目"]:
        hit=False
        for t in tabs2:
            if want in (t.inner_text() or ""):
                step(lambda: t.click()); settle(pg,3)
                pg.screenshot(path=os.path.join(OUT, f"12b-发团计划-{want}页签.png")); log("saved 12b "+want); hit=True
                break
        if hit: break

    # --- 13 单团损益 ---
    step(lambda: pg.goto(BASE+"/odoo/action-542", wait_until="domcontentloaded"))
    shot(pg, "13-单团损益-list.png", "pnl_list", "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 600)
    # 展开列找导游/费用口径列：横向滚动截图
    pg.evaluate("()=>{const el=document.querySelector('.o_list_table'); if(el){const w=el.parentElement; w.scrollLeft=400;}}")
    settle(pg,1); pg.screenshot(path=os.path.join(OUT,"13b-单团损益-右侧列.png")); log("saved 13b")

    br.close()

with open(os.path.join(OUT,"_notes3.json"),"w") as f:
    json.dump({"perf":perf,"notes":notes,"console_errors":cerr[:60]}, f, ensure_ascii=False, indent=1)
log("ALL DONE")
