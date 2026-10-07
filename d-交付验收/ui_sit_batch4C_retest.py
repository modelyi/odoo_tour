# -*- coding: utf-8 -*-
"""批4-C 购物返佣 UI 复测 v2（只读）· 修复②③验证 + 仿真数据取证
只导航/搜索/打开表单/截图，严禁点击 新建/保存/确认/结算 等写操作按钮。
口令经环境变量 ODOO_TEST_PASS 注入（默认 admin），不落盘不打印。
截图目录：/home/adai/tms/d-交付验收/截图-批4/（文件名 18- 起）。
Odoo 20 DOM 说明：列表头取 .o_list_table thead th；状态栏按钮取 .o_arrow_button（当前态
o_arrow_button_current）；表单组标题为 DIV.o_horizontal_separator。
"""
import os, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
SHOT = "/home/adai/tms/d-交付验收/截图-批4"
ADMIN_PW = os.environ.get("ODOO_TEST_PASS") or "admin"

T0 = time.time()
STEPS = []
CONSOLE = []

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

def elshot(pg, loc, name):
    path = os.path.join(SHOT, name)
    try:
        loc.screenshot(path=path)
        log(f"[SHOT] {name}")
    except Exception as e:
        shot(pg, name)
        log(f"[SHOT fallback] {name}: {e}")

def goto(pg, url, settle=2.5):
    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        pg.wait_for_selector(".o_control_panel, .o_view_controller, .o_form_view", timeout=20000)
    except Exception:
        pass
    time.sleep(settle)

def dismiss(pg):
    try:
        pg.evaluate("""() => { document.querySelectorAll('.o_notification_close, .o_onboarding_btn_close, .o_onboarding_close_btn').forEach(b=>{try{b.click()}catch(e){}}); }""")
        pg.keyboard.press("Escape")
    except Exception:
        pass

def row_count(pg):
    return len(pg.query_selector_all(".o_data_row"))

def search_freetext(pg, text, settle=2.5):
    inp = pg.locator(".o_searchview_input").first
    inp.click()
    inp.fill(text)
    time.sleep(1.2)
    inp.press("Enter")
    time.sleep(settle)
    dismiss(pg)
    return row_count(pg)

def headers(pg):
    try:
        return [t.inner_text().strip() for t in pg.query_selector_all(".o_list_table thead th") if t.inner_text().strip()]
    except Exception:
        return []

def state_cell(pg):
    """读取首行状态列单元格（表头为中文'状态'或英文'State'均可定位）"""
    hs = headers(pg)
    label = "状态" if "状态" in hs else ("State" if "State" in hs else None)
    if not label:
        return None
    i = hs.index(label) + 1   # +1：首列选择框 td 无表头
    rows = pg.query_selector_all(".o_data_row")
    if not rows:
        return None
    cells = rows[0].query_selector_all("td")
    if i < len(cells):
        return (cells[i].inner_text() or "").strip()
    return None

def norm(s):
    return (s or "").replace(",", "").replace(" ", "").replace("\u00a0", "").replace("\u2009", "")

def open_first_row(pg, key, settle=2.5):
    pg.locator(".o_data_row", has_text=key).first.click()
    try:
        pg.wait_for_selector(".o_form_view", timeout=15000)
    except Exception:
        pass
    time.sleep(settle)

def form_text(pg):
    try:
        return pg.locator(".o_form_view").first.inner_text()
    except Exception:
        return ""

def statusbar(pg):
    """Odoo 20 状态栏：o_arrow_button 按钮列表 + 当前态"""
    try:
        btns = pg.evaluate("""() => Array.from(document.querySelectorAll('.o_form_view .o_arrow_button')).map(b => ({t: b.innerText.trim(), cur: b.classList.contains('o_arrow_button_current')}))""")
        return btns
    except Exception:
        return []

def form_tables(pg):
    try:
        return pg.evaluate("""() => Array.from(document.querySelectorAll('.o_form_view table.o_list_table')).map(t => ({rows: t.querySelectorAll('.o_data_row').length, text: t.innerText}))""")
    except Exception:
        return []

