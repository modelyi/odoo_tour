#!/usr/bin/env python3
"""S0 影子实例验收冒烟（无真浏览器，按"渲染 + 状态码 + 后端取值"三层判）。

  PWFILE=/tmp/b0/.smoke_pw_s0 python3 s0_smoke.py [base_url] [登录名文件]

为什么不用 requests/selenium：B 阶段判据（TDS-30 #23 / 待签字口径②）明确
"前端无真浏览器点击"，所以这里只用标准库，保证在任何一台机器上都能复跑。
每条检查都打 PASS/FAIL 并以退出码汇总 —— 冒烟不许"人看一眼就算过"。
"""
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:28169"
PWFILE = os.environ.get("PWFILE", "/tmp/b0/.smoke_pw_s0")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("%-46s %-5s %s" % (name, "PASS" if ok else "FAIL", detail))


def http_get(path, expect=None):
    url = BASE + path
    try:
        r = opener.open(url, timeout=120)
        body = r.read()
        return r.getcode(), body, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def jsonrpc(path, params):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params,
                         "id": 1}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=180) as r:
            return json.loads(r.read())["result"]
    except Exception as e:                                    # noqa: BLE001
        return {"__error__": str(e)}


def call_kw(model, method, args=None, kwargs=None):
    return jsonrpc("/web/dataset/call_kw", {
        "model": model, "method": method, "args": args or [],
        "kwargs": kwargs or {}, "context": {}})


def main():
    pw = open(PWFILE, encoding="utf-8").read().strip()

    # 1) 未登录：登录页与门户路由都必须"有响应且不是 500"
    code, body, _ = http_get("/web/login")
    check("GET /web/login 200", code == 200 and b"login" in body.lower(), "code=%s" % code)
    code, body, _ = http_get("/my/home")
    check("GET /my/home 未登录不 500", code in (200, 301, 302, 303), "code=%s" % code)

    # 2) 登录（密码只从 600 文件读，绝不打印）
    sess = jsonrpc("/web/session/authenticate", {"db": "s0tour", "login": "admin", "password": pw})
    uid = (sess or {}).get("uid") if isinstance(sess, dict) else None
    check("admin 登录成功", bool(uid), "uid=%s" % uid)
    if not uid:
        finish()

    # 3) 业务对象真的在 20 上取得出数（后端取值层）
    for model, domain, want, label in [
            ("tour.plan", [], 86927, "tour.plan 行数"),
            ("account.move", [("state", "=", "posted")], 276541, "已过账凭证行数"),
            ("tour.guide", [], 2173, "tour.guide 行数"),
            ("account.move.line", [], 818693, "分录行数")]:
        r = call_kw(model, "search_count", [domain])
        got = r if isinstance(r, int) else -1
        check(label, got == want, "影子=%s 期望=%s" % (got, want))

    # 4) 视图与记录取值层。
    #    注意 20 的 RPC 协议变了（实测）：get_views 的参数是 **[[view_id, view_type], …]**
    #    （19 是 [{type:…}]）；web_search_read/web_read_group 改收 specification dict。
    #    所以这里用仍然兼容的 ORM 级 search_read/read_group —— 冒烟要判"数据在不在、
    #    视图编不编得出来"，不必绑死在某个 web 协议版本上。
    plans = call_kw("tour.plan", "search_read", [],
                    {"domain": [], "fields": ["display_name"], "limit": 3})
    ids = [p["id"] for p in plans] if isinstance(plans, list) else []
    names = [p.get("display_name") for p in plans] if isinstance(plans, list) else []
    check("tour.plan 取到真实记录", len(ids) == 3, str(names)[:80])
    check("tour.plan 记录有真实标题", any(names), str(names)[:80])

    view = call_kw("tour.plan", "get_views", [[[False, "list"], [False, "form"]]])
    ok = isinstance(view, dict) and len((view.get("views") or {})) >= 2
    check("tour.plan list+form 视图可编译", ok, "" if ok else json.dumps(view)[:200])

    # 5) 单据 QWeb 渲染（跨版本最容易坏的一层：t-call / 字段改名 / 模板搬家）
    one = ids[0] if ids else None
    rep = call_kw("ir.actions.report", "search_read",
                  [["model", "=", "tour.plan"]],
                  {"fields": ["report_name", "report_type", "name"], "limit": 8})
    tried = rendered = 0
    for r in rep if isinstance(rep, list) else []:
        rn, rt = r.get("report_name"), r.get("report_type")
        if not rn or not one or rt not in ("qweb-pdf", "qweb-html"):
            continue
        tried += 1
        if rt == "qweb-pdf":
            code, body, _ = http_get("/report/pdf/%s/%s" % (rn, one))
            if code == 200 and body[:4] == b"%PDF":
                rendered += 1
        else:
            code, body, _ = http_get("/report/html/%s/%s" % (rn, one))
            if code == 200:
                rendered += 1
    check("tour.plan 单据渲染 (qweb)", rendered > 0,
          "成功 %d / 尝试 %d（候选 %d 个报表）" % (rendered, tried, len(rep or [])))

    # 6) 导游可见性（ACL 层）：search_count 过不代表读得到 —— 中间表 res_groups_users_rel
    #    没搬时 admin 不属于任何组，这里第一条 records 调用就会 AccessError。
    gu = call_kw("tour.guide", "search_read", [],
                 {"domain": [], "fields": ["display_name"], "limit": 2})
    guok = isinstance(gu, list) and len(gu) > 0
    check("tour.guide 可读取（组映射生效）", guok,
          str(gu)[:120] if guok else json.dumps(gu)[:200])

    # 7) 附件下载（filestore 并集是否真的齐了）
    att = call_kw("ir.attachment", "search_read", [],
                  {"domain": [["store_fname", "!=", False], ["res_model", "=", "tour.plan"]],
                   "fields": ["name"], "limit": 3})
    aids = [a["id"] for a in att if a.get("id")] if isinstance(att, list) else []
    got = 0
    for a_id in aids:
        code, body, _ = http_get("/web/content/%s?original=false" % a_id)
        if code == 200 and len(body) > 0:
            got += 1
    check("tour.plan 附件可下载", got > 0, "成功 %d/%d" % (got, len(aids)))

    # 8) 财务口径：分组聚合必须出数。20 的 read_group 参数名是 aggregates（不是 fields），
    #    web_read_group 换成了 specification/gateway 协议 —— 冒烟走 ORM 级调用最稳。
    tot = call_kw("account.move", "read_group",
                  [[("state", "=", "posted")], ["journal_id"], ["amount_total"]],
                  {"limit": 20})
    grp = tot if isinstance(tot, list) else []
    s = sum(float(g.get("amount_total") or 0) for g in grp)
    check("account.move 分组聚合出数", len(grp) > 0,
          "%d 个日记账分组，合计 %.2f" % (len(grp), s))

    finish()


def finish():
    bad = [n for n, ok, _ in RESULTS if not ok]
    print("-" * 70)
    print("冒烟: %d 项，失败 %d 项 %s" % (len(RESULTS), len(bad), ("→ " + ", ".join(bad)) if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
