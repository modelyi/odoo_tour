# -*- coding: utf-8 -*-
"""门户/电商冒烟夹具：在 b1gate6 上造一条「可报名的线路产品 + 已发布班期」。

只造数据，不改代码；跑法见 /tmp/b0/serve_shop.sh。
"""
import datetime

Line = env['tour.line']
Dep = env['tour.departure']

tmpl = env['product.template'].create({
    'name': 'SMOKE 线路A（前端冒烟）',
    'type': 'service',
    'sale_ok': True,
    'list_price': 1000.0,
    'is_published': True,
})
line = Line.create({
    'product_tmpl_id': tmpl.id,
    'day_num': 3,
    'child_price': 500.0,
    'old_man_price': 700.0,
    'student_price': 600.0,
    'baby_price': 100.0,
})
dep = Dep.create({
    'line_id': line.id,
    'start_date': datetime.date.today() + datetime.timedelta(days=30),
    'seats': 20,
    'price_adult': 1200.0,
    'price_child': 550.0,
    'price_old_man': 720.0,
    'price_student': 640.0,
    'price_baby': 120.0,
})
dep.action_publish() if hasattr(dep, 'action_publish') else dep.write({'state': 'published'})
env.cr.flush()
env.invalidate_all()
d = Dep.browse(dep.id)
product = env['product.product'].search([('product_tmpl_id', '=', tmpl.id)], limit=1)
print('SEED product_tmpl_id=%s product_id=%s line_id=%s departure_id=%s state=%s' % (
    tmpl.id, product.id, line.id, d.id, d.state))
print('SEED url=%s' % tmpl.website_url)
print('SEED remain=%s prices=%s' % (d.remain_seats, d.get_online_prices()))
print('SEED price_json=%s' % d._price_json())
print('SEED avail=%s' % line._website_available_departures().ids)
print('SEED line_of_product=%s' % tmpl._get_tour_line().id)
# `odoo-bin shell` 从 stdin 跑脚本时**默认回滚**（20 实测：不加这行则上面全是幻影，
# 页面照样 404），夹具必须显式提交。
env.cr.commit()
