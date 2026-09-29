# -*- coding: utf-8 -*-
# 迭代6 UI 截图（第四批：费用列表 / 订单收款期次页签 / 单团损益DEMO团）
import os, time, json
from playwright.sync_api import sync_playwright
BASE="http://localhost:8079"; OUT="/home/adai/tms/d-交付验收/截图-迭代6"
notes=[]
def log(m): print(m, flush=True)
def settle(s=2): time.sleep(s)
def wait_pred(pg, js, timeout=300):
    t0=time.time()
    while time.time()-t0<timeout:
        try:
            if pg.evaluate(js): return round(time.time()-t0,1)
        except Exception: pass
        time.sleep(1)
    return -1
with sync_playwright() as p:
    br=p.chromium.launch(headless=True)
    pg=br.new_context(viewport={"width":1440,"height":1000}).new_page()
    cerr=[]
    pg.on("pageerror", lambda e: cerr.append(str(e)[:200]))
    pg.goto(BASE+"/web/login", wait_until="domcontentloaded"); settle(1)
    pg.fill("#login","admin"); pg.fill("#password","admin"); pg.click("button[type=submit]")
    pg.wait_for_selector("nav", timeout=40000); settle(2)
    # 09 费用报销 list（混合状态）
    pg.goto(BASE+"/odoo/action-549", wait_until="domcontentloaded")
    wait_pred(pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 120)
    settle(2); pg.screenshot(path=os.path.join(OUT,"09-费用报销-list.png")); notes.append("09 ok")
    # 11b 订单收款期次页签
    pg.goto(BASE+"/odoo/action-540", wait_until="domcontentloaded")
    wait_pred(pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 120)
    inp=pg.query_selector(".o_searchview input"); inp.click(); inp.fill("ETM|P35870"); settle(1); inp.press("Enter")
    wait_pred(pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length==1", 120)
    pg.locator("table.o_list_table tbody tr").first.locator(".o_data_cell").first.click(timeout=20000)
    wait_pred(pg, "()=>!!document.querySelector('.o_form_view')", 60)
    tab=pg.get_by_text("收款期次", exact=True).first
    tab.click(); settle(3)
    pg.screenshot(path=os.path.join(OUT,"11b-ETM订单-收款期次页签.png")); notes.append("11b ok")
    # 13b 单团损益 DEMO 团行
    pg.goto(BASE+"/odoo/action-542", wait_until="domcontentloaded")
    wait_pred(pg, "()=>document.querySelectorAll('table.o_list_table tbody tr').length>0", 600)
    inp=pg.query_selector(".o_searchview input"); inp.click(); inp.fill("ETM|D|811|2026-06-17"); settle(1); inp.press("Enter")
    t=wait_pred(pg, "()=>{const r=document.querySelectorAll('table.o_list_table tbody tr'); return r.length>0 && r.length<10}", 600)
    log("pnl search wait=%s rows=%s" % (t, pg.evaluate("()=>document.querySelectorAll('table.o_list_table tbody tr').length")))
    settle(2); pg.screenshot(path=os.path.join(OUT,"13b-单团损益-DEMO团.png")); notes.append("13b ok")
    br.close()
with open(os.path.join(OUT,"_notes4.json"),"w") as f:
    json.dump({"notes":notes,"pageerrors":cerr}, f, ensure_ascii=False)
log("DONE4")
