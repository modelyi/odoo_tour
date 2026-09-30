# -*- coding: utf-8 -*-
from odoo import models, fields


class TaSupplierPayable(models.Model):
    """供应商应付汇总（批3-2 付款闭环）：粒度 = 发团计划 × 供应商。

    付款动作走会计原生路径（账单过账→登记付款），本视图只做透出与核数：
    - item_total   = Σ 已确认计调条目金额（应付发生额口径）；
    - bill_total   = Σ 条目挂账账单面额（草稿+已过账均计，作废不计）；
    - paid_total   = 账单已付（已过账单 amount_total - amount_residual）
                     + 历史直写（无账单条目 paid_date 有值 → 计其条目全额，
                       批3-3 迁移仅对"旧系统已付清"条目写 paid_date）；
    - open_amount  = item_total - paid_total（未付余额，可正可负不取绝对值，NFR-1）；
    - bill_state   = 组内账单过账状态汇总：任一草稿→draft；否则有已过账→posted；
                     全无有效账单→none。
    SQL 视图聚合，只读（范式同 ta.team.pnl / ta.scenic.contribution）。
    """
    _name = 'ta.supplier.payable'
    _description = '供应商付款（按团）'
    _auto = False
    _order = 'departure_date desc, supplier_id'

    departure_id = fields.Many2one('ta.departure', string='发团计划', readonly=True)
    supplier_id = fields.Many2one('res.partner', string='供应商', readonly=True)
    route_name = fields.Char(string='线路', readonly=True)
    departure_date = fields.Date(string='出发日', readonly=True)
    kinds = fields.Char(string='资源类别', readonly=True)
    item_total = fields.Float(string='应付条目额', readonly=True)
    bill_total = fields.Float(string='账单面额', readonly=True)
    paid_total = fields.Float(string='已付合计', readonly=True)
    open_amount = fields.Float(string='未付余额', readonly=True)
    bill_state = fields.Selection([
        ('none', '无账单'),
        ('draft', '账单草稿'),
        ('posted', '账单已过账'),
    ], string='账单状态', readonly=True)
    company_id = fields.Many2one('res.company', string='公司', readonly=True)

    def init(self):
        # id 为 text 拼接：CREATE OR REPLACE 不允许改列类型 → 先 DROP（坑㉟）
        self.env.cr.execute("DROP VIEW IF EXISTS ta_supplier_payable")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ta_supplier_payable AS
            WITH agg AS (
                SELECT i.departure_id,
                       i.supplier_id,
                       string_agg(DISTINCT i.kind::text, ',' ORDER BY i.kind::text)
                           AS kinds,
                       COALESCE(sum(i.amount), 0) AS item_total,
                       COALESCE(sum(CASE WHEN mv.state IN ('draft', 'posted')
                                         THEN mv.amount_total ELSE 0 END), 0)
                           AS bill_total,
                       COALESCE(sum(CASE WHEN mv.state = 'posted'
                                         THEN mv.amount_total - mv.amount_residual
                                         ELSE 0 END), 0)
                       + COALESCE(sum(CASE WHEN i.move_id IS NULL
                                            AND i.paid_date IS NOT NULL
                                           THEN i.amount ELSE 0 END), 0)
                           AS paid_total,
                       CASE
                         WHEN count(*) FILTER (WHERE mv.state = 'draft') > 0
                              THEN 'draft'
                         WHEN count(*) FILTER (WHERE mv.state = 'posted') > 0
                              THEN 'posted'
                         ELSE 'none' END AS bill_state
                FROM ta_dispatch_item i
                LEFT JOIN account_move mv ON mv.id = i.move_id
                WHERE i.state = 'confirmed'
                GROUP BY i.departure_id, i.supplier_id
            )
            SELECT (a.departure_id::text || '_' || a.supplier_id::text) AS id,
                   a.departure_id AS departure_id,
                   a.supplier_id AS supplier_id,
                   r.name AS route_name,
                   d.date_start AS departure_date,
                   a.kinds::text AS kinds,
                   round(a.item_total::numeric, 2)::float AS item_total,
                   round(a.bill_total::numeric, 2)::float AS bill_total,
                   round(a.paid_total::numeric, 2)::float AS paid_total,
                   round((a.item_total - a.paid_total)::numeric, 2)::float
                       AS open_amount,
                   a.bill_state::text AS bill_state,
                   d.company_id AS company_id
            FROM agg a
            JOIN ta_departure d ON d.id = a.departure_id
            JOIN ta_route r ON r.id = d.route_id
        """)
