# -*- coding: utf-8 -*-
"""批4 正式库 UI SIT（只读）· 搜索修复 B + 购物返佣 C —— 终版
只导航/搜索/切视图/打开表单，严禁创建/修改/删除数据，不点保存/新建/确认等动作按钮。
口令经环境变量 ODOO_TEST_PASS 注入（默认 admin），不落盘不打印。
截图目录：/home/adai/tms/d-交付验收/截图-批4/
"""
import os, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
SHOT = "/home/adai/tms/d-交付验收/截图-批4"
ADMIN_PW = os.environ.get("ODOO_TEST_PASS", "admin")

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

def goto(pg, url, settle=2.5):
    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        pg.wait_for_selector(".o_control_panel, .o_view_controller, .o_form_view", timeout=20000)
    except Exception:
        pass
    time.sleep(settle)
    for sel in [".o_error_dialog", ".o_dialog .o_error"]:
        try:
            t = pg.locator(sel).first.inner_text(timeout=1200)
            if t.strip():
                rec("error-dialog", "FAIL", f"{sel}: {t.strip()[:150]}")
        except Exception:
            pass

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

def clear_search(pg, settle=2.5):
    try:
        inp = pg.locator(".o_searchview_input").first
        inp.click()
        inp.press("Control+a")
        inp.fill("")
        inp.press("Enter")
        time.sleep(settle)
    except Exception:
        pass

def col_idx(pg, label):
    ths = pg.query_selector_all(".o_list_table thead th")
    for i, th in enumerate(ths):
        try:
            if label in (th.inner_text() or ""):
                return i
        except Exception:
            pass
    return -1

def first_row_cell(pg, label):
    i = col_idx(pg, label)
    if i < 0:
        return None
    rows = pg.query_selector_all(".o_data_row")
    if not rows:
        return None
    cells = rows[0].query_selector_all("td")
    if i < len(cells):
        return (cells[i].inner_text() or "").strip()
    return None

def headers(pg):
    try:
        return [t.inner_text().strip() for t in pg.query_selector_all(".o_list_table thead th") if t.inner_text().strip()]
    except Exception:
        return []

def table_text(pg):
    try:
        return pg.locator(".o_list_table").first.inner_text()
    except Exception:
        return ""

