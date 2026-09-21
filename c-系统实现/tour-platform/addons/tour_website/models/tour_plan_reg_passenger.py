# -*- coding: utf-8 -*-
"""报名客人证件子表（GAP-2）。

逐人：姓名 / 证件类型 / 证件号（🔴 加密）/ 年龄档 / 单价。
id_number 走 tour.encrypted.field.mixin（AES-256-GCM 落盘加密 + 掩码 + 等值检索散列）。
"""
from odoo import api, fields, models


class TourPlanRegPassenger(models.Model):
    _name = 'tour.plan.reg.passenger'
    _description = '报名客人证件'
    _inherit = ['mail.thread', 'tour.encrypted.field.mixin']
    _order = 'sequence, id'
    _rec_name = 'name'

    # 敏感字段：证件号 🔴 加密存储
    _encrypted_fields = {'id_number': True}

    reg_id = fields.Many2one('tour.plan.reg', string='报名单', required=True,
                             index=True, ondelete='cascade')

    name = fields.Char('客人姓名', required=True)
    passenger_type = fields.Selection([
        ('adult', '成人'),
        ('child', '儿童'),
        ('old_man', '老人'),
        ('student', '学生'),
        ('baby', '婴儿'),
    ], string='年龄档', required=True, default='adult')

    id_type = fields.Selection([
        ('id_card', '身份证'),
        ('passport', '护照'),
        ('other', '其他'),
    ], string='证件类型', required=True, default='id_card')

    id_number = fields.Char('证件号', required=True,
                            help='🔴 敏感字段：已 AES-256-GCM 加密存储，界面掩码')
    id_number_hash = fields.Char('证件号检索散列', index=True, copy=False,
                                 help='HMAC-SHA256 等值检索辅助列（不存明文）')
    id_number_masked = fields.Char('证件号掩码', compute='_compute_masked_fields',
                                   help='界面/报表/日志/导出默认显示 ****后4位')

    price = fields.Float('单价', digits='Product Price',
                         help='该客人计价单价（下单时快照）')
    sequence = fields.Integer('排序', default=10)

    @api.depends('id_number')
    def _compute_masked_fields(self):
        for rec in self:
            rec.id_number_masked = rec._encrypt_mask('id_number')
