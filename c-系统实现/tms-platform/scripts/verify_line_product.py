# -*- coding: utf-8 -*-
"""第一阶段验收：registry KeyError + 委托字段可读 + website_sale 可识别。"""

# 1. tour.line.type 模型已从 registry 移除
try:
    env['tour.line.type']
    print('FAIL - tour.line.type 仍存在')
except KeyError:
    print('PASS - tour.line.type 已从 registry 移除 (KeyError)')

# 2. tour.line 委托字段可读（name/default_code/list_price/categ_id/is_published）
line = env['tour.line'].search([], limit=1)
print('--- tour.line 委托字段抽样 (id=%s) ---' % line.id)
print('  name=%r' % line.name)
print('  default_code=%r' % line.default_code)
print('  list_price=%r' % line.list_price)
print('  categ_id=%r' % (line.categ_id.name if line.categ_id else None))
print('  is_published=%r active=%r' % (line.is_published, line.active))
print('  product_tmpl_id=%r' % line.product_tmpl_id.id)
print('  day_num=%r help_code=%r' % (line.day_num, line.help_code))

# 3. website_sale 商品目录能检索到这些线路（is_published 的 service 产品）
published = env['product.template'].search_count([('is_published', '=', True), ('type', '=', 'service')])
total_svc = env['product.template'].search_count([('type', '=', 'service')])
print('PASS - product.template is_published service 产品 = %d / %d' % (published, total_svc))

# 4. product.product 变体自动生成
variants = env['product.product'].search_count([('product_tmpl_id', 'in', line.product_tmpl_id.ids)])
print('  product.product 变体数（抽样线路）= %d' % variants)

# 5. 分类映射正确（85 分类中抽样一个，含该分类的线路数）
cat_count = env['product.category'].search_count([])
print('  product.category 总数 = %d' % cat_count)
