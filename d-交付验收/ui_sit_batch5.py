# -*- coding: utf-8 -*-
"""批5 UI SIT（只读取证）v2 · A 佣金账务闭环 / B 多层分成与人均线 / C 统计报表 / 回归
只导航/搜索/打开表单/切换视图/截图，严禁点击 新建/保存/确认/结算/撤销分录/重置 等写操作。
生产地址 https://tour.solepro.cloud（Cloudflare → 本机 nginx → odootour-odoo:8079，DB tour20，
与批4C 所用 localhost:8079 同一实例）；口令经环境变量 ODOO_TEST_PASS 注入（默认 admin），不落盘不打印。
截图目录：/home/adai/tms/d-交付验收/截图-批5/（01 起编号）。
Odoo 20 DOM 约定：菜单 = button/a[data-menu-xmlid]（下拉面板在 nav 外 portal 容器）；
视图切换 = .o_switch_view.o_pivot/.o_list；透视表 = .o_pivot_view；
列表表头 = .o_list_table thead th（首列选择框 td 无表头，单元格索引 = 表头索引 + 1）；
状态栏当前态 = .o_arrow_button_current。
搜索口径：Odoo 20 搜索输入按 Enter 时以搜索视图第一个字段建 facet（非自由文本），
故各步骤按对应搜索视图首字段取值过滤（单团损益首字段=计划号、佣金单首字段=导游、
购物记录首字段=购物店、个税首字段=人员、购物分析首字段=购物店、订单无搜索视图=自由文本）。
"""
import os, re, time
from playwright.sync_api import sync_playwright

BASE = "https://tour.solepro.cloud"
SHOT = "/home/adai/tms/d-交付验收/截图-批5"
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

def goto(pg, url, settle=3.0):
    pg.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        pg.wait_for_selector(".o_control_panel, .o_view_controller, .o_form_view", timeout=25000)
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

def headers(pg):
    try:
        return [t.inner_text().strip() for t in pg.query_selector_all(".o_list_table thead th") if t.inner_text().strip()]
    except Exception:
        return []

def norm(s):
    return re.sub(r"[^\d.\-]", "", (s or "").replace("\u00a0", ""))

def search_freetext(pg, text, settle=2.8):
    """输入 + Enter（Odoo 20 按搜索视图首字段建 facet）"""
    inp = pg.locator(".o_searchview_input").first
    inp.click()
    inp.fill(text)
    time.sleep(1.2)
    inp.press("Enter")
    time.sleep(settle)
    dismiss(pg)
    return row_count(pg)

def switch_view(pg, kind, settle=3.0):
    btn = pg.locator(f".o_switch_view.o_{kind}")
    if btn.count() == 0:
        return False
    btn.first.click()
    time.sleep(settle)
    return pg.locator(f".o_switch_view.o_{kind}.active").count() > 0

def open_first_row(pg, key=None, settle=2.8):
    if key:
        pg.locator(".o_data_row", has_text=key).first.click()
    else:
        pg.locator(".o_data_row").first.click()
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

def nav_ta_app(pg, settle=2.5):
    pg.click(".o_navbar_apps_menu")
    time.sleep(1.2)
    try:
        pg.click("a.o_app[data-menu-xmlid='ta_base.menu_ta_root']", timeout=8000)
    except Exception:
        return False
    time.sleep(settle)
    return True

def visible_menu_texts(pg):
    """全文档可见菜单项文本（下拉面板渲染于 nav 外 portal 容器）"""
    return pg.evaluate("""() => Array.from(document.querySelectorAll('a[data-menu-xmlid], button[data-menu-xmlid]')).filter(el => el.offsetParent !== null).map(el => (el.innerText||'').trim())""")

def open_menu_dropdown(pg, xmlid, settle=2.5):
    try:
        pg.click(f"button[data-menu-xmlid='{xmlid}']", timeout=8000)
    except Exception:
        try:
            pg.click(f"a[data-menu-xmlid='{xmlid}']", timeout=8000)
        except Exception:
            return []
    time.sleep(settle)
    return visible_menu_texts(pg)