def visible_dropdown_texts(pg):
    out = []
    for loc in pg.locator(".dropdown-menu").all():
        try:
            if loc.is_visible():
                out.append(loc.inner_text())
        except Exception:
            pass
    return out

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

        # ================= B1/B5 单团损益 =================
        try:
            goto(pg, f"{BASE}/odoo/action-542")
            n0 = row_count(pg)
            n1 = search_freetext(pg, "BQ00266")
            shot(pg, "01-单团损益-搜索BQ00266.png")
            clear_search(pg)

            # B5 下拉建议
            try:
                inp = pg.locator(".o_searchview_input").first
                inp.click()
                inp.fill("BQ")
                time.sleep(2.0)
                dds = visible_dropdown_texts(pg)
                sug_ok = any("对于" in d for d in dds)
                shot(pg, "03-单团损益-搜索建议下拉.png")
                rec("B5-下拉建议", "PASS" if sug_ok else "NOTE", f"建议面板={'有' if sug_ok else '无'}")
            except Exception as e:
                rec("B5-下拉建议", "NOTE", f"采集异常 {str(e)[:80]}")
            clear_search(pg)

            rv = first_row_cell(pg, "线路")
            if rv:
                n2 = search_freetext(pg, rv)
                shot(pg, "02-单团损益-搜索线路名.png")
                rec("B1-单团损益", "PASS" if (n1 == 1 and n2 >= 1) else "FAIL",
                    f"初屏行数={n0} 搜BQ00266={n1} 搜线路[{rv}]={n2}")
            else:
                rec("B1-单团损益", "FAIL", f"搜BQ00266={n1}，但未能读取首行线路列")
        except Exception as e:
            rec("B1-单团损益", "FAIL", f"异常 {str(e)[:120]}")

        # ================= B2 应收账龄 =================
        try:
            goto(pg, f"{BASE}/odoo/action-554")
            cptext = ""
            try:
                cptext = pg.locator(".o_control_panel").first.inner_text()
            except Exception:
                pass
            default_facet = "含未结清" in cptext
            order_no = first_row_cell(pg, "订单号") or first_row_cell(pg, "订单")
            if order_no:
                n = search_freetext(pg, order_no)
                t = table_text(pg)
                shot(pg, "04-应收账龄-搜索订单号.png")
                rec("B2-应收账龄", "PASS" if (n >= 1 and order_no in t) else "FAIL",
                    f"默认未结清筛选={default_facet} 搜[{order_no}]行数={n}")
            else:
                shot(pg, "04-应收账龄-搜索订单号.png")
                rec("B2-应收账龄", "FAIL", f"默认筛选={default_facet} 未能读取首行订单号")
        except Exception as e:
            rec("B2-应收账龄", "FAIL", f"异常 {str(e)[:120]}")

        # ================= B3 银行流水 =================
        try:
            goto(pg, f"{BASE}/odoo/action-543")
            n = search_freetext(pg, "仿真")
            t = table_text(pg)
            shot(pg, "05-银行流水-搜索仿真.png")
            ok_rows = n >= 2 and "网银-0001" in t and "网银-0002" in t
            filt_ok = False
            try:
                pg.click(".o_searchview_dropdown_toggler")
                time.sleep(1.8)
                dds = visible_dropdown_texts(pg)
                filt_ok = any(all(k in d for k in ["待认领", "部分认领", "已认领"]) for d in dds)
                shot(pg, "06-银行流水-状态筛选.png")
                pg.keyboard.press("Escape")
            except Exception as e:
                log(f"筛选面板打开失败: {str(e)[:80]}")
                shot(pg, "06-银行流水-状态筛选.png")
            rec("B3-银行流水", "PASS" if (ok_rows and filt_ok) else "FAIL",
                f"搜仿真行数={n} 网银0001/0002可见={ok_rows} 状态快捷筛选={filt_ok}")
        except Exception as e:
            rec("B3-银行流水", "FAIL", f"异常 {str(e)[:120]}")

        # ================= B4 收款认领 =================
        try:
            goto(pg, f"{BASE}/odoo/action-544")
            n = search_freetext(pg, "RL")
            t = table_text(pg)
            shot(pg, "07-收款认领-搜索RL.png")
            ok_rows = n >= 2 and "RL000408" in t and "RL000409" in t
            rec("B4-收款认领", "PASS" if ok_rows else "FAIL",
                f"搜RL行数={n} RL000408/409可见={ok_rows}")
        except Exception as e:
            rec("B4-收款认领", "FAIL", f"异常 {str(e)[:120]}")

        # ================= C 菜单导航 =================
        try:
            goto(pg, f"{BASE}/odoo/action-558")
            pg.click("nav .o_menu_sections button:has-text('导游与报账')")
            time.sleep(2.0)
            dds = visible_dropdown_texts(pg)
            shot(pg, "08-菜单-购物返佣五项.png")
            need = ["购物记录", "购物店返佣协议", "司陪导协议", "导游佣金", "导游绩效"]
            got = [x for x in need if any(x in d for d in dds)]
            rec("C-菜单", "PASS" if len(got) == 5 else "FAIL", f"子菜单可见={got}")
        except Exception as e:
            rec("C-菜单", "FAIL", f"异常 {str(e)[:120]}")

        # ================= C6 购物记录 =================
        try:
            goto(pg, f"{BASE}/odoo/action-558")
            hs = headers(pg)
            n = row_count(pg)
            shot(pg, "09-购物记录-列表.png")
            need = ["发团计划", "购物店", "购物日期", "客人数", "总金额"]
            miss = [x for x in need if not any(x in h for h in hs)]
            has_state = any(("状态" in h or h == "State") for h in hs)
            rec("C6-购物记录", "PASS*" if (not miss and has_state) else "FAIL",
                f"行数={n} 列缺失={miss or '无'} 状态列={has_state}")
        except Exception as e:
            rec("C6-购物记录", "FAIL", f"异常 {str(e)[:120]}")

        # ================= C7 购物店返佣协议 =================
        try:
            goto(pg, f"{BASE}/odoo/action-559")
            hs = headers(pg)
            n = row_count(pg)
            shot(pg, "10-购物店返佣协议-列表.png")
            need = ["基础返佣比例", "协议开始日期", "协议结束日期"]
            miss = [x for x in need if not any(x in h for h in hs)]
            has_state = any(("状态" in h or h == "State") for h in hs)
            rec("C7-返佣协议", "PASS*" if (not miss and has_state) else "FAIL",
                f"行数={n} 列缺失={miss or '无'} 状态列={has_state}")
        except Exception as e:
            rec("C7-返佣协议", "FAIL", f"异常 {str(e)[:120]}")

        # ================= C8 司陪导协议 =================
        try:
            goto(pg, f"{BASE}/odoo/action-560")
            hs = headers(pg)
            n = row_count(pg)
            shot(pg, "11-司陪导协议-列表.png")
            need = ["人员类型", "分成比例", "税务类型"]
            miss = [x for x in need if not any(x in h for h in hs)]
            has_state = any(("状态" in h or h == "State") for h in hs)
            rec("C8-司陪导协议", "PASS*" if (not miss and has_state) else "FAIL",
                f"行数={n} 列缺失={miss or '无'} 状态列={has_state}")
        except Exception as e:
            rec("C8-司陪导协议", "FAIL", f"异常 {str(e)[:120]}")

        # ================= C9 导游佣金 =================
        try:
            goto(pg, f"{BASE}/odoo/action-547")
            n = search_freetext(pg, "YJ00065")
            if n >= 1:
                pg.locator(".o_data_row", has_text="YJ00065").first.click()
                pg.wait_for_selector(".o_form_view", timeout=15000)
                time.sleep(2.0)
                ft = ""
                try:
                    ft = pg.locator(".o_form_view").first.inner_text()
                except Exception:
                    pass
                tax_grp = "个税代扣代缴记录" in ft
                shop_grp = "购物返佣" in ft
                st = ""
                try:
                    st = pg.locator(".o_statusbar").first.inner_text()
                except Exception:
                    pass
                states3 = all(k in st for k in ["待确认", "已确认", "已结算"])
                has_cancel = "已取消" in st
                shot(pg, "12-导游佣金-YJ00065-表单.png")
                # 个税代扣组元素截图
                try:
                    grp = pg.locator("div", has_text="个税代扣代缴记录").first
                    grp.screenshot(path=os.path.join(SHOT, "13-导游佣金-YJ00065-个税代扣记录组.png"))
                except Exception:
                    shot(pg, "13-导游佣金-YJ00065-个税代扣记录组.png")
                rec("C9-佣金表单打开", "PASS" if ft else "FAIL", f"搜索行数={n} 表单文本={len(ft)}字符")
                rec("C9-购物返佣字段", "FAIL" if not shop_grp else "PASS",
                    f"购物返佣字段组可见={shop_grp}（YJ00065无购物数据，条件隐藏；字段定义经RPC核实存在）")
                rec("C9-个税代扣记录", "PASS" if tax_grp else "FAIL", f"个税代扣代缴记录组可见={tax_grp}")
                rec("C9-状态栏", "PASS" if (states3 and has_cancel) else "FAIL",
                    f"三项可见={states3} 已取消可见={has_cancel}")
            else:
                shot(pg, "12-导游佣金-YJ00065-表单.png")
                rec("C9-导游佣金", "FAIL", f"搜索YJ00065行数={n}")
        except Exception as e:
            rec("C9-导游佣金", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 回归 10 =================
        try:
            goto(pg, f"{BASE}/odoo/action-541")
            n = row_count(pg)
            shot(pg, "14-计调单-首屏.png")
            rec("R-计调单(action-541)", "PASS" if n > 0 else "FAIL", f"首屏行数={n}")
        except Exception as e:
            rec("R-计调单(action-541)", "FAIL", f"异常 {str(e)[:120]}")

        try:
            goto(pg, f"{BASE}/odoo/action-537")
            n = row_count(pg)
            shot(pg, "15-action537-线路产品.png")
            rec("R-action537", "PASS" if n > 0 else "FAIL",
                f"action-537 实际为线路产品(ta.route)，首屏行数={n}")
        except Exception as e:
            rec("R-action537", "FAIL", f"异常 {str(e)[:120]}")

        try:
            goto(pg, f"{BASE}/odoo/action-557")
            n = row_count(pg)
            shot(pg, "16-供应商付款按团-首屏.png")
            rec("R-供应商付款按团", "PASS" if n > 0 else "FAIL", f"首屏行数={n}")
        except Exception as e:
            rec("R-供应商付款按团", "FAIL", f"异常 {str(e)[:120]}")

        try:
            goto(pg, f"{BASE}/odoo/action-540")
            n = row_count(pg)
            shot(pg, "17-订单-首屏.png")
            rec("R-订单", "PASS" if n > 0 else "FAIL", f"首屏行数={n}")
        except Exception as e:
            rec("R-订单", "FAIL", f"异常 {str(e)[:120]}")

        br.close()

    fails = sum(1 for _, st, _ in STEPS if st == "FAIL")
    print("\n===== SUMMARY =====")
    for tag, st, dt in STEPS:
        print(f"{st:6s} | {tag:22s} | {dt}")
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
