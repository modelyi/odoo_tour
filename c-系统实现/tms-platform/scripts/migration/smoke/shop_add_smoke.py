#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电商加购闭环冒烟：GET 商品页（拿 session + csrf）→ POST /shop/tour/add → 看 /cart 出数。

这一步打的是**服务端**：`_cart_add(**counts)` 能不能把 departure_id / 五档人数透传到
20 的 website_sale 里（19→20 期间 `_cart_find_product_line` /
`_prepare_order_line_values` 的签名换过），前端合计只是预览。
"""
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = 'http://127.0.0.1:28169'
PATH = '/shop/' + urllib.parse.quote(sys.argv[1] if len(sys.argv) > 1 else 'smoke-线路a-前端冒烟-74')
PRODUCT_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 74
DEPARTURE_ID = int(sys.argv[3]) if len(sys.argv) > 3 else 8

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(path):
    with op.open(BASE + path) as r:
        return r.status, r.read().decode('utf-8', 'replace')


status, html = get(PATH)
csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
print('GET %s -> %s csrf=%s booking=%s' % (
    PATH, status, bool(csrf), 'tour_booking_wrap' in html))
if not csrf:
    sys.exit('没拿到 csrf_token，POST 必 400（假绿）')

post = urllib.parse.urlencode({
    'csrf_token': csrf.group(1),
    'product_id': PRODUCT_ID,
    'departure_id': DEPARTURE_ID,
    'adult_num': 2, 'child_num': 1, 'old_man_num': 0,
    'student_num': 0, 'baby_num': 3,
}).encode()
req = urllib.request.Request(BASE + '/shop/tour/add', data=post,
                             headers={'Referer': BASE + PATH})
try:
    with op.open(req) as r:
        print('POST /shop/tour/add -> %s %s' % (r.status, r.geturl()))
        body = r.read().decode('utf-8', 'replace')
except urllib.error.HTTPError as e:
    print('POST -> HTTP %s' % e.code)
    body = e.read().decode('utf-8', 'replace')
    print(re.search(r'<title>(.*?)</title>', body, re.S).group(1)[:200] if '<title>' in body else '')
    sys.exit(1)

err = re.search(r'tour_error=([^&"\']*)', body)
print('页面里的 tour_error =', urllib.parse.unquote(err.group(1)) if err else '无')

status, cart = get('/shop/cart')
print('GET /shop/cart -> %s  含线路名=%s' % (status, 'SMOKE' in cart))
for m in re.finditer(r'¥\s*[\d,]+\.\d\d', cart):
    pass
amounts = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d\d)', cart)
print('cart 金额样本 =', amounts[:8])
print('cart 行数提示 =', cart.count('o_cart_line_js_half_screen') or cart.count('js_cart_lines'))
print('COOKIES =', [(c.name, c.domain) for c in jar])
