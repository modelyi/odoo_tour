# -*- coding: utf-8 -*-
from odoo import models, fields, api

# 批5-迭代3（P0-3 AC-16）：购物佣金三列（BS-08 §4.9 经营收入口径）。
# join 条件：ta_guide_commission.departure_id = d.id AND shop_partner_id IS NOT NULL
# AND state IN ('confirmed','settled')——手工路径佣金（无 shop_partner_id）不进购物口径。
_SHOP_COMMISSION_COLS = """,
       COALESCE((SELECT sum(c.commission_total) FROM ta_guide_commission c
                  WHERE c.departure_id = d.id
                    AND c.shop_partner_id IS NOT NULL
                    AND c.state IN ('confirmed','settled')), 0) AS shop_commission,
       COALESCE((SELECT sum(c.commission_tax) FROM ta_guide_commission c
                  WHERE c.departure_id = d.id
                    AND c.shop_partner_id IS NOT NULL
                    AND c.state IN ('confirmed','settled')), 0) AS shop_commission_tax,
       COALESCE((SELECT sum(c.allowance) FROM ta_guide_commission c
                  WHERE c.departure_id = d.id
                    AND c.shop_partner_id IS NOT NULL
                    AND c.state IN ('confirmed','settled')), 0) AS shop_staff_cost
"""


def _ta_team_pnl_view_sql(cr):
    """单团损益视图 SQL（供 ta_dispatch / ta_guide 共用，防两处口径漂移）。

    购物佣金三列仅在 ta_guide 已安装（ta_guide_commission 表存在）时挂载：
    ta_dispatch 独立安装/更新时不引用未创建的表；ta_guide 安装后任何一方
    -u 触发的视图重建都会自动带上三列（表存在性探测）。
    """
    cr.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'ta_guide_commission'
    """)
    shop_cols = _SHOP_COMMISSION_COLS if cr.fetchone() else ""
    return f"""
        CREATE OR REPLACE VIEW ta_team_pnl AS
        SELECT d.id AS id,
               d.id AS departure_id,
               r.name AS route_name,
               d.code AS code,
               d.date_start AS date_start,
               d.company_id AS company_id,
               d.seats_used AS seats_used,
               COALESCE((SELECT sum(o.amount_paid) FROM ta_order o
                          WHERE o.departure_id = d.id
                            AND o.state IN ('confirmed','tripping','settled')), 0) AS income,
               COALESCE((SELECT sum(o.amount_total) FROM ta_order o
                          WHERE o.departure_id = d.id
                            AND o.state IN ('confirmed','tripping','settled')), 0) AS order_total,
               COALESCE((SELECT sum(i.amount) FROM ta_dispatch_item i
                          WHERE i.departure_id = d.id AND i.state = 'confirmed'), 0) AS cost_total
               {shop_cols}
        FROM ta_departure d
        JOIN ta_route r ON r.id = d.route_id
    """


class TaTeamPnl(models.Model):
    """单团核算（BS-19 口径）：收入=已审核认领到本团订单的金额；
    成本=已确认计调单 +（M4 追加）导游报账。SQL 视图聚合，只读。

    批5-迭代3（P0-3 AC-16）：利润双口径——
    - profit_no_shop：不含购物口径（BS-19 原口径）= income − cost_net；
    - profit：含购物口径 = profit_no_shop +（购物佣金总额 − 销项税）− 司陪分成，
      佣金/分成三列由 ta_guide 经 SQL 视图挂载（本模块独立运行时无购物列，两口径相等）。
    """
    _name = 'ta.team.pnl'
    _description = '单团损益'
    _auto = False
    _order = 'date_start desc'
    # 批4-B：SQL 视图无 name 字段，显式指定展示名与全文搜索字段，
    # 搜索框输入计划号/线路名即可过滤（name_search 走 display_name）。
    _rec_name = 'code'
    _rec_names_search = ['code', 'route_name']

    departure_id = fields.Many2one('ta.departure', string='发团计划', readonly=True)
    route_name = fields.Char(string='线路', readonly=True)
    code = fields.Char(string='计划号', readonly=True)
    date_start = fields.Date(string='出发日', readonly=True)
    company_id = fields.Many2one('res.company', string='公司', readonly=True)
    state = fields.Selection(related='departure_id.state', string='发团计划状态')
    seats_used = fields.Integer(string='报名人数', readonly=True)
    income = fields.Float(string='已收款', readonly=True)
    order_total = fields.Float(string='订单总额', readonly=True)
    cost_total = fields.Float(string='成本（含税）', readonly=True)

    @api.depends('income', 'cost_total')
    @api.depends_context('company')
    def _compute_tax_split(self):
        icp = self.env['ir.config_parameter'].sudo()
        split = icp.get_bool('ta_base.cost_tax_split', False)
        rate = icp.get_float('ta_base.default_tax_rate', 0.0)
        for pnl in self:
            cost_net = pnl.cost_total / (1.0 + rate) if (split and rate) else pnl.cost_total
            pnl.cost_net = cost_net
            pnl.profit_no_shop = pnl.income - cost_net
            # AC-16 含购物口径：净佣金收入（佣金总额 − 销项税）− 司陪分成成本。
            # 购物三列由 ta_guide 经 SQL 视图挂载；本模块独立运行时无该列，取 0
            # （无购物数据时两口径恒等）。
            shop_commission = getattr(pnl, 'shop_commission', 0.0) or 0.0
            shop_tax = getattr(pnl, 'shop_commission_tax', 0.0) or 0.0
            shop_staff = getattr(pnl, 'shop_staff_cost', 0.0) or 0.0
            pnl.profit = (pnl.profit_no_shop
                          + (shop_commission - shop_tax) - shop_staff)
            pnl.profit_tax_incl = pnl.income - pnl.cost_total

    cost_net = fields.Float(string='成本（不含税净额）', compute='_compute_tax_split')
    profit_no_shop = fields.Float(string='单团毛利（不含购物）', compute='_compute_tax_split',
                                  help='BS-19 原口径 = 收入 − 成本净额；购物佣金不进收入、'
                                       '司陪分成不进成本。')
    profit = fields.Float(string='单团毛利（含购物）', compute='_compute_tax_split',
                          help='AC-16 Profit = 不含购物毛利 +（购物佣金总额 − 销项税）− 司陪分成。')
    profit_tax_incl = fields.Float(string='毛利（含税口径）', compute='_compute_tax_split')

    def init(self):
        # 收入口径：订单 amount_paid 仅在认领审核后写入（ta_finance），天然=已审核收款。
        # NFR-1：全部直取原值，不做 abs() 方向修正。
        self.env.cr.execute(_ta_team_pnl_view_sql(self.env.cr))
