"""清掉冒烟夹具（临时用户、导游档案、线路产品与班期、由它们产生的购物车）。

留证据的方式不是"把夹具留在库里"，而是日志与 `d-交付验收` 的报告；夹具一律删干净，
否则下一次 dry-run 的行数核对会被这些额外记录污染（B2 判据是逐表行数）。

跑法：`... odoo-bin shell -d <库> ... < smoke/teardown_smoke_fixtures.py`
（20 的 shell 从 stdin 跑**默认回滚**，所以本脚本自己 `env.cr.commit()`。）
"""
env = env  # noqa: F821  (odoo-bin shell 注入)

# 全部按"夹具自己的名字"圈定，绝不按"表里有记录"圈定 —— 这个脚本可能在别的库上被跑到。
lines = env['tour.line'].sudo().search([('product_tmpl_id.name', 'like', 'SMOKE%')])
deps = env['tour.departure'].sudo().search([('line_id', 'in', lines.ids)])
tmpl = env['product.template'].sudo().search([('name', 'like', 'SMOKE%')])
products = env['product.product'].sudo().search([('product_tmpl_id', 'in', tmpl.ids)])
carts = env['sale.order'].sudo().search([
    ('order_line.product_id', 'in', products.ids),
    ('state', '=', 'draft')])
guides = env['tour.guide'].sudo().search([('guide_code', 'like', 'GD_SMOKE%')])
users = env['res.users'].sudo().search([('login', 'like', 'smoke_bot_%')])

print('FIXTURES carts=%s deps=%s lines=%s templates=%s guides=%s users=%s' % (
    carts.mapped('id'), deps.mapped('id'), lines.mapped('id'),
    tmpl.mapped('id'), guides.mapped('id'), users.mapped('login')))

# 顺序：单据 → 配置 → 档案 → 用户；每步失败都点名，不静默（残留要让下一个人看见）。
steps = [
    ('sale.order.line', env['sale.order.line'].sudo().search(
        [('order_id', 'in', carts.ids)])),
    ('sale.order', carts),
    ('tour.departure', deps),
    ('tour.line', lines),
    ('product.template', tmpl),
    ('tour.guide', guides),
    ('res.users', users),
]
for label, recs in steps:
    if not recs:
        continue
    try:
        recs.sudo().unlink()
        print('UNLINKED %s %s' % (label, recs.mapped('id') or recs.mapped('login')))
    except Exception as exc:
        print('UNLINK LEFT %s: %s' % (label, str(exc).splitlines()[0][:160]))
print('LEFT carts=%s departures=%s smoke_templates=%s smoke_guides=%s smoke_users=%s' % (
    env['sale.order'].sudo().search_count([('order_line.product_id', 'in', products.ids)]),
    env['tour.departure'].sudo().search_count([]),
    env['product.template'].sudo().search_count([('name', 'like', 'SMOKE%')]),
    env['tour.guide'].sudo().search_count([('guide_code', 'like', 'GD_SMOKE%')]),
    env['res.users'].sudo().search_count([('login', 'like', 'smoke_bot_%')])))
env.cr.commit()