def main():
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        ctx = br.new_context(viewport={"width": 1680, "height": 1000})
        ctx.set_default_timeout(20000)
        pg = ctx.new_page()

        def on_console(msg):
            if msg.type == "error":
                CONSOLE.append(f"[console.error] {msg.text[:200]}")
        def on_pageerror(err):
            CONSOLE.append(f"[pageerror] {str(err)[:200]}")
        pg.on("console", on_console)
        pg.on("pageerror", on_pageerror)

        # ---- 登录 ----
        pg.goto(BASE + "/web/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.5)
        pg.fill("#login", "admin")
        pg.fill("#password", ADMIN_PW)
        pg.click("button[type=submit]")
        try:
            pg.wait_for_selector("nav", timeout=30000)
            ok = True
        except Exception:
            ok = False
        time.sleep(2.5)
        rec("login", "PASS" if ok else "FAIL", "admin 登录")
        if not ok:
            br.close()
            return

        # ================= 1 购物记录（action-558）=================
        try:
            goto(pg, f"{BASE}/odoo/action-558")
            n = search_freetext(pg, "GW00005")
            hs = headers(pg)
            hdr_cn = "状态" in hs
            hdr_en = "State" in hs
            sc = state_cell(pg)
            try:
                pg.locator(".o_data_row", has_text="GW00005").first.scroll_into_view_if_needed()
            except Exception:
                pass
            shot(pg, "18-购物记录-列表-GW00005.png")
            rec("1-购物记录列表", "PASS" if (n == 1 and hdr_cn and not hdr_en and sc == "已确认") else "FAIL",
                f"行数={n} 表头含'状态'={hdr_cn} 表头为'State'={hdr_en} 状态值={sc}")

            if n == 1:
                open_first_row(pg, "GW00005")
                ft = norm(form_text(pg))
                lbls = ["发团计划", "购物店", "购物日期", "参与购物客人数", "购物总金额", "人均购物", "导游"]
                miss = [x for x in lbls if x not in ft]
                vals = ["BQ00266", "翡翠购物店", "10000.00", "833.33", "批4购物导游"]
                vmiss = [x for x in vals if x not in ft]
                dval = ""
                try:
                    dval = pg.locator(".o_form_view input[name='shop_date']").first.input_value(timeout=2500)
                except Exception:
                    pass
                if not dval:
                    try:
                        dval = pg.locator(".o_form_view [name='shop_date']").first.inner_text(timeout=2500)
                    except Exception:
                        pass
                date_ok = any(k in (dval or "") for k in ["2026-10-07", "10/07/2026", "2026/10/07", "10月7日"])
                sb = statusbar(pg)
                sb_ok = any(b["t"] == "已确认" and b["cur"] for b in sb)
                shot(pg, "19-购物记录-GW00005-表单.png")
                rec("1-购物记录表单", "PASS" if (not miss and not vmiss and date_ok and sb_ok) else "FAIL",
                    f"字段缺失={miss or '无'} 值缺失={vmiss or '无'} 购物日期[{dval}]={date_ok} 状态栏当前={sb}")
        except Exception as e:
            rec("1-购物记录", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 2 购物店返佣协议（action-559）=================
        try:
            goto(pg, f"{BASE}/odoo/action-559")
            n = search_freetext(pg, "XY0005")
            hs = headers(pg)
            hdr_cn = "状态" in hs
            hdr_en = "State" in hs
            sc = state_cell(pg)
            shot(pg, "20-购物店返佣协议-列表-XY0005.png")
            rec("2-返佣协议列表", "PASS" if (n == 1 and hdr_cn and not hdr_en and sc == "生效") else "FAIL",
                f"行数={n} 表头含'状态'={hdr_cn} 表头为'State'={hdr_en} 状态值={sc}")

            if n == 1:
                open_first_row(pg, "XY0005")
                ft = norm(form_text(pg))
                base_ok = "基础返佣比例" in ft and "15.00" in ft
                tbls = form_tables(pg)
                tier = None
                for t in tbls:
                    if "返佣比例" in t["text"] and "人均购物下限" in t["text"]:
                        tier = t
                        break
                trows = tier["rows"] if tier else -1
                ttxt = norm(tier["text"]) if tier else ""
                tier_ok = trows == 3 and all(k in ttxt for k in ["0.00", "1000.00", "20.00", "5000.00", "25.00", "30.00"])
                elshot(pg, pg.locator(".o_form_view"), "21-购物店返佣协议-XY0005-表单.png")
                rec("2-返佣协议表单", "PASS" if (base_ok and tier_ok) else "FAIL",
                    f"基础比例15.00可见={base_ok} 阶梯行数={trows} 阶梯数值齐全={tier_ok}")
        except Exception as e:
            rec("2-返佣协议", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 3 司陪导协议（action-560）=================
        try:
            goto(pg, f"{BASE}/odoo/action-560")
            n = search_freetext(pg, "SP0005")
            hs = headers(pg)
            hdr_cn = "状态" in hs
            hdr_en = "State" in hs
            sc = state_cell(pg)
            shot(pg, "22-司陪导协议-列表-SP0005.png")
            rec("3-司陪导协议列表", "PASS" if (n == 1 and hdr_cn and not hdr_en and sc == "生效") else "FAIL",
                f"行数={n} 表头含'状态'={hdr_cn} 表头为'State'={hdr_en} 状态值={sc}")

            if n == 1:
                open_first_row(pg, "SP0005")
                ft = norm(form_text(pg))
                field_ok = all(k in ft for k in ["导游", "40.00", "劳务报酬"])
                tbls = form_tables(pg)
                prem = None
                for t in tbls:
                    if "奖金金额" in t["text"] and "人均购物下限" in t["text"]:
                        prem = t
                        break
                prows = prem["rows"] if prem else -1
                ptxt = norm(prem["text"]) if prem else ""
                prem_ok = prows == 2 and "2500.00" in ptxt and "5000.00" in ptxt
                elshot(pg, pg.locator(".o_form_view"), "23-司陪导协议-SP0005-表单.png")
                rec("3-司陪导协议表单", "PASS" if (field_ok and prem_ok) else "FAIL",
                    f"导游/40/劳务报酬可见={field_ok} 奖金规则行数={prows} 数值(2500/5000)={prem_ok}")
        except Exception as e:
            rec("3-司陪导协议", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 4 导游佣金 YJ00068（action-547）=================
        try:
            goto(pg, f"{BASE}/odoo/action-547")
            n = search_freetext(pg, "YJ00068")
            if n >= 1:
                open_first_row(pg, "YJ00068")
                # 4a 购物返佣字段组（Odoo 20 组标题 = DIV.o_horizontal_separator）
                ft = norm(form_text(pg))
                sep = pg.locator(".o_form_view .o_horizontal_separator", has_text="购物返佣").first
                g_visible = False
                try:
                    g_visible = sep.is_visible(timeout=3000)
                except Exception:
                    g_visible = False
                need = ["翡翠购物店", "10000.00", "833.33", "20.00", "2000.00", "800.00", "0.00", "1200.00"]
                miss = [x for x in need if x not in ft]
                lbls = ["购物店", "购物金额", "人均购物", "返佣比例", "佣金总额", "导游税前分成", "代扣个税", "旅行社留存"]
                lmiss = [x for x in lbls if x not in ft]
                elshot(pg, pg.locator(".o_form_view"), "25-导游佣金-YJ00068-购物返佣字段组.png")
                rec("4a-购物返佣字段组", "PASS" if (g_visible and not miss and not lmiss) else "FAIL",
                    f"组标题可见={g_visible} 值缺失={miss or '无'} 标签缺失={lmiss or '无'}")

                # 4b 状态栏四态（重点：已取消是否可见）
                sb = statusbar(pg)
                texts = [b["t"] for b in sb]
                st4 = all(k in texts for k in ["待确认", "已确认", "已结算", "已取消"])
                cur = next((b["t"] for b in sb if b["cur"]), "")
                rec("4b-状态栏四态", "PASS" if (st4 and cur == "已确认") else "FAIL",
                    f"状态按钮={texts} 含'已取消'={'已取消' in texts} 当前态={cur or '未识别'}")

                # 4c 个税代扣代缴记录
                tbls = form_tables(pg)
                tax = None
                for t in tbls:
                    if "申报月份" in t["text"] and "申报状态" in t["text"]:
                        tax = t
                        break
                trows = tax["rows"] if tax else -1
                ttxt = norm(tax["text"]) if tax else ""
                tax_ok = trows == 1 and "800.00" in ttxt and "批4购物导游" in ttxt and "劳务报酬" in ttxt
                elshot(pg, pg.locator(".o_form_view"), "26-导游佣金-YJ00068-个税代扣代缴记录.png")
                rec("4c-个税代扣记录", "PASS" if tax_ok else "FAIL",
                    f"记录行数={trows} 内容(800.00/导游/劳务报酬)={tax_ok}")
                shot(pg, "24-导游佣金-YJ00068-表单.png")
            else:
                shot(pg, "24-导游佣金-YJ00068-表单.png")
                rec("4-导游佣金YJ00068", "FAIL", f"搜索行数={n}")
        except Exception as e:
            rec("4-导游佣金YJ00068", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 5 回归：导游佣金列表 =================
        try:
            goto(pg, f"{BASE}/odoo/action-547")
            n0 = row_count(pg)
            n1 = search_freetext(pg, "YJ00065")
            sc = state_cell(pg)
            try:
                pg.locator(".o_data_row", has_text="YJ00065").first.scroll_into_view_if_needed()
            except Exception:
                pass
            shot(pg, "27-导游佣金-列表-回归-YJ00065.png")
            rec("5-佣金列表回归", "PASS" if (n0 > 0 and n1 == 1 and sc == "已结算") else "FAIL",
                f"列表首屏行数={n0} 搜YJ00065行数={n1} 状态值={sc}")
        except Exception as e:
            rec("5-佣金列表回归", "FAIL", f"异常 {str(e)[:120]}")

        br.close()

    fails = sum(1 for _, st, _ in STEPS if st == "FAIL")
    print("\n===== SUMMARY =====")
    for tag, st, dt in STEPS:
        print(f"{st:5s} | {tag:16s} | {dt}")
    print(f"\n共 {len(STEPS)} 步，FAIL={fails}")
    if CONSOLE:
        print("\n===== CONSOLE ERRORS =====")
        seen = []
        for c in CONSOLE:
            if c not in seen:
                seen.append(c)
        for c in seen[:25]:
            print(" ", c)
        print(f"（去重后 {len(seen)} 条）")
    else:
        print("\nCONSOLE ERRORS: 无")

if __name__ == "__main__":
    main()
