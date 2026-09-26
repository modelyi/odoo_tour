# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaDispatchItem(models.Model):
    """计调资源条目：一单团一资源一行；确认后生成供应商账单草稿。

    NFR-2：move_id 已有值不得重复生成；条目确认后金额锁定，改价须取消重开。
    """
    _name = 'ta.dispatch.item'
    _description = '计调派工条目'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'departure_id desc, kind, id'

    # 语义参考 tour_base/constants.py::SUP_TYPE，按新产品口径增导游/领队
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

    departure_id = fields.Many2one(
        'ta.departure', string='班期', required=True, ondelete='cascade',
        index=True, tracking=True)
    route_id = fields.Many2one(related='departure_id.route_id', store=True)
    kind = fields.Selection(KIND, required=True, tracking=True)
    supplier_id = fields.Many2one('res.partner', string='供应商', required=True, tracking=True)
    name = fields.Char(string='项目说明', required=True)
    date_start = fields.Date(related='departure_id.date_start', string='开始日期')
    qty = fields.Float(string='数量', default=1.0, required=True)
    unit_price = fields.Float(string='单价', required=True)
    amount = fields.Float(compute='_compute_amount', store=True)
    note = fields.Char()
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已确认'),
        ('cancel', '已取消'),
    ], default='draft', required=True, tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string='供应商账单', readonly=True, copy=False)

    _amount_check = models.Constraint(
        "check(qty > 0 and unit_price >= 0)",
        '数量必须为正，单价不得为负（NFR-1：金额方向不取绝对值）。')

    @api.depends('qty', 'unit_price')
    def _compute_amount(self):
        for item in self:
            item.amount = item.qty * item.unit_price

    def action_confirm(self):
        for item in self:
            if item.state != 'draft':
                raise UserError("只有草稿条目可以确认。")
            if item.departure_id.state not in ('open', 'confirmed', 'departed', 'settled'):
                raise UserError("班期当前状态不允许确认派工。")
            item.move_id = item._create_supplier_bill()
            item.state = 'confirmed'
        return True

    def action_cancel(self):
        for item in self:
            if item.state == 'cancel':
                raise UserError("条目已取消。")
            if item.move_id:
                if item.move_id.state != 'draft':
                    raise UserError("供应商账单已过账，请先在会计侧处理，不能直接取消派工。")
                item.move_id.unlink()
            item.state = 'cancel'

    def action_reset_draft(self):
        for item in self:
            if item.state != 'cancel':
                raise UserError("只有已取消条目可以恢复为草稿。")
            if item.move_id:
                raise UserError("该条目仍挂着账单，无法恢复。")
            item.state = 'draft'

    def _create_supplier_bill(self):
        self.ensure_one()
        partner = self.supplier_id
        # Odoo 20：费用科目走公司默认值（res.company.expense_account_id），partner 级已移除
        expense = self.company_id.expense_account_id
        if not expense:
            raise UserError("公司未设置默认费用科目（会计设置→费用科目），无法生成账单。")
        journal = self.env['account.journal'].search(
            [('type', '=', 'purchase'), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal:
            raise UserError("当前公司没有采购日记账，无法生成供应商账单。")
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': journal.id,
            'partner_id': partner.id,
            'date': self.date_start or fields.Date.context_today(self),
            'ref': f"派工 {self.departure_id.code or ''} {self.name}",
            'invoice_line_ids': [(0, 0, {
                'name': self.name,
                'account_id': expense.id,
                'quantity': self.qty,
                'price_unit': self.unit_price,
            })],
        })
        return move


class TaDepartureDispatch(models.Model):
    _inherit = 'ta.departure'

    dispatch_item_ids = fields.One2many('ta.dispatch.item', 'departure_id', string='派工条目')
    dispatch_cost_total = fields.Float(compute='_compute_dispatch_cost', store=True)

    @api.depends('dispatch_item_ids.state', 'dispatch_item_ids.amount')
    def _compute_dispatch_cost(self):
        for dep in self:
            dep.dispatch_cost_total = sum(
                dep.dispatch_item_ids.filtered(lambda i: i.state == 'confirmed').mapped('amount'))
