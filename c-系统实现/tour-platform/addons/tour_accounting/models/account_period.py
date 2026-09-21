# -*- coding: utf-8 -*-
"""会计期间管理。

旅行社财务通用期间管理功能，控制所有财务操作的期间。
"""
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import date


class TourAccountPeriod(models.Model):
    _name = 'tour.account.period'
    _description = '会计期间'
    _order = 'date_start desc'
    
    name = fields.Char('期间名称', required=True)
    code = fields.Char('期间编码', required=True, help='格式：YYYYMM，如 202609')
    date_start = fields.Date('开始日期', required=True)
    date_end = fields.Date('结束日期', required=True)
    state = fields.Selection([
        ('draft', '草稿'),
        ('open', '开放'),
        ('closed', '已关闭'),
    ], string='状态', default='draft', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='公司', 
                                  default=lambda self: self.env.company)
    note = fields.Text('备注')
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', '期间编码必须唯一！'),
    ]
    
    @api.model
    def get_period_by_date(self, check_date, company=None):
        """根据日期获取会计期间"""
        if not check_date:
            return False
        if isinstance(check_date, str):
            check_date = fields.Date.from_string(check_date)
        
        domain = [
            ('date_start', '<=', check_date),
            ('date_end', '>=', check_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        
        return self.search(domain, limit=1)
    
    @api.model
    def check_period_open(self, check_date, company=None, raise_error=True):
        """检查指定日期的期间是否开放"""
        period = self.get_period_by_date(check_date, company)
        
        if not period:
            if raise_error:
                raise UserError(f'日期 {check_date} 没有对应的会计期间，请先创建会计期间')
            return False
        
        if period.state != 'open':
            if raise_error:
                raise UserError(f'会计期间 {period.name} 已关闭，无法在期间 {check_date} 创建/修改单据')
            return False
        
        return True
    
    def action_open(self):
        """开放期间"""
        for period in self:
            if period.state != 'draft':
                raise UserError(f'期间 {period.name} 状态不是草稿，无法开放')
        self.write({'state': 'open'})
    
    def action_close(self):
        """关闭期间"""
        for period in self:
            if period.state != 'open':
                raise UserError(f'期间 {period.name} 状态不是开放，无法关闭')
        self.write({'state': 'closed'})
    
    def action_reset(self):
        """重置为草稿"""
        for period in self:
            if period.state != 'closed':
                raise UserError(f'期间 {period.name} 状态不是已关闭，无法重置')
        self.write({'state': 'draft'})
