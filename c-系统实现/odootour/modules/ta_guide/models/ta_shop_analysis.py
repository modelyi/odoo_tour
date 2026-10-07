# -*- coding: utf-8 -*-
from odoo import models, fields


class TaShopAnalysis(models.Model):
    """多维度购物分析（BS-08 §7 [4307][4308][4309-4311] / AC-15）：
    粒度 = 已确认购物记录（按 发团计划 × 购物店 归组）× 已确认订单名单行。

    est_amount 口径：= 该名单行客人数（每行按 1 人）× 该团该店人均购物，
    人均购物 = 组内购物总金额 ÷ 加权前团队人数（= 已确认/行程中/已结算订单
    名单行数，无名单时兜底发团报名数）——按人均×客人数估算，非精确分摊。
    SQL 视图聚合，只读。
    """
    _name = 'ta.shop.analysis'
    _description = '多维度购物分析'
    _auto = False
    _order = 'shop_date desc, id desc'
    _rec_name = 'shop_name'
    _rec_names_search = ['shop_name', 'route_name', 'origin_province']

    line_id = fields.Many2one('ta.order.line', string='名单行', readonly=True)
    order_id = fields.Many2one('ta.order', string='订单', readonly=True)
    partner_id = fields.Many2one('res.partner', string='组团社', readonly=True)
    departure_id = fields.Many2one('ta.departure', string='发团计划', readonly=True)
    route_id = fields.Many2one('ta.route', string='线路', readonly=True)
    route_name = fields.Char(string='线路名称', readonly=True)
    shop_partner_id = fields.Many2one('res.partner', string='购物店', readonly=True)
    shop_name = fields.Char(string='购物店名称', readonly=True)
    shop_date = fields.Date(string='购物日期', readonly=True)
    shop_count = fields.Integer(string='购物笔数', readonly=True)
    kind = fields.Selection([
        ('adult', '成人'),
        ('child', '儿童'),
        ('child_bed', '儿童含床'),
        ('single', '单房差'),
        ('same_tour', '同团升级'),
    ], string='价别', readonly=True)
    gender = fields.Selection([
        ('male', '男'),
        ('female', '女'),
    ], string='性别', readonly=True)
    age_group = fields.Selection([
        ('child', '儿童'),
        ('youth', '青年'),
        ('middle', '中年'),
        ('senior', '老年'),
    ], string='年龄段', readonly=True)
    origin_province = fields.Char(string='客源地', readonly=True)
    est_amount = fields.Float(string='预估购物金额', readonly=True, digits=(15, 2),
                              help='按人均×客人数估算，非精确分摊（BS-08 §7 多维度报表口径）。')
    company_id = fields.Many2one('res.company', string='公司', readonly=True)

    def init(self):
        # id 为 text 拼接：先 DROP 再 CREATE（防列类型变更，范式同 ta.supplier.payable）。
        self.env.cr.execute("DROP VIEW IF EXISTS ta_shop_analysis")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ta_shop_analysis AS
            WITH shop_group AS (
                -- 已确认购物记录按 发团计划×购物店 归组（人均购物分母=组内总额）
                SELECT s.departure_id,
                       s.shop_partner_id,
                       sum(s.total_amount) AS shop_amount,
                       min(s.shop_date) AS shop_date,
                       count(*) AS shop_count
                FROM ta_shop s
                WHERE s.state = 'confirmed'
                GROUP BY s.departure_id, s.shop_partner_id
            ),
            team_heads AS (
                -- 加权前团队人数：已确认/行程中/已结算订单名单行数
                SELECT o.departure_id, count(l.id) AS heads
                FROM ta_order o
                JOIN ta_order_line l ON l.order_id = o.id
                WHERE o.state IN ('confirmed', 'tripping', 'settled')
                GROUP BY o.departure_id
            )
            SELECT (l.id::text || '_' || sg.shop_partner_id::text) AS id,
                   l.id AS line_id,
                   l.order_id AS order_id,
                   o.partner_id AS partner_id,
                   sg.departure_id AS departure_id,
                   d.route_id AS route_id,
                   r.name AS route_name,
                   sg.shop_partner_id AS shop_partner_id,
                   p.name AS shop_name,
                   sg.shop_date AS shop_date,
                   sg.shop_count AS shop_count,
                   l.kind AS kind,
                   l.gender AS gender,
                   l.age_group AS age_group,
                   l.origin_province AS origin_province,
                   d.company_id AS company_id,
                   COALESCE(round((sg.shop_amount
                                   / NULLIF(COALESCE(th.heads, d.seats_used), 0))::numeric, 2),
                            0)::float AS est_amount
            FROM ta_order_line l
            JOIN ta_order o ON o.id = l.order_id
            JOIN shop_group sg ON sg.departure_id = o.departure_id
            JOIN ta_departure d ON d.id = sg.departure_id
            JOIN ta_route r ON r.id = d.route_id
            JOIN res_partner p ON p.id = sg.shop_partner_id
            LEFT JOIN team_heads th ON th.departure_id = sg.departure_id
            WHERE o.state IN ('confirmed', 'tripping', 'settled')
        """)
