# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaShopCost(models.Model):
    """购物成本（BS-08 §4.4 菜单 [4305]）：回扣/礼品/其他杂项成本，只做录入与统计，
    不生成凭证、不参与佣金计算。

    合规口径：[增值税暂行条例] 购物成本不可从增值税计税依据中扣除；
    净利润 = 佣金总额 − 购物成本 − 分成支出（§4.4 业务规则 2）。
    """
    _name = 'ta.shop.cost'
    _description = '购物成本'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'departure_id desc, id desc'

    departure_id = fields.Many2one(
        'ta.departure', string='发团计划', required=True, tracking=True,
        domain="[('state', 'in', ('confirmed', 'departed', 'settled'))]")
    plan_code = fields.Char(related='departure_id.code', string='计划号')
    route_id = fields.Many2one('ta.route', related='departure_id.route_id',
                               store=True, string='线路')
    supplier_id = fields.Many2one(
        'res.partner', string='购物店', required=True, tracking=True,
        domain="[('supplier_rank', '>', 0)]")
    supplier_name = fields.Char(related='supplier_id.name', string='购物店名称')
    cost_type = fields.Selection([
        ('rebate', '回扣'),
        ('gift', '礼品'),
        ('other', '其他'),
    ], string='成本类型', required=True, default='other', tracking=True)
    amount = fields.Float(
        string='成本金额', required=True, digits=(15, 2), tracking=True,
        help='[增值税暂行条例] 购物成本不可从增值税计税依据中扣除。')
    remark = fields.Text(string='备注')

    @api.constrains('amount')
    def _check_amount(self):
        for c in self:
            if c.amount <= 0:
                raise UserError("购物成本金额必须大于 0。")

    def init(self):
        # 模型初始化次序不保证对账视图后建：本表落库后重建对账视图挂购物成本列。
        from .ta_shop_reconciliation import _ta_shop_reconciliation_view_sql
        self.env.cr.execute("DROP VIEW IF EXISTS ta_shop_reconciliation")
        self.env.cr.execute(_ta_shop_reconciliation_view_sql(self.env.cr))
