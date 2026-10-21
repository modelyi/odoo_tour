# -*- coding: utf-8 -*-
from odoo import models, fields, api


def _ta_dispatch_summary_view_sql(cr):
    """计调成本分析视图 SQL（批7）：供应商 × 资源类型 × 月 聚合。

    口径与 ta.supplier.payable / ta.team.pnl 一致：
    - amount_total / confirmed_count 仅计 state IN ('confirmed','completed')；
    - bill_total / paid_total / unpaid_total 仅计已过账账单（m.state='posted'），
      NFR-1：全部直取原值，不做 abs() 方向修正。
    """
    return """
        CREATE OR REPLACE VIEW ta_dispatch_summary AS
        SELECT row_number() OVER () AS id,
               i.company_id AS company_id,
               i.kind AS kind,
               i.supplier_id AS supplier_id,
               to_char(d.date_start, 'YYYY-MM') AS month,
               count(*) AS item_count,
               count(*) FILTER (WHERE i.state IN ('confirmed', 'completed'))
                   AS confirmed_count,
               count(*) FILTER (WHERE i.state = 'completed') AS completed_count,
               count(*) FILTER (WHERE i.state = 'cancel') AS cancelled_count,
               COALESCE(sum(i.amount) FILTER
                        (WHERE i.state IN ('confirmed', 'completed')), 0)
                   AS amount_total,
               COALESCE(sum(m.amount_total) FILTER (WHERE m.state = 'posted'), 0)
                   AS bill_total,
               COALESCE(sum(m.amount_total - m.amount_residual)
                        FILTER (WHERE m.state = 'posted'), 0)
                   AS paid_total,
               COALESCE(sum(m.amount_residual) FILTER (WHERE m.state = 'posted'), 0)
                   AS unpaid_total
        FROM ta_dispatch_item i
        JOIN ta_departure d ON d.id = i.departure_id
        LEFT JOIN account_move m ON m.id = i.move_id
        GROUP BY i.company_id, i.kind, i.supplier_id, to_char(d.date_start, 'YYYY-MM')
    """


class TaDispatchSummary(models.Model):
    """计调成本分析（BS-03 US-03-09）：资源预订完成率与成本，评估计调操作质量。

    SQL 视图聚合，只读；行粒度 = 公司 × 资源类型 × 供应商 × 发团月。
    """
    _name = 'ta.dispatch.summary'
    _description = '计调成本分析'
    _auto = False
    _order = 'month desc, kind, supplier_id'
    # 批4 教训（5.2/5.4）：SQL 视图显式声明展示名 + 配 search view；
    # _rec_names_search 仅支持 char 字段，供应商检索走 search view 的 M2O 域。
    _rec_name = 'supplier_id'

    KIND = [
        ('ditch', '地接社'),
        ('hotel', '酒店'),
        ('meal', '餐厅'),
        ('vehicle', '车队'),
        ('ticket', '票务'),
        ('scenic', '景区'),
        ('guide', '导游'),
        ('leader', '领队'),
        ('other', '其他'),
    ]

    company_id = fields.Many2one('res.company', string='公司', readonly=True)
    kind = fields.Selection(KIND, string='资源类型', readonly=True)
    supplier_id = fields.Many2one('res.partner', string='供应商', readonly=True)
    month = fields.Char(string='发团月', readonly=True)
    item_count = fields.Integer(string='条目数', readonly=True)
    confirmed_count = fields.Integer(string='已确认/完成数', readonly=True)
    completed_count = fields.Integer(string='已完成数', readonly=True)
    cancelled_count = fields.Integer(string='已取消数', readonly=True)
    amount_total = fields.Float(string='成本合计', readonly=True,
                                help='已确认 + 已完成条目金额。')
    bill_total = fields.Float(string='账单金额', readonly=True,
                              help='已过账供应商账单票面金额。')
    paid_total = fields.Float(string='已付金额', readonly=True)
    unpaid_total = fields.Float(string='未付金额', readonly=True)
    confirm_rate = fields.Float(compute='_compute_confirm_rate', string='确认完成率 %')

    @api.depends('item_count', 'confirmed_count')
    def _compute_confirm_rate(self):
        for row in self:
            row.confirm_rate = (
                row.confirmed_count * 100.0 / row.item_count) if row.item_count else 0.0

    def init(self):
        self.env.cr.execute(_ta_dispatch_summary_view_sql(self.env.cr))
