# -*- coding: utf-8 -*-
from odoo import models, fields


class TaShopReconciliation(models.Model):
    """购物对账（BS-08 §7 [4316] / AC-13）：粒度 = 购物店 × 公司。
    - commission_payable 应付佣金 = Σ 已确认/已结算购物佣金单佣金总额（含税）；
    - commission_tax 销项税 = Σ 佣金增值税额；
    - staff_share 司陪分成 = Σ 佣金单 allowance（各分成行税前应发）；
    - company_retain 旅行社留存 = Σ 佣金单留存（佣金总额 − 税前应发）；
    - paid_total 已付佣金：购物批量收款（AC-17）不在本批范围，固定为 0，口径待接。
    SQL 视图聚合，只读（范式同 ta.team.pnl）。
    """
    _name = 'ta.shop.reconciliation'
    _description = '购物对账'
    _auto = False
    _order = 'shop_partner_id'
    # SQL 视图无 name 字段：显式指定展示名与全文搜索字段（范式同 ta.team.pnl）。
    _rec_name = 'shop_name'
    _rec_names_search = ['shop_name']

    company_id = fields.Many2one('res.company', string='公司', readonly=True)
    shop_partner_id = fields.Many2one('res.partner', string='购物店', readonly=True)
    shop_name = fields.Char(string='购物店名称', readonly=True)
    commission_payable = fields.Float(string='应付佣金（含税）', readonly=True, digits=(15, 2))
    commission_tax = fields.Float(string='佣金销项税', readonly=True, digits=(15, 2))
    staff_share = fields.Float(string='司陪分成（税前应发）', readonly=True, digits=(15, 2))
    company_retain = fields.Float(string='旅行社留存', readonly=True, digits=(15, 2))
    paid_total = fields.Float(string='已付佣金', readonly=True, digits=(15, 2),
                              help='购物批量收款（AC-17）不在本批范围，固定为 0，口径待接。')
    commission_count = fields.Integer(string='佣金笔数', readonly=True)
    last_commission_date = fields.Date(string='最近佣金日期', readonly=True)

    def init(self):
        # id 为 text 拼接：先 DROP 再 CREATE（防列类型变更，范式同 ta.supplier.payable）。
        self.env.cr.execute("DROP VIEW IF EXISTS ta_shop_reconciliation")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ta_shop_reconciliation AS
            SELECT (c.company_id::text || '_' || c.shop_partner_id::text) AS id,
                   c.company_id AS company_id,
                   c.shop_partner_id AS shop_partner_id,
                   p.name AS shop_name,
                   round(sum(c.commission_total)::numeric, 2)::float AS commission_payable,
                   round(sum(c.commission_tax)::numeric, 2)::float AS commission_tax,
                   round(sum(c.allowance)::numeric, 2)::float AS staff_share,
                   round(sum(c.company_retain)::numeric, 2)::float AS company_retain,
                   0.0::float AS paid_total,
                   count(*)::int AS commission_count,
                   max(c.date) AS last_commission_date
            FROM ta_guide_commission c
            JOIN res_partner p ON p.id = c.shop_partner_id
            WHERE c.shop_partner_id IS NOT NULL
              AND c.state IN ('confirmed', 'settled')
            GROUP BY c.company_id, c.shop_partner_id, p.name
        """)
