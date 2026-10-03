# -*- coding: utf-8 -*-
"""TMS 用户视角仿真测试 第二段 (batch35-A)
Playwright 驱动 http://localhost:8079 (Odoo 20, db=tour20)。
范围：发团计划→订单(含超额探针)→计调单→供应商账单付款→收款三级闭环→报表核对。
纪律：只新建业务单据；不动既有数据；不改代码；口令经环境变量 SIM_PW 传入不落盘；
      所有等待 ≤15s，超时即截图并继续，不重试不轮询。
"""
import os, sys, time, json, datetime
import urllib.request, http.cookiejar
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8079"
SHOT = "/home/adai/tms/d-交付验收/截图-用户仿真"
ADMIN_PW = os.environ.get("SIM_ADMIN_PW", "admin")
SIM_PW = os.environ.get("SIM_PW", "")

T0 = time.time()
DOCS = {}          # 新建单据编号/ID 记录
STEPS = []         # (tag, status, detail)

def log(msg):
    print(f"[{int(time.time()-T0):4d}s] {msg}", flush=True)

def rec(tag, status, detail=""):
    STEPS.append((tag, status, detail))
    log(f"STEP {tag}: {status} {detail}")

def shot(page, name):
    path = os.path.join(SHOT, name)
    try:
        page.screenshot(path=path)
        log(f"[SHOT] {name}")
    except Exception as e:
        log(f"[SHOT FAIL] {name}: {e}")
    return path

def page_summary(page):
    try:
        url = page.url
        txt = page.evaluate("() => (document.body ? document.body.innerText : '').slice(0,300)").replace("\n", " | ")
        return f"URL={url} TEXT={txt}"
    except Exception:
        return "URL=?"

