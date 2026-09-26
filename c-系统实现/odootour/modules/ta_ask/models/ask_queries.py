# -*- coding: utf-8 -*-
"""白名单查询函数实现：只读聚合，运行在 with_user(asker) 环境下，
天然继承 ta_* ACL 与 record rule（权限口径=提问人）。

一期启用 4 个（ask_catalog 中 enabled=False 的函数暂缓）。
"""
from odoo import models, fields


def _month_bounds(month_str):
    """'YYYY-MM' → (first_day, next_first_day) 字符串对。"""
    y, m = int(month_str[:4]), int(month_str[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return '%s-%02d-01' % (y, m), '%s-%02d-01' % (ny, nm)


class TaPaymentClaimAsk(models.Model):
    _inherit = 'ta.payment.claim'

    def _ask_collections_month(self, args):
        month = args.get('month') or fields.Date.context_today(self).strftime('%Y-%m')
        first, next_first = _month_bounds(month)
        claims = self.search([
            ('state', '=', 'approved'),
            ('date', '>=', first), ('date', '<', next_first)])
        total = sum(claims.mapped('amount'))
        return {
            'title': '%s 月已审核收款' % month,
            'columns': ['月份', '认领单数', '到账合计'],
            'rows': [[month, len(claims), total]],
            'note': '',
        }


class TaTeamPnlAsk(models.Model):
    _inherit = 'ta.team.pnl'

    def _ask_top_departure_pnl(self, args):
        topn = args.get('topn') or 5
        order = args.get('order') or 'top'
        self.env.flush_all()  # SQL 视图模型：读取前先落盘（ODOO_PIN 陷阱⑨）
        rows = [[p.code, p.route_name, p.income, p.cost_total, p.profit]
                for p in self.search([], limit=200)]
        rows.sort(key=lambda r: r[4], reverse=(order == 'top'))
        return {
            'title': '班期毛利%s TOP%d（BS-19 口径）' % ('排行' if order == 'top' else '垫底', topn),
            'columns': ['班期', '线路', '已收款', '成本（含税）', '毛利'],
            'rows': rows[:topn],
            'note': '',
        }


class TaOrderAsk(models.Model):
    _inherit = 'ta.order'

    def _ask_receivable_top(self, args):
        topn = args.get('topn') or 10
        orders = self.search(
            [('state', 'in', ('confirmed', 'tripping', 'settled')),
             ('amount_open', '>', 0.01)],
            order='amount_open desc', limit=topn)
        rows = [[o.name, o.partner_id.display_name or '-', o.heads,
                 o.amount_total, o.amount_paid, o.amount_open] for o in orders]
        return {
            'title': '未收金额 TOP%d' % topn,
            'columns': ['订单号', '客户', '人数', '应收总额', '已到账', '未收'],
            'rows': rows,
            'note': '未收=应收-已审核到账认领；草稿/取消订单不含。',
        }

    def _ask_order_month_stats(self, args):
        month = args.get('month') or fields.Date.context_today(self).strftime('%Y-%m')
        first, next_first = _month_bounds(month)
        orders = self.search([
            ('state', 'in', ('confirmed', 'tripping', 'settled')),
            ('date_confirm', '>=', first), ('date_confirm', '<', next_first)])
        return {
            'title': '%s 月报名统计' % month,
            'columns': ['月份', '订单数', '报名人数', '应收总额'],
            'rows': [[month, len(orders), sum(orders.mapped('heads')),
                      sum(orders.mapped('amount_total'))]],
            'note': '',
        }
