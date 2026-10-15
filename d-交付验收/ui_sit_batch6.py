# -*- coding: utf-8 -*-
"""批6 UI SIT（只读取证）· 财务收尾
覆盖：A 购物成本（P1-4 菜单4305）/ B 佣金收款与批量向导（P1-5 菜单3622）/
C 购物退单红冲与个税抵扣（P0-4 菜单4303）/ D 收入确认（P0-6 菜单 ta_finance）/
E 统计口径（购物对账新列、单团损益购物成本列）/ F 批3-5 回归抽查。
只导航/搜索/打开表单/截图，严禁点击 新建/保存/确认/生成收款/确认退单/驳回/申请退税 等写操作。
生产地址 https://tour.solepro.cloud（DB tour20）；口令经环境变量 ODOO_TEST_PASS 注入（默认 admin），
不落盘不打印。截图目录：/home/adai/tms/d-交付验收/截图-批6/（01 起编号）。
数据锚点（scripts/sim_batch6.py 正式执行产物）：
购物成本 500（仿真|批6购物店，BQ00266）；收款 SK00004 500（YJ00070，凭证 BNK1/2026/00001）；
退单 TD00004+TD00005 各 2000（GW00011→YJ00077/YJ00078 已取消→红冲→新单 YJ00079 已确认 4000/800，
个税抵扣 8.00×2 待抵扣）；收入确认 1674 条（net 6,120,015.21 / tax 365,266.14）。
搜索口径沿用批5：搜索输入 Enter 以搜索视图首字段建 facet。
"""
import os, re, time
from playwright.sync_api import sync_playwright

BASE = "https://tour.solepro.cloud"
SHOT = "/home/adai/tms/d-交付验收/截图-批6"
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
        pg.wait_for_selector(".o_control_panel, .o_view_controller, .o_form_view, .modal", timeout=25000)
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
    inp = pg.locator(".o_searchview_input").first
    inp.click()
    inp.fill(text)
    time.sleep(1.2)
    inp.press("Enter")
    time.sleep(settle)
    dismiss(pg)
    return row_count(pg)

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

def form_text(pg, tries=3):
    for i in range(tries):
        try:
            return pg.locator(".o_form_view").first.inner_text(timeout=8000)
        except Exception:
            time.sleep(1.5)
    return ""

def form_text_wait(pg, pred, tries=8):
    """表单字段值异步渲染：轮询直到 pred(文本) 成立或超时。"""
    ft = ""
    for i in range(tries):
        ft = form_text(pg, tries=1)
        if ft and pred(ft):
            return ft
        time.sleep(1.5)
    return ft

def form_field(pg, name):
    """表单字段值经 DOM 按 name 读取（inner_text 常不含 m2o/float 值，只含标签）。"""
    for i in range(3):
        try:
            return pg.evaluate(
                """nm => {const el = document.querySelector(`.o_form_view [name='${nm}']`);
                if (!el) return '';
                const a = el.querySelector('input');
                return a ? a.value : el.textContent.trim();}""", name)
        except Exception:
            time.sleep(1.5)
    return ""

def statusbar(pg, tries=3):
    for i in range(tries):
        try:
            return pg.evaluate("""() => Array.from(document.querySelectorAll('.o_form_view .o_arrow_button')).map(b => ({t: b.innerText.trim(), cur: b.classList.contains('o_arrow_button_current')}))""")
        except Exception:
            time.sleep(1.5)
    return []

def visible_menu_texts(pg):
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

def form_tables(pg):
    try:
        return pg.evaluate("""() => Array.from(document.querySelectorAll('.o_form_view table.o_list_table')).map(t => ({rows: t.querySelectorAll('.o_data_row').length, text: t.innerText}))""")
    except Exception:
        return []

def move_sums(pg):
    return pg.evaluate("""() => {
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
          if (di >= 0 && di < tds.length) deb += parseFloat((tds[di].innerText||'0').replace(/[^0-9.\\-]/g,'')) || 0;
          if (ci >= 0 && ci < tds.length) cred += parseFloat((tds[ci].innerText||'0').replace(/[^0-9.\\-]/g,'')) || 0;
        });
        return {rows, deb, cred};
    }""")

