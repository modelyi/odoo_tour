# -*- coding: utf-8 -*-
# 补拍：AC-02 pivot 视图 + AC-01 详细行程页签（改名重拍，空白占位行已被 devops 08:54 清理）
import os, time, json
from playwright.sync_api import sync_playwright
BASE = "http://localhost:8079"
OUT  = "/home/adai/tms/d-交付验收/截图-批3"
notes = []
def log(m): print(m, flush=True)
def settle(pg, s=1.2): time.sleep(s)
def wait_sel(pg, sel, cap=300):
    t0 = time.time()
    while time.time() - t0 < cap:
        if pg.query_selector_all(sel): return round(time.time()-t0,1)
        time.sleep(0.25)
    return -1

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    ctx = br.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    pg.goto(BASE + "/web/login", wait_until="domcontentloaded"); settle(pg, 1)
    pg.fill("#login", "admin"); pg.fill("#password", os.environ["ODOO_TEST_PASS"])
    pg.click("button[type=submit]"); pg.wait_for_selector("nav", timeout=60000); settle(pg, 2)

    # AC-02 pivot
    pg.goto(BASE + "/odoo/action-557", wait_until="domcontentloaded")
    wait_sel(pg, ".o_data_row"); settle(pg, 1)
    btns = pg.evaluate("""() => [...document.querySelectorAll('.o_view_switcher button, .o-switch-view button, [aria-label*="视图"], .o_control_panel button[data-view-type]')]
        .map(b => ({cls: b.className, dt: b.dataset.viewType||'', title: b.title||'', txt: (b.innerText||'').trim().slice(0,20), html: b.innerHTML.slice(0,60)}))""")
    notes.append("switcher buttons: " + json.dumps(btns, ensure_ascii=False))
    clicked = pg.evaluate("""() => {
        const cands = [...document.querySelectorAll('button')].filter(b =>
            (b.dataset.viewType === 'pivot') || /fa-pivot|fa-table/.test(b.innerHTML) && b.closest('.o_control_panel'));
        if (cands.length) { cands[0].click(); return cands[0].outerHTML.slice(0,120); }
        return null; }""")
    notes.append("pivot click: " + str(clicked))
    if clicked:
        t0 = time.time()
        ok = wait_sel(pg, ".o_pivot, table.o_pivot, .o_pivot_table, .o_view_renderer table", 240)
        notes.append(f"pivot render wait={ok}s elapsed={round(time.time()-t0,1)}")
        settle(pg, 1.5)
        pg.screenshot(path=os.path.join(OUT, "AC-02-供应商付款按团-pivot.png"))
        log("[SHOT] AC-02 pivot")
    else:
        pg.screenshot(path=os.path.join(OUT, "AC-02-供应商付款按团-无pivot按钮.png"))

    # AC-01 详细行程页签（route 212）
    pg.goto(BASE + "/odoo/action-537/212", wait_until="domcontentloaded")
    settle(pg, 2.5)
    tab = pg.query_selector(".o_notebook .nav-link:has-text('详细行程')")
    if tab:
        tab.click(); settle(pg, 2)
        n = len(pg.query_selector_all(".o_notebook .o_list_table tbody tr"))
        notes.append(f"AC-01 route212 stop rows now={n}")
        pg.screenshot(path=os.path.join(OUT, "AC-01-线路-详细行程页签.png"))
        pg.evaluate("() => {const t=document.querySelectorAll('.o_notebook .o_list_table tbody tr'); if(t.length>3) t[Math.floor(t.length/2)].scrollIntoView();}")
        settle(pg, 1)
        pg.screenshot(path=os.path.join(OUT, "AC-01-线路-详细行程页签-下半.png"))
        log(f"[SHOT] AC-01 rows={n}")
    br.close()
with open(os.path.join(OUT, "_notes_fix.json"), "w") as f:
    json.dump(notes, f, ensure_ascii=False, indent=1)
log("DONE")
