#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端验证：待实施功能占位菜单（admin/admin），并实测 load_menus 可见性。"""
import json, urllib.request, http.cookiejar

BASE = "http://127.0.0.1:8070"
DB = "tms"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def post(endpoint, payload):
    req = urllib.request.Request(f"{BASE}/{endpoint}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=120) as r:
        return json.loads(r.read())

def call_kw(model, method, args, kwargs=None):
    r = post("web/dataset/call_kw", {"jsonrpc": "2.0",
        "params": {"model": model, "method": method, "args": args, "kwargs": kwargs or {}}, "id": 3})
    if "error" in r:
        raise RuntimeError(r["error"].get("data", {}).get("message") or r["error"].get("message") or str(r["error"]))
    return r.get("result")

uid = post("web/session/authenticate",
           {"jsonrpc": "2.0", "params": {"db": DB, "login": "admin", "password": "admin"}, "id": 1})["result"]["uid"]
print("登录成功 uid=%s (admin)" % uid)

# load_menus 返回 dict：key=菜单id字符串 + 'root'；每个节点含 id/name/children/parent_id/action_id/xmlid
menus = call_kw("ir.ui.menu", "load_menus", [False])

pending_ids = list(range(632, 643))  # 632 顶级 + 633..642 十子项
present = {mid: (str(mid) in menus) for mid in pending_ids}

print("=== 待实施功能菜单在 load_menus 中的可见性（实测）===")
for mid in pending_ids:
    node = menus.get(str(mid))
    name = node.get("name") if node else None
    print("  id=%s 可见=%s 名称=%r" % (mid, present[mid], name))

root_ids = menus["root"]["children"]
print("\n旅行社管理(220) 是否顶级可见=%s" % (220 in root_ids))
print("产品导览(628) 是否顶级可见=%s" % (628 in root_ids))

# 对照：一个「有 action」的既有业务菜单是否可见
for probe, label in [(221, "线路产品"), (632, "待实施功能")]:
    print("  对照 id=%s(%s) 在 menus=%s" % (probe, label, str(probe) in menus))