def nav_ta_app(pg, settle=2.5):
    pg.click(".o_navbar_apps_menu")
    time.sleep(1.2)
    try:
        pg.click("a.o_app[data-menu-xmlid='ta_base.menu_ta_root']", timeout=8000)
    except Exception:
        return False
    time.sleep(settle)
    return True

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

        # ================= 1 菜单可见性：购物成本/购物退单/购物批量收款/收入确认 =================
        try:
            items = open_menu_dropdown(pg, "ta_guide.menu_ta_guide")
            want1 = ["购物成本", "购物退单"]
            found1 = [w for w in want1 if any(w == t for t in items)]
            shot(pg, "01-菜单-导游与报账-购物成本购物退单.png")
            dismiss(pg)
            items3 = open_menu_dropdown(pg, "ta_finance.menu_ta_finance")
            # 购物统计子菜单在财务面板中平铺展示，购物批量收款直接可见
            found2 = [t for t in ["购物批量收款"] if any(t == x for x in items3)]
            found3 = [t for t in ["收入确认"] if any(t == x for x in items3)]
            shot(pg, "02-菜单-购物统计-购物批量收款.png")
            dismiss(pg)
            shot(pg, "03-菜单-财务-收入确认.png")
            rec("1-新菜单可见性", "PASS" if (len(found1) == 2 and found2 and found3) else "FAIL",
                f"导游与报账缺={[w for w in want1 if w not in found1] or '无'} 购物批量收款={bool(found2)} 收入确认={bool(found3)}")
        except Exception as e:
            rec("1-新菜单可见性", "FAIL", f"异常 {str(e)[:120]}")
        dismiss(pg)

        # ================= 2 购物成本（P1-4，action-572）=================
        try:
            goto(pg, f"{BASE}/odoo/action-572")
            # 搜索视图首字段 = 发团计划（m2o，显示名 BQ00266）
            n = search_freetext(pg, "BQ00266")
            hs = headers(pg)
            rows = list_rows(pg)
            tgt = next((r for r in rows if "仿真|批6购物店" in r), "")
            cell = row_cells(pg, tgt, hs)
            amt = norm(cell.get("成本金额", ""))
            ct = cell.get("成本类型", "")
            lst_ok = (n == 1 and amt == "500.00" and "回扣" in ct)
            shot(pg, "04-购物成本-列表-批6购物店500.png")
            v_dep = v_sup = v_amt = v_ct = ""
            if n >= 1:
                open_first_row(pg, "仿真|批6购物店", settle=4.0)
                # 字段值经 DOM 读取（表单 inner_text 只含标签不含值）
                v_dep = form_field(pg, "departure_id")
                v_sup = form_field(pg, "supplier_id")
                v_amt = form_field(pg, "amount")
                v_ct = form_field(pg, "cost_type")
                f_ok = ("BQ00266" in v_dep and v_sup == "仿真|批6购物店"
                        and norm(v_amt) == "500.00" and v_ct == "回扣")
                shot(pg, "05-购物成本-表单.png")
            else:
                f_ok = False
            rec("2-购物成本", "PASS" if (lst_ok and f_ok) else "FAIL",
                f"行数={n} 金额={amt} 成本类型={ct} 表单(计划={v_dep[:20]}/购物店={v_sup}/金额={v_amt}/类型={v_ct})={f_ok}")
        except Exception as e:
            rec("2-购物成本", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 3 佣金收款（P1-5，action-573 + 凭证）=================
        try:
            goto(pg, f"{BASE}/odoo/action-573")
            # 搜索视图首字段 = 佣金单（m2o，显示名 YJ00070）
            n = search_freetext(pg, "YJ00070")
            rows = list_rows(pg)
            row_ok = any("SK0000" in r and "500.00" in r.replace(",", "") for r in rows)
            shot(pg, "06-佣金收款-列表-SK00004.png")
            mv_ok = posted_ok = bal_ok = False
            jrows = -1; deb = cred = "?"; move_name = ""
            if n >= 1 and row_ok:
                open_first_row(pg, "500.00", settle=4.0)
                ft = form_text_wait(
                    pg, lambda t: re.search(r"[A-Z]{2,5}\d*/\d{4}/\d{4,5}", t))
                m = re.search(r"[A-Z]{2,5}\d*/\d{4}/\d{4,5}", ft)
                move_name = m.group(0) if m else ""
                has_link = bool(move_name) and move_name in ft
                shot(pg, "07-佣金收款-表单-凭证链接.png")
                if has_link:
                    pg.locator(".o_form_view a", has_text=move_name).first.click(timeout=8000)
                    pg.wait_for_selector(".o_form_view", timeout=20000)
                    time.sleep(3.5)
                    mft = pg.locator(".o_form_view").first.inner_text()
                    mv_ok = move_name in mft
                    posted_ok = ("已过账" in mft) or ("posted" in mft.lower())
                    js = move_sums(pg)
                    jrows, deb, cred = js.get("rows", -1), js.get("deb"), js.get("cred")
                    bal_ok = (jrows == 2) and abs(float(deb) - 500.0) < 0.005 and abs(float(cred) - 500.0) < 0.005
                    elshot(pg, pg.locator(".o_form_view"), "08-收款凭证-凭证行明细.png")
            rec("3-佣金收款与凭证", "PASS" if (n >= 1 and row_ok and mv_ok and posted_ok and bal_ok) else "FAIL",
                f"行数={n} 含SK500={row_ok} 凭证={move_name or '未识别'} 打开={mv_ok} 已过账={posted_ok} "
                f"行数={jrows} 借={deb} 贷={cred} 平衡={bal_ok}")
        except Exception as e:
            rec("3-佣金收款与凭证", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 4 购物批量收款向导（action-574，只读渲染）=================
        try:
            goto(pg, f"{BASE}/odoo/action-574", settle=4.0)
            body = pg.locator("body").first.inner_text()
            wiz_ok = ("购物批量收款" in body and ("收款日记账" in body or "佣金单" in body))
            btn_visible = pg.locator("button:has-text('生成收款')").count() > 0 or pg.evaluate(
                """() => Array.from(document.querySelectorAll('button, a.btn')).some(e => e.offsetParent !== null && (e.innerText||'').includes('生成收款'))""")
            shot(pg, "09-购物批量收款-向导渲染.png")
            pg.keyboard.press("Escape")
            time.sleep(1.0)
            rec("4-批量收款向导", "PASS" if (wiz_ok and btn_visible) else "FAIL",
                f"向导表单渲染={wiz_ok} 生成收款按钮可见={btn_visible}（未点击任何写操作）")
        except Exception as e:
            rec("4-批量收款向导", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 5 购物退单（P0-4，action-575）=================
        try:
            goto(pg, f"{BASE}/odoo/action-575")
            # 搜索视图首字段 = 购物记录（m2o，显示名 GW00011）
            n = search_freetext(pg, "GW00011")
            rows = list_rows(pg)
            has_td = ("TD00004" in "".join(rows)) and ("TD00005" in "".join(rows))
            shot(pg, "10-购物退单-列表-GW00011两笔退单.png")
            f_ok = deduct_ok = False
            if n >= 1 and any("TD00004" in r for r in rows):
                open_first_row(pg, "TD00004", settle=4.0)
                # 退单金额经 DOM 读取；状态条 current 断言已确认
                v_ret = form_field(pg, "return_amount")
                sb = statusbar(pg)
                cur = next((b["t"] for b in sb if b["cur"]), "")
                f_ok = (cur == "已确认" and norm(v_ret) == "2000.00")
                tbls = form_tables(pg)
                split = next((t for t in tbls if "个税抵扣" in t["text"] or "待抵扣" in t["text"]), None)
                deduct_ok = bool(split) and ("8.00" in split["text"].replace(",", "") and "待抵扣" in split["text"])
                shot(pg, "11-购物退单-表单-个税抵扣.png")
            rec("5-购物退单", "PASS" if (n >= 2 and has_td and f_ok and deduct_ok) else "FAIL",
                f"行数={n} 含TD00004+TD00005={has_td} 状态已确认={f_ok} 个税抵扣8待抵扣={deduct_ok}")
        except Exception as e:
            rec("5-购物退单", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 6 佣金单红冲结果（action-547：YJ00077/78 已取消 / YJ00079 重确认）=================
        try:
            goto(pg, f"{BASE}/odoo/action-547")
            n = search_freetext(pg, "仿真|批6导游")
            rows = list_rows(pg)
            has_cancel = ("YJ00077" in "".join(rows)) and ("YJ00078" in "".join(rows))
            has_new = any("YJ00079" in r for r in rows)
            shot(pg, "12-佣金单-列表-批6导游-取消与重确认.png")
            new_ok = False
            if has_new:
                open_first_row(pg, "YJ00079")
                ft = form_text(pg)
                new_ok = ("4,000.00" in ft or "4000.00" in norm(ft)) and \
                         ("800.00" in ft or "800.00" in norm(ft))
                sb = statusbar(pg)
                cur = next((b["t"] for b in sb if b["cur"]), "")
                new_ok = new_ok and cur == "已确认"
                shot(pg, "13-佣金单-YJ00079-重确认4000-800.png")
            rec("6-退单红冲佣金单", "PASS" if (has_cancel and has_new and new_ok) else "FAIL",
                f"YJ00077/78在列表={has_cancel} YJ00079在列表={has_new} 新单金额4000/800已确认={new_ok}")
        except Exception as e:
            rec("6-退单红冲佣金单", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 7 佣金单 YJ00070 已收佣金回流（action-547）=================
        try:
            goto(pg, f"{BASE}/odoo/action-547")
            n = search_freetext(pg, "仿真|批5导游")
            recv_ok = False
            if n >= 1 and any("YJ00070" in r for r in list_rows(pg)):
                open_first_row(pg, "YJ00070")
                ft = form_text(pg)
                recv_ok = "已收佣金" in ft and "500.00" in norm(ft)
                shot(pg, "14-佣金单-YJ00070-已收佣金500.png")
            rec("7-已收佣金回流", "PASS" if recv_ok else "FAIL",
                f"YJ00070 表单含已收佣金500={recv_ok}")
        except Exception as e:
            rec("7-已收佣金回流", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 8 收入确认（P0-6，action-571）=================
        try:
            goto(pg, f"{BASE}/odoo/action-571")
            n = row_count(pg)
            hs = headers(pg)
            need_cols = ["收入基数（含税）", "确认收入（净额）", "销项税额", "确认凭证", "状态"]
            miss_cols = [c for c in need_cols if c not in hs]
            rows = list_rows(pg)
            tot_ok = False
            sums = pg.evaluate("""() => {
                const ths = Array.from(document.querySelectorAll('.o_list_table thead th')).map(x => (x.innerText||'').trim());
                const rows = Array.from(document.querySelectorAll('.o_list_table .o_data_row'));
                const f = (name) => { const i = ths.findIndex(x => x.includes(name)); return i; };
                let net = 0, tax = 0;
                const ni = f('净额'), ti = f('销项税');
                rows.forEach(r => {
                    const tds = r.querySelectorAll('td');
                    if (ni >= 0 && ni + 1 < tds.length) net += parseFloat((tds[ni+1].innerText||'0').replace(/[^0-9.\\-]/g,'')) || 0;
                    if (ti >= 0 && ti + 1 < tds.length) tax += parseFloat((tds[ti+1].innerText||'0').replace(/[^0-9.\\-]/g,'')) || 0;
                });
                return {cnt: rows.length, net: Math.round(net*100)/100, tax: Math.round(tax*100)/100};
            }""")
            # 列表首屏最多 80 行，仅校验可见行净额>0；总额口径以仿真脚本 1674/6120015.21 为准
            tot_ok = sums.get("cnt", 0) > 0 and sums.get("net", 0) > 0
            shot(pg, "15-收入确认-列表.png")
            form_ok = False
            if n >= 1:
                open_first_row(pg, None)
                ft = form_text(pg)
                form_ok = ("确认凭证" in ft and ("已过账" in ft or "posted" in ft.lower()))
                shot(pg, "16-收入确认-表单-凭证链接.png")
            rec("8-收入确认", "PASS" if (n > 0 and not miss_cols and tot_ok and form_ok) else "FAIL",
                f"行数(首屏)={n} 缺列={miss_cols or '无'} 可见净额合计={sums.get('net')} 表单凭证已过账={form_ok} "
                f"| 全量口径以 sim_batch6 为准：1674 条 net=6,120,015.21 tax=365,266.14")
        except Exception as e:
            rec("8-收入确认", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 9 购物对账新列（action-567）=================
        try:
            goto(pg, f"{BASE}/odoo/action-567")
            hs = headers(pg)
            need_cols = ["购物成本", "购物净利润", "已付佣金"]
            miss_cols = [c for c in need_cols if c not in hs]
            n = search_freetext(pg, "仿真|批5购物店")
            rows = list_rows(pg)
            tgt = next((r for r in rows if "仿真|批5购物店" in r), "")
            cell = row_cells(pg, tgt, hs)
            paid = norm(cell.get("已付佣金", ""))
            shot(pg, "17-购物对账-批5购物店-已付佣金500.png")
            goto(pg, f"{BASE}/odoo/action-567")
            search_freetext(pg, "仿真|批6购物店")
            rows2 = list_rows(pg)
            tgt2 = next((r for r in rows2 if "仿真|批6购物店" in r), "")
            cell2 = row_cells(pg, tgt2, hs)
            cost = norm(cell2.get("购物成本", ""))
            payable6 = norm(cell2.get("应付佣金（含税）", ""))
            shot(pg, "18-购物对账-批6购物店-购物成本500.png")
            rec("9-购物对账新列", "PASS" if (not miss_cols and paid == "1000.00" and cost == "500.00" and payable6 == "800.00") else "FAIL",
                f"缺列={miss_cols or '无'} 批5已付佣金={paid}(两笔×500) 批6购物成本={cost} 批6应付佣金={payable6}")
        except Exception as e:
            rec("9-购物对账新列", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 10 单团损益购物成本列（action-542 回归）=================
        try:
            goto(pg, f"{BASE}/odoo/action-542")
            n = search_freetext(pg, "BQ00266")
            hs = headers(pg)
            cost_col = "购物成本" in hs
            try:
                pg.locator(".o_data_row", has_text="BQ00266").first.scroll_into_view_if_needed()
            except Exception:
                pass
            shot(pg, "19-单团损益-BQ00266-购物成本列.png")
            rec("10-单团损益购物成本列", "PASS" if (n == 1 and cost_col) else "FAIL",
                f"行数={n} 购物成本列={cost_col}")
        except Exception as e:
            rec("10-单团损益购物成本列", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 11 购物记录退单联动（action-558 GW00011）=================
        try:
            goto(pg, f"{BASE}/odoo/action-558")
            n = search_freetext(pg, "仿真|批6购物店")
            rows = list_rows(pg)
            has_gw = any("GW00011" in r and "8,000.00" in r.replace(",", "").replace("8000.00", "8,000.00") or "GW00011" in r and "8000.00" in r.replace(",", "") for r in rows)
            shot(pg, "20-购物记录-GW00011-列表.png")
            body_ok = False
            if n >= 1 and any("GW00011" in r for r in rows):
                open_first_row(pg, "GW00011")
                ft = form_text(pg)
                body_ok = "退单" in ft and "TD0000" in ft
                shot(pg, "21-购物记录-GW00011-表单-退单信息.png")
            rec("11-购物记录退单联动", "PASS" if (has_gw and body_ok) else "FAIL",
                f"GW00011×8000={has_gw} 表单含退单轨迹={body_ok}")
        except Exception as e:
            rec("11-购物记录退单联动", "FAIL", f"异常 {str(e)[:120]}")

        # ================= 12 批3-5 回归抽查 =================
        try:
            goto(pg, f"{BASE}/odoo/action-546")
            r = row_count(pg)
            shot(pg, "22-回归-导游报账.png")
            rec("12a-导游报账", "PASS" if (r > 0) else "FAIL", f"行数={r}")
        except Exception as e:
            rec("12a-导游报账", "FAIL", f"异常 {str(e)[:120]}")
        try:
            goto(pg, f"{BASE}/odoo/action-555")
            r = row_count(pg)
            shot(pg, "23-回归-导游绩效.png")
            rec("12b-导游绩效", "PASS" if (r > 0) else "FAIL", f"行数={r}")
        except Exception as e:
            rec("12b-导游绩效", "FAIL", f"异常 {str(e)[:120]}")
        try:
            goto(pg, f"{BASE}/odoo/action-565")
            r = row_count(pg)
            goto(pg, f"{BASE}/odoo/action-566")
            r2 = row_count(pg)
            shot(pg, "24-回归-人均线与算法.png")
            rec("12c-人均线算法", "PASS" if (r > 0 and r2 > 0) else "FAIL", f"人均线行数={r} 算法行数={r2}")
        except Exception as e:
            rec("12c-人均线算法", "FAIL", f"异常 {str(e)[:120]}")

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