# ---------------- RPC (只读校验 + 元数据解析) ----------------
class RPC:
    def __init__(self, login="admin", pw=ADMIN_PW):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.creds = (login, pw)
    def call(self, model, method, args, kwargs=None):
        payload = {"jsonrpc": "2.0",
                   "params": {"service": "object", "method": "execute_kw",
                              "args": ["tour20", 2, self.creds[1],
                                       model, method, args, kwargs or {}]}, "id": 7}
        req = urllib.request.Request(BASE + "/jsonrpc", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with self.op.open(req, timeout=30) as r:
            d = json.loads(r.read())
        if d.get("error"):
            raise RuntimeError(str(d["error"].get("data", {}).get("message") or d["error"].get("message")))
        return d.get("result")
    def sr(self, model, domain, fields, limit=50, order=""):
        return self.call(model, "search_read", [domain, fields, 0, limit, order])
    def cnt(self, model, domain):
        return self.call(model, "search_count", [domain])

R = RPC()

def xmlid(model, module, name):
    try:
        rows = R.sr("ir.model.data", [["model", "=", model], ["module", "=", module], ["name", "=", name]], ["res_id"], 5)
        return rows[0]["res_id"] if rows else None
    except Exception as e:
        log(f"xmlid {module}.{name} 解析失败: {e}")
        return None

A_DEP = 539; A_ORDER = 540; A_DISP = 541; A_PNL = 542
A_BANKLINE = 543; A_CLAIM = 544; A_AGING = 554; A_PAYABLE = 557
A_USERS = xmlid("ir.actions.act_window", "base", "action_res_users") or 67
A_BILLS = xmlid("ir.actions.act_window", "account", "action_move_in_invoice_type") or 271

# ---------------- UI 助手 ----------------
def wait_vis(page, sel, t=15):
    try:
        page.locator(sel).first.wait_for(state="visible", timeout=t * 1000)
        return True
    except Exception:
        return False

def login(page, user, pw, tag):
    try:
        page.goto(BASE + "/web/login", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.5)
        page.fill("#login", user)
        page.fill("#password", pw)
        page.click("button[type=submit]")
        ok = wait_vis(page, "nav", 15)
        time.sleep(2.5)
        if not ok:
            shot(page, f"{tag}-login-timeout")
            log(f"login {user} 未见导航: {page_summary(page)}")
        return ok
    except Exception as e:
        log(f"login {user} 异常: {type(e).__name__} {str(e)[:150]}")
        return False

def goto(page, aid, tag):
    try:
        page.goto(f"{BASE}/odoo/action-{aid}", wait_until="domcontentloaded", timeout=20000)
        if not wait_vis(page, ".o_control_panel", 15):
            shot(page, f"{tag}-timeout")
            log(f"goto {aid} 超时: {page_summary(page)}")
            return False
        time.sleep(2.0)
        return True
    except Exception as e:
        log(f"goto {aid} 异常: {type(e).__name__} {str(e)[:150]}")
        return False

def click_create(page, tag):
    try:
        page.click("button.o_list_button_add")
        if not wait_vis(page, ".o_form_view", 15):
            shot(page, f"{tag}-create-timeout")
            return False
        time.sleep(2.5)
        return True
    except Exception as e:
        log(f"create {tag} 失败: {type(e).__name__} {str(e)[:150]}")
        return False

def save(page):
    try:
        page.click(".o_form_button_save")
        time.sleep(2.5)
        return True
    except Exception as e:
        log(f"save 失败: {type(e).__name__} {str(e)[:150]}")
        return False

def dialog_text(page):
    try:
        d = page.locator(".o_dialog").first
        if d.count() and d.is_visible():
            t = (d.inner_text() or "").strip()
            if t:
                return t[:800]
    except Exception:
        pass
    return ""

def close_dialog(page):
    try:
        page.locator(".o_dialog button.btn-primary").first.click(timeout=5000)
        time.sleep(1.0)
    except Exception:
        pass

def click_btn(page, name, wait=2.5):
    """点状态按钮，返回 (ok, dialog文本)"""
    try:
        page.locator(f"button[name='{name}']").first.click(timeout=15000)
        time.sleep(wait)
        return True, dialog_text(page)
    except Exception as e:
        return False, f"{type(e).__name__} {str(e)[:120]}"

def m2o(page, fname, text, exact=None):
    """many2one/many2many：输入→下拉→点匹配项"""
    try:
        inp = page.locator(f"div[name='{fname}'] .o-autocomplete--input, div[name='{fname}'] input").first
        inp.click()
        time.sleep(0.5)
        inp.fill("")
        inp.fill(str(text))
        time.sleep(1.2)
        if not wait_vis(page, ".o-autocomplete--dropdown-item", 15):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(0.4)
            return None
        time.sleep(0.4)
        chosen = page.evaluate("""(a) => {
            const items = [...document.querySelectorAll('.o-autocomplete--dropdown-item')];
            let best = null;
            for (const it of items) {
                const t = (it.innerText || '').trim();
                if (!t) continue;
                if (a.exact && t === a.exact) { best = it; break; }
                if (!best && !t.includes('创建') && !t.includes('搜索更多')) best = it;
            }
            if (best) {
                const link = best.querySelector('a.ui-menu-item-wrapper') || best;
                link.click();
                return (best.innerText || '').trim().slice(0, 60);
            }
            return null;
        }""", {"exact": exact})
        time.sleep(1.5)
        try:
            open_menu = page.evaluate("() => { const m = [...document.querySelectorAll('ul.ui-autocomplete, .o-autocomplete--dropdown')]; return m.some(e => e.offsetWidth > 0 || e.offsetHeight > 0); }")
            if open_menu:
                page.keyboard.press("Escape")
                time.sleep(0.5)
        except Exception:
            pass
        return chosen
    except Exception as e:
        log(f"m2o {fname} 失败: {type(e).__name__} {str(e)[:120]}")
        return None

def fill_field(page, fname, value):
    try:
        e = page.locator(f"div[name='{fname}'] input, div[name='{fname}'] textarea").first
        e.click()
        time.sleep(0.3)
        e.fill("")
        e.fill(str(value))
        e.press("Tab")
        time.sleep(0.7)
        return True
    except Exception as ex:
        log(f"fill {fname} 失败: {type(ex).__name__} {str(ex)[:120]}")
        return False

def sel_form(page, fname, label):
    try:
        native = page.locator(f"div[name='{fname}'] select").first
        if native.count() and native.is_visible():
            native.select_option(label=label)
            time.sleep(0.8)
            return True
    except Exception:
        pass
    try:
        box = page.locator(f"div[name='{fname}']").first
        box.click()
        time.sleep(0.8)
        opened = False
        try:
            opened = page.locator(".o_select_menu_item:visible", has_text=label).first.is_visible(timeout=2000)
        except Exception:
            opened = False
        if not opened:
            try:
                box.locator(".o_select_menu_toggler, .o_select_menu .o_input_dropdown").first.click(timeout=5000)
                time.sleep(0.8)
            except Exception:
                pass
        page.locator(".o_select_menu_item:visible", has_text=label).first.click(timeout=15000)
        time.sleep(0.8)
        return True
    except Exception as e:
        log(f"sel_form {fname}={label} 失败: {type(e).__name__} {str(e)[:120]}")
        return False

def click_tab(page, tab_text):
    try:
        page.locator(".o_notebook .nav-link", has_text=tab_text).first.click()
        time.sleep(1.2)
        return True
    except Exception as e:
        log(f"tab {tab_text} 失败: {type(e).__name__} {str(e)[:100]}")
        return False

def add_row(page, list_field):
    try:
        page.locator(f"div[name='{list_field}'] button:has-text('添加行')").first.click(timeout=15000)
        time.sleep(1.3)
        return True
    except Exception as e:
        log(f"add_row {list_field} 失败: {type(e).__name__} {str(e)[:100]}")
        return False

def row_loc(page, list_field, idx):
    return page.locator(f"div[name='{list_field}'] .o_list_table tbody tr.o_data_row").nth(idx)

def cell_fill(page, list_field, idx, col, value):
    try:
        td = row_loc(page, list_field, idx).locator(f"td[name='{col}']").first
        td.click()
        time.sleep(0.5)
        e = td.locator("input, textarea").first
        e.fill("")
        e.fill(str(value))
        e.press("Enter")
        time.sleep(0.6)
        return True
    except Exception as ex:
        log(f"cell_fill {list_field}[{idx}].{col} 失败: {type(ex).__name__} {str(ex)[:100]}")
        return False

def cell_sel(page, list_field, idx, col, label):
    try:
        td = row_loc(page, list_field, idx).locator(f"td[name='{col}']").first
        td.click()
        time.sleep(0.8)
        opened = False
        try:
            opened = page.locator(".o_select_menu_item:visible", has_text=label).first.is_visible(timeout=2000)
        except Exception:
            opened = False
        if not opened:
            try:
                td.locator(".o_select_menu_toggler, .o_select_menu .o_input_dropdown").first.click(timeout=5000)
                time.sleep(0.8)
            except Exception:
                pass
        page.locator(".o_select_menu_item:visible", has_text=label).first.click(timeout=15000)
        time.sleep(1.0)
        return True
    except Exception as e:
        log(f"cell_sel {list_field}[{idx}].{col}={label} 失败: {type(e).__name__} {str(e)[:100]}")
        return False

def cell_m2o(page, list_field, idx, col, text, contain=None):
    try:
        td = row_loc(page, list_field, idx).locator(f"td[name='{col}']").first
        td.click()
        time.sleep(0.6)
        inp = td.locator("input").first
        inp.fill("")
        inp.fill(str(text))
        time.sleep(1.2)
        if not wait_vis(page, ".o-autocomplete--dropdown-item", 15):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return None
        time.sleep(0.4)
        chosen = page.evaluate("""(a) => {
            const items = [...document.querySelectorAll('.o-autocomplete--dropdown-item')];
            let best = null;
            for (const it of items) {
                const t = (it.innerText || '').trim();
                if (!t) continue;
                if (a.exact && t === a.exact) { best = it; break; }
                if (a.contain && t.includes(a.contain)) { best = it; break; }
                if (!best && !t.includes('创建') && !t.includes('搜索更多')) best = it;
            }
            if (best) {
                const link = best.querySelector('a.ui-menu-item-wrapper') || best;
                link.click();
                return (best.innerText || '').trim().slice(0, 60);
            }
            return null;
        }""", {"exact": None, "contain": contain})
        time.sleep(1.3)
        try:
            open_menu = page.evaluate("() => { const m = [...document.querySelectorAll('ul.ui-autocomplete, .o-autocomplete--dropdown')]; return m.some(e => e.offsetWidth > 0 || e.offsetHeight > 0); }")
            if open_menu:
                page.keyboard.press("Escape")
                time.sleep(0.5)
        except Exception:
            pass
        return chosen
    except Exception as e:
        log(f"cell_m2o {list_field}[{idx}].{col} 失败: {type(e).__name__} {str(e)[:100]}")
        return None


def row_shot(page, text, name, fallback_sel=".o_list_table"):
    """尽量把含指定文本的行滚入视口并截图；失败则整页截图"""
    try:
        row = page.locator(f"tr:has-text('{text}')").first
        row.scroll_into_view_if_needed(timeout=8000)
        time.sleep(0.8)
        row.screenshot(path=os.path.join(SHOT, name))
        log(f"[SHOT] {name} (row)")
        return True
    except Exception as e:
        log(f"row_shot {name} 失败: {type(e).__name__} {str(e)[:80]}，改整页截图")
        shot(page, name)
        return False

def search(page, text):
    try:
        inp = page.locator(".o_searchview .o_searchview_input, .o_searchview input").first
        inp.click()
        inp.fill("")
        inp.fill(str(text))
        time.sleep(1.5)
        has_sugg = False
        try:
            has_sugg = page.locator(".o-autocomplete--dropdown-item").first.is_visible(timeout=2000)
        except Exception:
            has_sugg = False
        if has_sugg:
            inp.press("Enter")
        else:
            page.keyboard.press("Escape")
        time.sleep(1.8)
        # 若误弹 Custom Filter 对话框则关闭
        try:
            dlg = page.locator(".modal.show, .o_dialog").first
            if dlg.count() and dlg.is_visible():
                t = (dlg.inner_text() or "")[:120]
                if "Custom Filter" in t or "自定义筛选" in t:
                    page.keyboard.press("Escape")
                    time.sleep(0.6)
        except Exception:
            pass
        return True
    except Exception as e:
        log(f"search {text} 失败: {type(e).__name__} {str(e)[:100]}")
        return False

# ================= 主流程 =================
def main():
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        # 管理员上下文
        cadmin = br.new_context(viewport={"width": 1680, "height": 1000})
        cadmin.set_default_timeout(15000)
        ad = cadmin.new_page()
        if not login(ad, "admin", ADMIN_PW, "admin"):
            rec("前置", "FAIL", "admin 登录失败，终止")
            br.close()
            return

        # ========== 步骤1 发团计划 ==========
        try:
            route = R.sr("ta.route", [["id", "=", 432]], ["id", "name", "state", "list_price"], 1)
            rec("前置", "PASS" if route and route[0]["state"] == "on_sale" else "FAIL",
                f"线路432={route[0]['name'] if route else '?'} state={route[0]['state'] if route else '?'}")
            goto(ad, A_DEP, "s1")
            click_create(ad, "s1")
            m2o(ad, "route_id", "仿真|海南", exact="仿真|海南5日游-20261001")
            fill_field(ad, "date_start", "2026-11-01")
            fill_field(ad, "date_end", "2026-11-05")
            fill_field(ad, "seats_total", "20")
            m2o(ad, "guide_ids", "仿真|导游-林海")
            save(ad)
            shot(ad, "01-发团计划-已保存.png")
            dep = R.sr("ta.departure",
                       [["route_id", "=", 432], ["date_start", "=", "2026-11-01"], ["seats_total", "=", 20]],
                       ["id", "code", "state", "seats_total", "seats_used", "seats_min"], 3)
            if dep:
                DOCS["departure"] = {"id": dep[0]["id"], "code": dep[0]["code"]}
                rec("s1", "PASS", f"发团计划 {dep[0]['code']} id={dep[0]['id']} state={dep[0]['state']}")
            else:
                rec("s1", "FAIL", "保存后查不到发团计划")
            if dep:
                ok, dtxt = click_btn(ad, "action_open")
                shot(ad, "01-发团计划-开放报名.png")
                st = R.sr("ta.departure", [["id", "=", dep[0]["id"]]], ["state"], 1)[0]["state"]
                rec("s1-开放报名", "PASS" if st == "open" else "FAIL", f"state={st} dialog={dtxt[:80] if dtxt else '-'}")
                ok, dtxt = click_btn(ad, "action_confirm")
                shot(ad, "01-发团计划-确认成团.png")
                st = R.sr("ta.departure", [["id", "=", dep[0]["id"]]], ["state"], 1)[0]["state"]
                rec("s1-确认成团", "PASS" if st == "confirmed" else "FAIL", f"state={st} dialog={dtxt[:80] if dtxt else '-'}")
        except Exception as e:
            rec("s1", "FAIL", f"异常 {type(e).__name__} {str(e)[:150]}")
            shot(ad, "s1-timeout")

        dep_id = DOCS.get("departure", {}).get("id")
        dep_code = DOCS.get("departure", {}).get("code", "")

        # ========== 步骤2 订单 ==========
        orders = {}
        SPECS = [("O1", [("adult", 4, "成人"), ("child", 2, "儿童")], 8000.0),
                 ("O2", [("adult", 2, "成人")], 3200.0),
                 ("O3", [("adult", 3, "成人"), ("child", 1, "儿童")], 5600.0)]
        price_map = {"成人": "1600", "儿童": "800"}
        if dep_id:
            for tag, lines, total in SPECS:
                try:
                    goto(ad, A_ORDER, f"s2-{tag}")
                    click_create(ad, f"s2-{tag}")
                    sel_form(ad, "kind", "散客")
                    m2o(ad, "partner_id", "仿真|客户-散客甲", exact="仿真|客户-散客甲")
                    m2o(ad, "departure_id", "仿真|海南5日游")
                    click_tab(ad, "报名名单")
                    idx = 0
                    for kind, cnt, label in lines:
                        for j in range(cnt):
                            add_row(ad, "line_ids")
                            cell_fill(ad, "line_ids", idx, "name", f"仿真客{idx+1}")
                            cell_sel(ad, "line_ids", idx, "kind", label)
                            time.sleep(1.0)
                            try:
                                up = row_loc(ad, "line_ids", idx).locator("td[name='unit_price'] input").first.input_value()
                            except Exception:
                                up = ""
                            if (up or "").replace(",", "") != price_map[label]:
                                cell_fill(ad, "line_ids", idx, "unit_price", price_map[label])
                            idx += 1
                    click_tab(ad, "收款期次")
                    add_row(ad, "plan_ids")
                    cell_fill(ad, "plan_ids", 0, "name", "期次1")
                    cell_fill(ad, "plan_ids", 0, "due_date", "2026-10-15")
                    cell_fill(ad, "plan_ids", 0, "amount", str(int(total)))
                    save(ad)
                    shot(ad, f"02-订单{tag}-已保存.png")
                    ok, dtxt = click_btn(ad, "action_confirm")
                    if dtxt:
                        close_dialog(ad)
                    shot(ad, f"02-订单{tag}-已确认.png")
                    ordr = R.sr("ta.order", [["departure_id", "=", dep_id], ["partner_id", "=", 6401]],
                                ["id", "name", "state", "amount_total", "heads", "amount_paid"], 3, "id desc")
                    o = ordr[0] if ordr else None
                    if o and o["state"] == "confirmed" and abs(o["amount_total"] - total) < 0.01:
                        orders[tag] = {"id": o["id"], "name": o["name"]}
                        DOCS[f"order_{tag}"] = {"id": o["id"], "name": o["name"]}
                        rec(f"s2-{tag}", "PASS",
                            f"{o['name']} id={o['id']} state={o['state']} total={o['amount_total']} heads={o['heads']} dialog={dtxt[:60] if dtxt else '-'}")
                    else:
                        rec(f"s2-{tag}", "FAIL", f"RPC={o} dialog={dtxt[:120] if dtxt else '-'}")
                except Exception as e:
                    rec(f"s2-{tag}", "FAIL", f"异常 {type(e).__name__} {str(e)[:150]}")
                    shot(ad, f"s2-{tag}-timeout")
            # 列表截图
            try:
                goto(ad, A_ORDER, "s2-list")
                search(ad, dep_code)
                shot(ad, "02-订单列表-3张已确认.png")
            except Exception as e:
                log(f"s2-list 截图失败 {e}")

            # ---- 探针 O4：9 成人超额 ----
            try:
                goto(ad, A_ORDER, "s2-probe")
                click_create(ad, "s2-probe")
                sel_form(ad, "kind", "散客")
                m2o(ad, "partner_id", "仿真|客户-散客甲", exact="仿真|客户-散客甲")
                m2o(ad, "departure_id", "仿真|海南5日游")
                click_tab(ad, "报名名单")
                for j in range(9):
                    add_row(ad, "line_ids")
                    cell_fill(ad, "line_ids", j, "name", f"探针客{j+1}")
                    cell_sel(ad, "line_ids", j, "kind", "成人")
                    time.sleep(0.8)
                save(ad)
                ok, dtxt = click_btn(ad, "action_confirm")
                shot(ad, "02-探针O4-超额拦截.png")
                blocked = "超出发团计划余位" in dtxt or "余位" in dtxt
                rec("s2-探针", "PASS" if blocked else "发现",
                    f"9成人确认→拦截={'是' if blocked else '否'} 文案={dtxt[:150] if dtxt else '(无对话框)'}")
                if dtxt:
                    close_dialog(ad)
                # 清理探针草稿
                try:
                    ok2, dtxt2 = click_btn(ad, "action_cancel")
                    time.sleep(1.0)
                    if dialog_text(ad):
                        close_dialog(ad)
                    time.sleep(1.5)
                except Exception as e:
                    log(f"探针取消失败 {e}")
                shot(ad, "02-探针O4-已取消.png")
                st4 = R.sr("ta.order", [["departure_id", "=", dep_id], ["partner_id", "=", 6401], ["state", "=", "cancel"]],
                           ["id", "name", "state"], 3, "id desc")
                seats = R.sr("ta.departure", [["id", "=", dep_id]], ["seats_used", "seats_total"], 1)
                rec("s2-探针清理", "PASS" if st4 and seats and seats[0]["seats_used"] == 12 else "FAIL",
                    f"探针单={st4[0]['name'] if st4 else '?'} 已占位={seats[0]['seats_used'] if seats else '?'}/20")
            except Exception as e:
                rec("s2-探针", "FAIL", f"异常 {type(e).__name__} {str(e)[:150]}")
                shot(ad, "s2-probe-timeout")

        # ========== 步骤3 计调单 ==========
        disp_items = {}
        DISPS = [("ticket", "票务", "仿真|三亚湾景区", "门票", "10", "120"),
                 ("hotel", "酒店", "仿真|海棠湾酒店", "住宿", "8", "220"),
                 ("vehicle", "车队", "仿真|环岛车队", "用车", "1", "1800"),
                 ("meal", "餐厅", "仿真|椰香餐厅", "用餐", "10", "60")]
        if dep_id:
            for kind, kind_label, sup, desc, qty, uprice in DISPS:
                try:
                    goto(ad, A_DISP, f"s3-{kind}")
                    click_create(ad, f"s3-{kind}")
                    m2o(ad, "departure_id", "仿真|海南5日游")
                    sel_form(ad, "kind", kind_label)
                    m2o(ad, "supplier_id", sup, exact=sup)
                    fill_field(ad, "name", desc)
                    fill_field(ad, "qty", qty)
                    fill_field(ad, "unit_price", uprice)
                    save(ad)
                    ok, dtxt = click_btn(ad, "action_confirm")
                    if dtxt:
                        close_dialog(ad)
                    shot(ad, f"03-计调单-{kind}-已确认.png")
                    it = R.sr("ta.dispatch.item", [["departure_id", "=", dep_id], ["kind", "=", kind]],
                              ["id", "state", "amount", "move_id"], 3, "id desc")
                    i = it[0] if it else None
                    if i and i["state"] == "confirmed" and i["move_id"]:
                        disp_items[kind] = {"id": i["id"], "move_id": i["move_id"][0], "amount": i["amount"]}
                        DOCS[f"dispatch_{kind}"] = {"id": i["id"], "amount": i["amount"], "move_id": i["move_id"][0]}
                        rec(f"s3-{kind}", "PASS", f"计调单id={i['id']} amount={i['amount']} 账单move={i['move_id'][0]} dialog={dtxt[:60] if dtxt else '-'}")
                    else:
                        rec(f"s3-{kind}", "FAIL", f"RPC={it} dialog={dtxt[:120] if dtxt else '-'}")
                except Exception as e:
                    rec(f"s3-{kind}", "FAIL", f"异常 {type(e).__name__} {str(e)[:150]}")
                    shot(ad, f"s3-{kind}-timeout")
            try:
                goto(ad, A_DISP, "s3-list")
                search(ad, dep_code)
                shot(ad, "03-计调单-列表汇总.png")
            except Exception as e:
                log(f"s3-list 截图失败 {e}")

        # ========== 步骤4 供应商账单过账 + 登记付款 ==========
        PAYS = {"ticket": 1200.0, "hotel": 1760.0, "vehicle": 1000.0, "meal": 0.0}
        bills = {}
        for kind, pay in PAYS.items():
            move_id = disp_items.get(kind, {}).get("move_id")
            if not move_id:
                rec(f"s4-{kind}", "FAIL", "无 move_id 跳过")
                continue
            try:
                ad.goto(f"{BASE}/odoo/action-{A_BILLS}/{move_id}", wait_until="domcontentloaded", timeout=20000)
                if not wait_vis(ad, ".o_form_view", 15):
                    shot(ad, f"s4-{kind}-timeout")
                    log(f"账单 {move_id} 打开超时 {page_summary(ad)}")
                    continue
                time.sleep(2.5)
                mv = R.sr("account.move", [["id", "=", move_id]], ["name", "state", "amount_total", "payment_state", "amount_residual"], 1)
                mv = mv[0] if mv else {}
                ok, dtxt = click_btn(ad, "action_post")
                if dtxt:
                    rec(f"s4-{kind}-过账", "FAIL", f"过账报错: {dtxt[:150]}")
                    close_dialog(ad)
                    shot(ad, f"s4-{kind}-post-error")
                    continue
                time.sleep(1.0)
                st = R.sr("account.move", [["id", "=", move_id]], ["state"], 1)[0]["state"]
                rec(f"s4-{kind}-过账", "PASS" if st == "posted" else "FAIL", f"账单{mv.get('name')} state={st}")
                if pay > 0:
                    ok, dtxt = click_btn(ad, "action_register_payment")
                    if not wait_vis(ad, ".o_dialog", 15):
                        shot(ad, f"s4-{kind}-pay-timeout")
                        log(f"登记付款向导未出现 {page_summary(ad)}")
                        continue
                    time.sleep(1.0)
                    try:
                        ae = ad.locator(".o_dialog div[name='amount'] input").first
                        ae.click()
                        ae.fill("")
                        ae.fill(str(int(pay)))
                        ae.press("Tab")
                        time.sleep(0.8)
                    except Exception as e:
                        log(f"向导金额填充失败 {type(e).__name__} {str(e)[:100]}")
                    ok, dtxt = click_btn(ad, "action_create_payments", wait=3.5)
                    if dtxt:
                        rec(f"s4-{kind}-付款", "FAIL", f"创建付款报错: {dtxt[:150]}")
                        close_dialog(ad)
                    shot(ad, f"04-账单-{kind}-过账付款.png")
                else:
                    shot(ad, f"04-账单-{kind}-过账未付款.png")
                mv2 = R.sr("account.move", [["id", "=", move_id]],
                           ["name", "payment_state", "amount_residual", "amount_total"], 1)[0]
                bills[kind] = {"bill": mv2.get("name"), "state": mv2.get("payment_state"),
                               "residual": mv2.get("amount_residual")}
                DOCS[f"bill_{kind}"] = {"move_id": move_id, "name": mv2.get("name"),
                                        "payment_state": mv2.get("payment_state"),
                                        "residual": mv2.get("amount_residual")}
                rec(f"s4-{kind}-账单", "PASS", f"账单{mv2.get('name')} 状态={mv2.get('payment_state')} 未清={mv2.get('amount_residual')} 本次付={pay}")
            except Exception as e:
                rec(f"s4-{kind}", "FAIL", f"异常 {type(e).__name__} {str(e)[:150]}")
                shot(ad, f"s4-{kind}-timeout")

        # 付款凭证编号
        try:
            pays = R.sr("account.payment",
                        [["partner_id", "in", [6397, 6398, 6399, 6400]], ["payment_type", "=", "outbound"]],
                        ["id", "name", "amount", "partner_id"], 20, "id desc")
            for pp in pays:
                if abs(pp["amount"] - 1200) < 0.01:
                    DOCS.setdefault("pay_ticket", {"name": pp["name"], "id": pp["id"]})
                if abs(pp["amount"] - 1760) < 0.01:
                    DOCS.setdefault("pay_hotel", {"name": pp["name"], "id": pp["id"]})
                if abs(pp["amount"] - 1000) < 0.01:
                    DOCS.setdefault("pay_vehicle", {"name": pp["name"], "id": pp["id"]})
        except Exception as e:
            log(f"付款凭证查询失败 {e}")

        # ========== 步骤5 收款三级闭环 ==========
        # 5.0 为仿真用户设定口令（标准 UI 修改密码向导；失败则 RPC 直写兜底）
        pwd_ok = False
        if SIM_PW:
            try:
                goto(ad, A_USERS, "s5-pwd")
                for uname in ["仿真|出纳-王", "仿真|会计-李"]:
                    try:
                        search(ad, uname)
                        row = ad.locator(f"tr:has-text('{uname}')").first
                        cb = row.locator("td.o_list_record_selector input, td input[type='checkbox']").first
                        cb.check(timeout=10000)
                        log(f"已勾选 {uname}")
                    except Exception as e:
                        log(f"勾选 {uname} 失败 {type(e).__name__} {str(e)[:80]}")
                time.sleep(0.8)
                try:
                    clicked_gear = False
                    for gsel in [".o_list_buttons .o_dropdown_toggler",
                                 ".o_list_buttons button.dropdown-toggle",
                                 ".o_list_buttons button.o_dropdown_toggler"]:
                        try:
                            ad.locator(gsel).first.click(timeout=8000)
                            clicked_gear = True
                            break
                        except Exception:
                            continue
                    if clicked_gear:
                        time.sleep(0.8)
                        ad.locator(".o-dropdown--menu a, .o-dropdown--menu .dropdown-item", has_text="Change Password").first.click(timeout=10000)
                        time.sleep(2.0)
                        pws = ad.locator(".o_dialog input[type='password']")
                        n = pws.count()
                        for i in range(n):
                            pws.nth(i).fill(SIM_PW)
                        ad.locator("button[name='change_password_button']").first.click(timeout=10000)
                        time.sleep(2.5)
                        try:
                            ad.keyboard.press("Escape")
                        except Exception:
                            pass
                        time.sleep(1.2)
                        pwd_ok = True
                        log(f"修改密码向导完成，处理 {n} 个用户")
                except Exception as e:
                    log(f"修改密码向导失败: {type(e).__name__} {str(e)[:120]}")
            except Exception as e:
                log(f"s5-pwd UI 异常: {type(e).__name__} {str(e)[:120]}")
            if not pwd_ok:
                try:
                    R.call("res.users", "write", [[2826, 2827], {"password": SIM_PW}])
                    pwd_ok = True
                    log("兜底：RPC 直写 simu 用户口令完成")
                except Exception as e:
                    log(f"RPC 口令兜底失败: {type(e).__name__} {str(e)[:120]}")
        rec("s5-口令", "PASS" if pwd_ok else "FAIL", "simu_cashier/simu_accountant 口令已设定" if pwd_ok else "口令不可用，以下用 admin 代替")

        # 5.1 出纳登记银行流水
        bank_lines = {}
        cashier_ok = False
        if pwd_ok:
            ccash = br.new_context(viewport={"width": 1680, "height": 1000})
            ccash.set_default_timeout(15000)
            csh = ccash.new_page()
            cashier_ok = login(csh, "simu_cashier", SIM_PW, "s5-cashier")
            jname = "Bank"
            try:
                jrns = R.sr("account.journal", [["type", "=", "bank"]], ["id", "name"], 5, "id desc")
                if jrns:
                    jname = jrns[0]["name"]
            except Exception as e:
                log(f"journal 查询失败 {e}")
            if cashier_ok:
                for ref, amt in [("SIM-R-5000", "5000"), ("SIM-R-3200", "3200")]:
                    try:
                        goto(csh, A_BANKLINE, f"s5-bl-{ref}")
                        click_create(csh, f"s5-bl-{ref}")
                        fill_field(csh, "amount", amt)
                        m2o(csh, "journal_id", jname, exact=jname)
                        fill_field(csh, "partner_name", "仿真|客户-散客甲")
                        m2o(csh, "partner_id", "仿真|客户-散客甲", exact="仿真|客户-散客甲")
                        fill_field(csh, "ref", ref)
                        save(csh)
                    except Exception as e:
                        log(f"银行流水 {ref} 创建异常 {type(e).__name__} {str(e)[:120]}")
                try:
                    goto(csh, A_BANKLINE, "s5-bl-list")
                    search(csh, "SIM-R-")
                    shot(csh, "05-收款登记-出纳2笔流水.png")
                except Exception:
                    shot(csh, "05-收款登记-出纳2笔流水.png")
                bls = R.sr("ta.bank.line", [["ref", "like", "SIM-R-%"]],
                           ["id", "ref", "amount", "registered_by", "state"], 5, "id desc")
                for b in bls:
                    bank_lines[b["ref"]] = b
                rec("s5-收款登记", "PASS" if len(bls) == 2 else "FAIL",
                    f"{[ (b['ref'], b['id'], b['state'], b['registered_by']) for b in bls ]}")
            ccash.close()
        if not cashier_ok:
            # 兜底：admin 登记（审核人=会计仍可过 AC-05）
            try:
                jname = "Bank"
                try:
                    jrns = R.sr("account.journal", [["type", "=", "bank"]], ["id", "name"], 5, "id desc")
                    if jrns:
                        jname = jrns[0]["name"]
                except Exception:
                    pass
                for ref, amt in [("SIM-R-5000", "5000"), ("SIM-R-3200", "3200")]:
                    goto(ad, A_BANKLINE, f"s5-bl2-{ref}")
                    click_create(ad, f"s5-bl2-{ref}")
                    fill_field(ad, "amount", amt)
                    m2o(ad, "journal_id", jname, exact=jname)
                    fill_field(ad, "partner_name", "仿真|客户-散客甲")
                    m2o(ad, "partner_id", "仿真|客户-散客甲", exact="仿真|客户-散客甲")
                    fill_field(ad, "ref", ref)
                    save(ad)
                bls = R.sr("ta.bank.line", [["ref", "like", "SIM-R-%"]],
                           ["id", "ref", "amount", "registered_by", "state"], 5, "id desc")
                for b in bls:
                    bank_lines[b["ref"]] = b
                rec("s5-收款登记", "PASS" if len(bls) == 2 else "FAIL", f"admin代登记 {[(b['ref'], b['id']) for b in bls]}")
            except Exception as e:
                rec("s5-收款登记", "FAIL", f"{type(e).__name__} {str(e)[:120]}")

        # 5.2 admin 建认领单并提交
        claims = {}
        try:
            bl1 = bank_lines.get("SIM-R-5000")
            bl2 = bank_lines.get("SIM-R-3200")
            o1 = orders.get("O1")
            o2 = orders.get("O2")
            plan = [(bl1, o1, "5000", "C1"), (bl2, o2, "3200", "C2")]
            for bl, o, amt, tag in plan:
                if not bl or not o:
                    rec(f"s5-claim-{tag}", "FAIL", f"缺前置 bl={bl} o={o}")
                    continue
                try:
                    goto(ad, A_CLAIM, f"s5-{tag}")
                    click_create(ad, f"s5-{tag}")
                    click_tab(ad, "资金来源")
                    add_row(ad, "line_ids")
                    cell_m2o(ad, "line_ids", 0, "bank_line_id", "", contain=f",{bl['id']}")
                    cell_fill(ad, "line_ids", 0, "amount", amt)
                    click_tab(ad, "认领去向")
                    add_row(ad, "alloc_ids")
                    cell_m2o(ad, "alloc_ids", 0, "order_id", o["name"], exact=o["name"])
                    cell_fill(ad, "alloc_ids", 0, "amount_allocated", amt)
                    save(ad)
                    ok, dtxt = click_btn(ad, "action_submit")
                    if dtxt:
                        close_dialog(ad)
                    cl = R.sr("ta.payment.claim", [], ["id", "name", "state", "amount", "amount_alloc", "claimed_by"], 1, "id desc")
                    c = cl[0] if cl else None
                    if c and c["state"] == "submitted":
                        claims[tag] = {"id": c["id"], "name": c["name"]}
                        DOCS[f"claim_{tag}"] = {"id": c["id"], "name": c["name"]}
                        rec(f"s5-{tag}", "PASS", f"认领单 {c['name']} id={c['id']} state={c['state']} 金额={c['amount']}/{c['amount_alloc']} dialog={dtxt[:60] if dtxt else '-'}")
                    else:
                        rec(f"s5-{tag}", "FAIL", f"RPC={c} dialog={dtxt[:150] if dtxt else '-'}")
                except Exception as e:
                    rec(f"s5-{tag}", "FAIL", f"异常 {type(e).__name__} {str(e)[:150]}")
                    shot(ad, f"s5-{tag}-timeout")
            try:
                goto(ad, A_CLAIM, "s5-claim-list")
                shot(ad, "05-收款认领-两单已提交.png")
            except Exception:
                pass
        except Exception as e:
            rec("s5-claim", "FAIL", f"{type(e).__name__} {str(e)[:150]}")

        # 5.3 会计审核
        accountant_ok = False
        if pwd_ok:
            cacc = br.new_context(viewport={"width": 1680, "height": 1000})
            cacc.set_default_timeout(15000)
            acc = cacc.new_page()
            accountant_ok = login(acc, "simu_accountant", SIM_PW, "s5-acc")
            if accountant_ok:
                for tag in ["C1", "C2"]:
                    c = claims.get(tag)
                    if not c:
                        rec(f"s5-approve-{tag}", "FAIL", "无认领单")
                        continue
                    try:
                        goto(acc, A_CLAIM, f"s5-app-{tag}")
                        search(acc, c["name"])
                        row = acc.locator(f"tr:has-text('{c['name']}')").first
                        row.click()
                        if not wait_vis(acc, ".o_form_view", 15):
                            shot(acc, f"s5-app-{tag}-timeout")
                            continue
                        time.sleep(2.0)
                        ok, dtxt = click_btn(acc, "action_approve")
                        if dtxt:
                            close_dialog(acc)
                        st = R.sr("ta.payment.claim", [["id", "=", c["id"]]], ["state", "move_id", "approved_by"], 1)
                        s = st[0] if st else {}
                        if s.get("state") == "approved" and s.get("move_id"):
                            DOCS[f"claim_{tag}"]["move_id"] = s["move_id"][0]
                            DOCS[f"claim_{tag}"]["approved_by"] = s["approved_by"][0]
                            rec(f"s5-approve-{tag}", "PASS", f"{c['name']} approved 凭证move={s['move_id'][0]} 审核人={s['approved_by'][1]} dialog={dtxt[:60] if dtxt else '-'}")
                        else:
                            rec(f"s5-approve-{tag}", "FAIL", f"RPC={s} dialog={dtxt[:200] if dtxt else '-'}")
                    except Exception as e:
                        rec(f"s5-approve-{tag}", "FAIL", f"异常 {type(e).__name__} {str(e)[:150]}")
                        shot(acc, f"s5-app-{tag}-timeout")
                try:
                    goto(acc, A_CLAIM, "s5-app-list")
                    shot(acc, "05-收款认领-审核通过.png")
                except Exception:
                    pass
            cacc.close()
        if not accountant_ok:
            rec("s5-审核", "FAIL", "会计登录失败，审核未执行（AC-05 无法用 admin 自审）")

        # 5.4 核对订单已收款
        try:
            ver = {}
            for tag in ["O1", "O2", "O3"]:
                o = orders.get(tag)
                if o:
                    v = R.sr("ta.order", [["id", "=", o["id"]]], ["name", "amount_paid", "amount_open"], 1)
                    ver[tag] = v[0]
            exp = {"O1": 5000.0, "O2": 3200.0, "O3": 0.0}
            okall = all(ver.get(t) and abs(ver[t]["amount_paid"] - exp[t]) < 0.01 for t in exp)
            rec("s5-核对", "PASS" if okall else "FAIL",
                " | ".join(f"{t}={ver[t]['amount_paid'] if t in ver else '?'}/{exp[t]}" for t in exp))
            goto(ad, A_ORDER, "s5-verify")
            search(ad, dep_code)
            shot(ad, "05-订单-已收款核对.png")
        except Exception as e:
            rec("s5-核对", "FAIL", f"{type(e).__name__} {str(e)[:120]}")

        # ========== 步骤6 报表核对 ==========
        try:
            goto(ad, A_PNL, "s6-pnl")
            search(ad, dep_code)
            row_shot(ad, "仿真|海南5日游-20261001", "06-单团损益.png")
            pnl = R.sr("ta.team.pnl", [["departure_id", "=", dep_id]],
                       ["code", "income", "order_total", "cost_total", "profit", "profit_tax_incl"], 3)
            p = pnl[0] if pnl else {}
            if p:
                DOCS["pnl"] = p
                rec("s6-单团损益", "核对", f"income={p['income']} cost={p['cost_total']} 毛利(BS19)={p['profit']} 毛利(含税)={p['profit_tax_incl']} order_total={p['order_total']} | 预期 income=8200 cost=5360 含税毛利=2240")
        except Exception as e:
            rec("s6-单团损益", "FAIL", f"{type(e).__name__} {str(e)[:120]}")

        try:
            goto(ad, A_PAYABLE, "s6-payable")
            search(ad, dep_code)
            row_shot(ad, "仿真|海南5日游-20261001", "06-供应商付款按团.png")
            rows = R.sr("ta.supplier.payable", [["departure_id", "=", dep_id]],
                        ["supplier_id", "item_total", "paid_total", "open_amount", "bill_state"], 10)
            it = round(sum(r["item_total"] for r in rows), 2)
            pd = round(sum(r["paid_total"] for r in rows), 2)
            op = round(sum(r["open_amount"] for r in rows), 2)
            DOCS["payable"] = {"item_total": it, "paid_total": pd, "open": op, "rows": rows}
            rec("s6-供应商付款", "PASS" if abs(it-5360)<0.01 and abs(pd-3960)<0.01 and abs(op-1400)<0.01 else "FAIL",
                f"total={it} paid={pd} open={op} | 预期 5360/3960/1400 rows={[(r['supplier_id'][1], r['item_total'], r['paid_total']) for r in rows]}")
        except Exception as e:
            rec("s6-供应商付款", "FAIL", f"{type(e).__name__} {str(e)[:120]}")

        try:
            goto(ad, A_AGING, "s6-aging")
            search(ad, "仿真")
            if orders.get("O1"):
                row_shot(ad, orders["O1"]["name"], "06-应收账龄-O1.png")
                row_shot(ad, orders["O3"]["name"], "06-应收账龄-O3.png")
            shot(ad, "06-应收账龄.png")
            rows = R.sr("ta.receivable.aging", [["departure_id", "=", dep_id]],
                        ["order_name", "amount_open", "amount_paid", "bucket", "days_overdue"], 10)
            DOCS["aging"] = rows
            okn = len(rows) == 2 and all(r["bucket"] == "b0_30" for r in rows) and \
                  sorted([round(r["amount_open"],2) for r in rows]) == [3000.0, 5600.0]
            rec("s6-应收账龄", "PASS" if okn else "FAIL",
                f"{[(r['order_name'], r['amount_open'], r['bucket']) for r in rows]} | 预期 2行(3000,5600 b0_30)")
        except Exception as e:
            rec("s6-应收账龄", "FAIL", f"{type(e).__name__} {str(e)[:120]}")

        br.close()

    # ========== 汇总 ==========
    print("\n===== SUMMARY =====")
    for tag, st, dt in STEPS:
        print(f"{st:5s} | {tag:22s} | {dt}")
    print("\n===== DOCS =====")
    print(json.dumps(DOCS, ensure_ascii=False, indent=1, default=str))

if __name__ == "__main__":
    main()