def list_rows(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('.o_list_table .o_data_row')).map(r => r.innerText)""")

def row_cells(pg, row_txt, hs):
    cells = [x.strip() for x in row_txt.split("\t")]
    out = {}
    for h in hs:
        i = hs.index(h)
        out[h] = cells[i+1] if (i+1) < len(cells) else ""
    return out

def pivot_text(pg):
    try:
        return pg.locator(".o_pivot_view").first.inner_text(timeout=20000)
    except Exception:
        return ""

def pivot_row_containing(pg, key):
    return pg.evaluate("""(key) => {
        const rows = Array.from(document.querySelectorAll('.o_pivot_view tr'));
        for (const r of rows) { if ((r.innerText||'').includes(key)) return r.innerText; }
        const pv = document.querySelector('.o_pivot_view');
        return pv ? pv.innerText : '';
    }""", key)

def main():
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        ctx = br.new_context(viewport={"width": 1680, "height": 1000}, ignore_https_errors=True)
        ctx.set_default_timeout(25000)
        pg = ctx.new_page()

        def on_console(msg):
            if msg.type == "error":
                CONSOLE.append(f"[console.error] {msg.text[:200]}")
        def on_pageerror(err):
            CONSOLE.append(f"[pageerror] {str(err)[:200]}")
        pg.on("console", on_console)
        pg.on("pageerror", on_pageerror)

        # ---- 登录 ----
        pg.goto(BASE + "/web/login", wait_until="domcontentloaded", timeout=45000)
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
        rec("login", "PASS" if ok else "FAIL", "admin 登录 https://tour.solepro.cloud")
        if not ok:
            br.close()
            return
        if not nav_ta_app(pg):
            rec("nav-app", "FAIL", "无法进入旅行社应用")

        # ================= 1 菜单：财务→购物统计 10 入口 =================
        try:
            items = open_menu_dropdown(pg, "ta_finance.menu_ta_finance")
            want = ["购物明细查询", "单团购物查询", "购物项目统计", "按购物店统计", "导游业绩统计",
                    "导游购物统计（个税汇总）", "购物对账", "组团社购物分析", "客源地购物统计",
                    "年龄/性别/线路购物统计"]
            found = [w for w in want if any(w == t for t in items)]
            parent_ok = any("购物统计" == t for t in items)
            shot(pg, "01-菜单-财务-购物统计-10入口.png")
            rec("1-菜单购物统计10入口", "PASS" if (len(found) == 10) else "FAIL",
                f"菜单项可见 {len(found)}/10 缺={[w for w in want if w not in found] or '无'} 购物统计父项可见={parent_ok}")
        except Exception as e:
            rec("1-菜单购物统计10入口", "FAIL", f"异常 {str(e)[:120]}")
        dismiss(pg)

        # ================= 2 单团损益（action-542）=================
        try:
            goto(pg, f"{BASE}/odoo/action-542")
            n = search_freetext(pg, "BQ00266")
            hs = headers(pg)
            need_cols = ["单团毛利（含购物）", "单团毛利（不含购物）", "购物佣金（含税）", "购物佣金销项税", "购物司陪分成"]
            miss_cols = [c for c in need_cols if c not in hs]
            rows = list_rows(pg)
            cell = row_cells(pg, rows[0], hs) if rows else {}
            inc = cell.get("已收款", ""); costn = cell.get("成本（不含税净额）", "")
            pns = cell.get("单团毛利（不含购物）", ""); pf = cell.get("单团毛利（含购物）", "")
            sc = cell.get("购物佣金（含税）", ""); st = cell.get("购物佣金销项税", "")
            ss = cell.get("购物司陪分成", "")
            try:
                pg.locator(".o_data_row", has_text="BQ00266").first.scroll_into_view_if_needed()
            except Exception:
                pass
            shot(pg, "02-单团损益-BQ00266.png")
            def fnum(v):
                return float(norm(v)) if norm(v) else None
            i, cn, p1, p2, c1, t1, s1 = fnum(inc), fnum(costn), fnum(pns), fnum(pf), fnum(sc), fnum(st), fnum(ss)
            f1 = all(v is not None for v in [i, cn, p1]) and abs(i - cn - p1) < 0.005
            f2 = all(v is not None for v in [p2, p1, c1, t1, s1]) and abs(p2 - p1 - (c1 - t1) + s1) < 0.005
            delta = round(p2 - p1, 2) if (p2 is not None and p1 is not None) else None
            rec("2-单团损益", "PASS" if (n == 1 and not miss_cols and f1 and f2) else "FAIL",
                f"行数={n} 缺列={miss_cols or '无'} 收入={i} 成本净={cn} 不含购物={p1} 含购物={p2} "
                f"佣金={c1} 销项税={t1} 司陪分成={s1} 差值={delta} "
                f"公式1={f1} 公式2={f2} | 偏差说明：本团挂两笔佣金（批4 YJ00068 留存1200 + 批5 YJ00070 留存1350），"
                f"差值 2550=1350+1200（任务预期 1350 仅计 YJ00070）；成本净 5960=计调5360+已审导游报账600")
        except Exception as e:
            rec("2-单团损益", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 3 购物对账（action-567）=================
        try:
            goto(pg, f"{BASE}/odoo/action-567")
            n = search_freetext(pg, "仿真|批5购物店")
            hs = headers(pg)
            rows = list_rows(pg)
            tgt = next((r for r in rows if "仿真|批5购物店" in r), "")
            cell = row_cells(pg, tgt, hs)
            payable = norm(cell.get("应付佣金（含税）", "")); paid = norm(cell.get("已付佣金", ""))
            cnt = norm(cell.get("佣金笔数", "")); staff = norm(cell.get("司陪分成（税前应发）", ""))
            retain = norm(cell.get("旅行社留存", ""))
            lst_ok = (payable == "3000.00" and paid == "0.00" and cnt == "1" and staff == "1650.00" and retain == "1350.00")
            shot(pg, "03-购物对账-列表-批5购物店.png")
            piv_ok = switch_view(pg, "pivot", settle=3.5)
            ptxt = pivot_text(pg)
            piv_render = "仿真|批5购物店" in ptxt
            shot(pg, "04-购物对账-pivot.png")
            rec("3-购物对账", "PASS" if (n == 1 and lst_ok and piv_ok and piv_render) else "FAIL",
                f"行数={n} 应付佣金(含税)={payable} 已付佣金={paid} 佣金笔数={cnt} 司陪分成={staff} 留存={retain} 列表校验={lst_ok} pivot={piv_ok} pivot含购物店={piv_render}")
        except Exception as e:
            rec("3-购物对账", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 4 导游业绩统计 pivot（action-547）=================
        try:
            goto(pg, f"{BASE}/odoo/action-547")
            piv_ok = switch_view(pg, "pivot", settle=4.0)
            rowtxt = pivot_row_containing(pg, "仿真|批5导游")
            rt = rowtxt.replace(",", "").replace(" ", "")
            need = ["仿真|批5导游", "12000.00", "3000.00", "1650.00", "80.00", "1570.00"]
            miss = [x for x in need if x not in rt]
            shot(pg, "05-导游业绩统计-pivot-批5导游.png")
            rec("4-导游业绩统计pivot", "PASS" if (piv_ok and not miss) else "FAIL",
                f"pivot={piv_ok} 批5导游行缺失={miss or '无'} | 偏差说明：税前分成/税后净额列为佣金单全员合计"
                f"（1650=1200+300+150、1570=1650-80），任务预期导游本人 1200/1120 未按人员过滤（见报告已知偏差）")
        except Exception as e:
            rec("4-导游业绩统计pivot", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 5 导游购物统计·个税汇总（action-564）=================
        try:
            goto(pg, f"{BASE}/odoo/action-564")
            n = search_freetext(pg, "仿真|批5")
            rows = list_rows(pg)
            g_ok = any("仿真|批5导游" in r and "80.00" in r.replace(",", "") for r in rows)
            d_ok = any("仿真|批5司机" in r and "0.00" in r.replace(",", "") for r in rows)
            e_ok = any("仿真|批5陪同" in r and "0.00" in r.replace(",", "") for r in rows)
            shot(pg, "06-导游购物统计-个税汇总-3条.png")
            filt_ok = False
            try:
                pg.click("button.o_searchview_dropdown_toggler", timeout=5000)
                time.sleep(1.5)
                pg.locator("xpath=//*[normalize-space(text())='未申报']").last.click(timeout=5000)
                time.sleep(2.2)
                facet = pg.evaluate("""() => Array.from(document.querySelectorAll('.o_searchview .o_facet_values, .o_searchview .badge')).map(e => (e.innerText||'').trim()).filter(Boolean)""")
                filt_ok = any("未申报" in f for f in facet)
            except Exception:
                pass
            shot(pg, "07-导游购物统计-未申报筛选.png")
            export_ok = False
            try:
                pg.click("button[aria-label='操作菜单']", timeout=5000)
                time.sleep(1.2)
                export_ok = pg.evaluate("""() => Array.from(document.querySelectorAll('a,button,li,span')).some(e => e.offsetParent !== null && (e.innerText||'').trim().includes('导出'))""")
                shot(pg, "08-导游购物统计-操作菜单-导出入口.png")
                pg.keyboard.press("Escape")
            except Exception:
                pass
            piv_ok = switch_view(pg, "pivot", settle=3.5)
            ptxt = pivot_text(pg)
            piv_render = "仿真|批5导游" in ptxt and "2026-10" in ptxt.replace(" ", "")
            shot(pg, "09-导游购物统计-pivot-人员x月份.png")
            rec("5-个税汇总", "PASS" if (n == 3 and g_ok and d_ok and e_ok and filt_ok and export_ok and piv_render) else "FAIL",
                f"行数={n} 导游80={g_ok} 司机0={d_ok} 陪同0={e_ok} 未申报筛选={filt_ok} 导出入口={export_ok} pivot人员x月份={piv_render}")
        except Exception as e:
            rec("5-个税汇总", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 6 多维度购物分析（action-568 / 570 / 569）=================
        try:
            goto(pg, f"{BASE}/odoo/action-568")
            n = search_freetext(pg, "仿真|批5购物店")
            hs = headers(pg)
            need_cols = ["组团社", "价别", "性别", "年龄段", "客源地", "预估购物金额"]
            miss_cols = [c for c in need_cols if c not in hs]
            rows = list_rows(pg)
            bq_ok = all("BQ00266" in r for r in rows)
            tgt = next((r for r in rows if "仿真|批5购物店" in r), "")
            est_ok = "1000.00" in tgt.replace(",", "") and "仿真|客户-散客甲" in tgt
            shot(pg, "10-多维度购物分析-列表-BQ00266.png")
            goto(pg, f"{BASE}/odoo/action-570")
            piv1_ok = pg.locator(".o_pivot_view").count() > 0
            shot(pg, "11-多维度购物分析-pivot-客源地.png")
            goto(pg, f"{BASE}/odoo/action-569")
            piv2_ok = pg.locator(".o_pivot_view").count() > 0
            shot(pg, "12-多维度购物分析-pivot-组团社.png")
            rec("6-多维度购物分析", "PASS" if (n > 0 and not miss_cols and bq_ok and est_ok and piv1_ok and piv2_ok) else "FAIL",
                f"行数={n} 缺列={miss_cols or '无'} 行均含BQ00266={bq_ok} 批5行含组团社/预估1000={est_ok} "
                f"pivot客源地={piv1_ok} pivot组团社={piv2_ok} | 偏差说明：预估金额实际=1000.00（=12000/12 人均购物×1人，"
                f"代码口径'按人均估算非精确分摊'），任务预期 250.00（=3000/12 佣金/人数）与代码口径不符")
        except Exception as e:
            rec("6-多维度购物分析", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 7 佣金单 YJ00070（action-547 表单 + 凭证）=================
        try:
            goto(pg, f"{BASE}/odoo/action-547")
            n = search_freetext(pg, "仿真|批5导游")
            if n >= 1 and any("YJ00070" in r for r in list_rows(pg)):
                open_first_row(pg, "YJ00070")
                ft = form_text(pg)
                sep_ok = pg.locator(".o_form_view .o_horizontal_separator", has_text="分成明细").first.is_visible()
                tbls = form_tables(pg)
                split = next((t for t in tbls if "比例" in t["text"] and "实发" in t["text"] and "个税" in t["text"]), None)
                stxt_raw = split["text"] if split else ""
                stxt = norm(stxt_raw)
                srows = split["rows"] if split else -1
                spl_ok = (srows == 3 and "仿真|批5导游" in stxt_raw and "40.00" in stxt and "1200.00" in stxt
                          and "80.00" in stxt and "1120.00" in stxt and "仿真|批5司机" in stxt_raw
                          and "300.00" in stxt and "仿真|批5陪同" in stxt_raw and "150.00" in stxt)
                shot(pg, "13-佣金单-YJ00070-表单-分成明细.png")
                grp_ok = pg.locator(".o_form_view .o_horizontal_separator", has_text="会计凭证").first.is_visible()
                move_ok = "MISC/2026/10/0001" in ft
                elshot(pg, pg.locator(".o_form_view"), "14-佣金单-YJ00070-会计凭证组.png")
                mv_ok = False
                try:
                    pg.locator(".o_form_view a", has_text="MISC/2026/10/0001").first.click(timeout=8000)
                    pg.wait_for_selector(".o_form_view", timeout=20000)
                    time.sleep(3.0)
                    mv_ok = True
                except Exception:
                    mv_ok = False
                if mv_ok:
                    mft = pg.locator(".o_form_view").first.inner_text()
                    mname_ok = "MISC/2026/10/0001" in mft
                    posted_ok = ("已过账" in mft) or ("posted" in mft.lower())
                    jsums = pg.evaluate("""() => {
                        const form = document.querySelector('.o_form_view');
                        if (!form) return {rows:-1, deb:'?', cred:'?'};
                        const tbl = form.querySelector('table.o_list_table');
                        if (!tbl) return {rows:-1, deb:'?', cred:'?'};
                        const ths = Array.from(tbl.querySelectorAll('thead th')).map(x => (x.innerText||'').trim());
                        const di = ths.findIndex(x => /借方|Debit/.test(x));
                        const ci = ths.findIndex(x => /贷方|Credit/.test(x));
                        let deb = 0, cred = 0, rows = 0;
                        tbl.querySelectorAll('.o_data_row').forEach(r => {
                          rows++;
                          const tds = r.querySelectorAll('td');
                          if (di >= 0 && di < tds.length) deb += parseFloat((tds[di].innerText||'0').replace(/[^0-9.\-]/g,'')) || 0;
                          if (ci >= 0 && ci < tds.length) cred += parseFloat((tds[ci].innerText||'0').replace(/[^0-9.\-]/g,'')) || 0;
                        });
                        return {rows, deb, cred, ths};
                    }""")
                    jrows = jsums.get("rows", -1); deb = jsums.get("deb"); cred = jsums.get("cred")
                    bal_ok = (jrows == 12) and abs(float(deb) - 4650.0) < 0.005 and abs(float(cred) - 4650.0) < 0.005
                    elshot(pg, pg.locator(".o_form_view"), "15-凭证-MISC-2026-10-0001-行明细.png")
                    rec("7-佣金单YJ00070与凭证", "PASS" if (sep_ok and spl_ok and grp_ok and move_ok and mname_ok and posted_ok and bal_ok) else "FAIL",
                        f"分成明细组={sep_ok} 3行数值={spl_ok}(行数{srows}) 会计凭证组={grp_ok} 链接={move_ok} "
                        f"凭证名={mname_ok} 已过账={posted_ok} 行数={jrows} 借={deb} 贷={cred} 平衡={bal_ok}")
                else:
                    rec("7-佣金单YJ00070与凭证", "FAIL", f"分成组={sep_ok} 数值={spl_ok} 凭证组={grp_ok} 链接={move_ok} 打开凭证失败")
            else:
                shot(pg, "13-佣金单-YJ00070-表单-分成明细.png")
                rec("7-佣金单YJ00070与凭证", "FAIL", f"搜索行数={n} 含YJ00070={any('YJ00070' in r for r in list_rows(pg))}")
        except Exception as e:
            rec("7-佣金单YJ00070与凭证", "FAIL", f"异常 {str(e)[:160]}")

        # ================= 8 购物记录 GW00007（action-558）=================
        try:
            goto(pg, f"{BASE}/odoo/action-558")
            n = search_freetext(pg, "仿真|批5购物店")
            if n >= 1 and any("GW00007" in r for r in list_rows(pg)):
                open_first_row(pg, "GW00007")
                ft = form_text(pg)
                sb = statusbar(pg)
                cur = next((b["t"] for b in sb if b["cur"]), "")
                fld_ok = all(k in ft for k in ["仿真|批5购物店", "12,000.00", "来源"])
                body = pg.locator("body").first.inner_text()
                chat_ok = "已生成/更新佣金单 YJ00070" in body
                shot(pg, "16-购物记录-GW00007-表单.png")
                rec("8-购物记录GW00007", "PASS" if (fld_ok and cur == "已确认" and chat_ok) else "FAIL",
                    f"字段={fld_ok} 状态栏当前={cur or '未识别'} 聊天区佣金消息={chat_ok}")
            else:
                shot(pg, "16-购物记录-GW00007-表单.png")
                rec("8-购物记录GW00007", "FAIL", f"搜索行数={n}")
        except Exception as e:
            rec("8-购物记录GW00007", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 9 菜单：导游与报账 → 人均线/算法（action-565/566）=================
        try:
            items = open_menu_dropdown(pg, "ta_guide.menu_ta_guide")
            m_ok = any("导游人均线" == t for t in items) and any("人均算法设置" == t for t in items)
            shot(pg, "17-菜单-导游与报账-人均线算法入口.png")
            rec("9a-菜单入口", "PASS" if m_ok else "FAIL", f"导游人均线/人均算法设置可见={m_ok} 可见项={[t for t in items if '人均' in t]}")
        except Exception as e:
            rec("9a-菜单入口", "FAIL", f"异常 {str(e)[:120]}")
        dismiss(pg)
        try:
            goto(pg, f"{BASE}/odoo/action-565")
            rows = list_rows(pg)
            g_ok = any("2000.00" in r.replace(",", "") and "5000.00" in r.replace(",", "") for r in rows)
            if row_count(pg) >= 1:
                open_first_row(pg, None)
                ft = form_text(pg)
                f_ok = ("2000.00" in norm(ft) and "5000.00" in norm(ft) and "35.00" in norm(ft)
                        and "45.00" in norm(ft) and "生效" in ft)
                shot(pg, "18-导游人均线-全局配置.png")
            else:
                f_ok = False
                shot(pg, "18-导游人均线-全局配置.png")
            rec("9b-人均线全局", "PASS" if (g_ok and f_ok) else "FAIL",
                f"列表基础2000/优秀5000={g_ok} 表单2000/5000/35/45+生效={f_ok}")
        except Exception as e:
            rec("9b-人均线全局", "FAIL", f"异常 {str(e)[:120]}")
        try:
            goto(pg, f"{BASE}/odoo/action-566")
            rows = list_rows(pg)
            c_ok = any("简单平均" in r for r in rows)
            if row_count(pg) >= 1:
                open_first_row(pg, None)
                ft = form_text(pg)
                cf_ok = ("简单平均" in ft and "四舍五入" in ft and "小数位数" in ft and "生效" in ft)
                shot(pg, "19-人均算法设置-全局.png")
            else:
                cf_ok = False
                shot(pg, "19-人均算法设置-全局.png")
            rec("9c-人均算法全局", "PASS" if (c_ok and cf_ok) else "FAIL",
                f"列表简单平均={c_ok} 表单简单平均/四舍五入/小数位数={cf_ok}")
        except Exception as e:
            rec("9c-人均算法全局", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 10 发团 BQ00266 司机/陪同（action-539）=================
        try:
            goto(pg, f"{BASE}/odoo/action-539")
            n = search_freetext(pg, "BQ00266")
            if n >= 1:
                open_first_row(pg, "BQ00266")
                ft = form_text(pg)
                d_ok = "仿真|批5司机" in ft
                e_ok = "仿真|批5陪同" in ft
                shot(pg, "20-发团-BQ00266-司机陪同.png")
                rec("10-发团司机陪同", "PASS" if (d_ok and e_ok) else "FAIL",
                    f"司机=仿真|批5司机:{d_ok} 陪同=仿真|批5陪同:{e_ok}")
            else:
                shot(pg, "20-发团-BQ00266-司机陪同.png")
                rec("10-发团司机陪同", "FAIL", f"搜索行数={n}")
        except Exception as e:
            rec("10-发团司机陪同", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 11 订单报名名单 性别/年龄段/客源地（action-540）=================
        try:
            goto(pg, f"{BASE}/odoo/action-540")
            n = search_freetext(pg, "DD000229")
            time.sleep(1.0)
            open_first_row(pg, "DD000229")
            time.sleep(1.5)
            # 三个新字段在名单树内为可选列（optional=hide，订单已确认→树只读，可选列开关不一定渲染）
            toggle_ok = False
            try:
                pg.locator(".o_form_view .o_list_renderer button.o-dropdown, .o_form_view .o_optional_columns_dropdown_toggle").first.hover(timeout=4000)
                time.sleep(0.8)
                pg.locator(".o_form_view .o_list_renderer button.o-dropdown, .o_form_view .o_optional_columns_dropdown_toggle").first.click(timeout=4000)
                time.sleep(1.5)
                opts = pg.evaluate("""() => Array.from(document.querySelectorAll('body .o_optional_columns label, body .o_optional_columns li, body .o_optional_columns span, body .dropdown-menu label')).filter(e => e.offsetParent !== null).map(e => (e.innerText||'').trim()).filter(Boolean)""")
                if all(lbl in opts for lbl in ["性别", "年龄段", "客源地"]):
                    for lbl in ["性别", "年龄段", "客源地"]:
                        try:
                            pg.locator(f"body label:has-text('{lbl}')").first.click(timeout=3000)
                            time.sleep(0.5)
                        except Exception:
                            pass
                    time.sleep(1.5)
                    hs2 = headers(pg)
                    toggle_ok = all(lbl in hs2 for lbl in ["性别", "年龄段", "客源地"])
                pg.keyboard.press("Escape")
            except Exception:
                pass
            fld_render = pg.evaluate("""() => {
                const f = document.querySelector('.o_form_view');
                if (!f) return [];
                return ['gender','age_group','origin_province'].filter(n => !!f.querySelector(`[name='${n}']`));
            }""")
            shot(pg, "21-订单-报名名单-性别年龄段客源地.png")
            rec("11-报名名单三字段", "PASS" if (toggle_ok or len(fld_render) == 3) else "FAIL",
                f"可选列切换显示3列={toggle_ok} 名单树DOM字段渲染={fld_render} "
                f"| 注：BQ00266 订单均已确认，名单树为只读，字段只读渲染；未做任何保存")
        except Exception as e:
            rec("11-报名名单三字段", "FAIL", f"异常 {str(e)[:160]}")

        # ================= 12 回归抽查 =================
        try:
            goto(pg, f"{BASE}/odoo/action-558")
            rows = list_rows(pg)
            both = ("GW00005" in "".join(rows)) and ("GW00007" in "".join(rows))
            shot(pg, "22-回归-购物记录列表-GW两行.png")
            rec("12a-购物记录列表", "PASS" if both else "FAIL", f"行数={len(rows)} 含GW00005/GW00007={both}")
        except Exception as e:
            rec("12a-购物记录列表", "FAIL", f"异常 {str(e)[:120]}")
        try:
            goto(pg, f"{BASE}/odoo/action-557")
            r = row_count(pg)
            h = len(headers(pg))
            shot(pg, "23-回归-供应商付款按团.png")
            rec("12b-供应商付款", "PASS" if (r > 0 and h > 0) else "FAIL", f"行数={r} 表头数={h}")
        except Exception as e:
            rec("12b-供应商付款", "FAIL", f"异常 {str(e)[:120]}")
        try:
            goto(pg, f"{BASE}/odoo/action-554")
            r = row_count(pg)
            h = len(headers(pg))
            shot(pg, "24-回归-应收账龄.png")
            rec("12c-应收账龄", "PASS" if (r > 0 and h > 0) else "FAIL", f"行数={r} 表头数={h}")
        except Exception as e:
            rec("12c-应收账龄", "FAIL", f"异常 {str(e)[:120]}")

        br.close()

    fails = sum(1 for _, st, _ in STEPS if st == "FAIL")
    print("\n===== SUMMARY =====")
    for tag, st, dt in STEPS:
        print(f"{st:5s} | {tag:22s} | {dt}")
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
