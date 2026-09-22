#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""负例冒烟：加购的**服务端校验分支**必须走 redirect?tour_error=，不能 500。

判据来自 tour_website_sale/controllers/main.py 的 `except ValidationError` 分支：
它会 `_get_product_url()` 再拼 `?tour_error=`。这条路径 GET 冒烟永远走不到。
"""
import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = 'http://127.0.0.1:28169'
PATH = '/shop/' + urllib.parse.quote('smoke-线路a-前端冒烟-74')
PRODUCT_ID, DEPARTURE_ID = 74, 8

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def post_case(label, fields, want_sub):
    with op.open(BASE + PATH) as r:
        html = r.read().decode('utf-8', 'replace')
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if not csrf:
        print('%-26s FAIL 拿不到 csrf_token' % label)
        return False
    data = {'csrf_token': csrf.group(1), 'product_id': PRODUCT_ID}
    data.update(fields)
    req = urllib.request.Request(BASE + '/shop/tour/add',
                                 data=urllib.parse.urlencode(data).encode(),
                                 headers={'Referer': BASE + PATH})
    try:
        with op.open(req) as r:
            code, url, body = r.status, r.geturl(), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        code, url, body = e.code, req.full_url, e.read().decode('utf-8', 'replace')
    err = re.search(r'tour_error=([^&"\']*)', url) or re.search(r'tour_error=([^&"\'\\]*)', body)
    msg = urllib.parse.unquote(err.group(1)) if err else ''
    ok = code in (200, 303) and want_sub in msg
    print('%-26s %s code=%s -> %s' % (label, 'PASS' if ok else 'FAIL', code, msg or url[:60]))
    return ok


fails = 0
cases = [
    ('未选班期', {'departure_id': '', 'adult_num': 1}, '请选择发团日期'),
    ('人数全 0', {'departure_id': DEPARTURE_ID, 'adult_num': 0}, '至少填写'),
    ('超余位', {'departure_id': DEPARTURE_ID, 'adult_num': 99}, '余位不足'),
    ('班期不存在', {'departure_id': 9999, 'adult_num': 1}, '请选择发团日期'),
]
for label, fields, want in cases:
    fails += 0 if post_case(label, fields, want) else 1

print('\n%s' % ('ALL PASS' if not fails else 'FAIL %d' % fails))
sys.exit(1 if fails else 0)
