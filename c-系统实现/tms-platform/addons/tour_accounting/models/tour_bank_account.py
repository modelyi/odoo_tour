# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourBankAccount(models.Model):
    _name = 'tour.bank.account'
    _description = '银行账户'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.encrypted.field.mixin']
    _order = 'company_id, name'
    _rec_name = 'name'

    # 敏感字段（AES-256-GCM 落盘加密 + 掩码展示 + 等值检索散列）
    _encrypted_fields = {'acc_number': True}

    # === 基本 ===
    name = fields.Char('账户名称', required=True, index=True)
    bank_id = fields.Many2one('res.bank', string='开户行', index=True)
    acc_number = fields.Char('银行卡号',
                             help='🔴 敏感字段：已 AES-256-GCM 加密存储（AES-256-GCM + 密钥分离），界面掩码')
    acc_number_hash = fields.Char('卡号检索散列', index=True, copy=False,
                                  help='HMAC-SHA256 等值检索辅助列（不存明文），用于精确匹配搜索')
    acc_number_masked = fields.Char('卡号掩码', compute='_compute_acc_number_masked',
                                    help='界面/报表/日志/导出默认显示 ****后4位')
    currency_id = fields.Many2one('res.currency', string='币种',
                                  default=lambda self: self.env.company.currency_id)
    account_type = fields.Selection([
        ('bank', '银行'),
        ('cash', '现金'),
        ('third_party', '第三方'),
    ], string='账户类型', default='bank')
    balance = fields.Float('账户余额', digits=(16, 2),
                           help='由银行对账单派生，不手工维护')
    taxpayer_no = fields.Char('纳税人识别号')
    trans_fee_rate = fields.Float('手续费率(%)', digits=(5, 2))
    active = fields.Boolean('启用', default=True)
    power_area = fields.Char('权限区域', help='权限区域（最小化访问）')
    remark = fields.Text('备注')

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    @api.depends('acc_number')
    def _compute_acc_number_masked(self):
        for rec in self:
            rec.acc_number_masked = rec._encrypt_mask('acc_number')
