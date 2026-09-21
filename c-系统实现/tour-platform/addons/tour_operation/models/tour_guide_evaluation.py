# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourGuideEvaluation(models.Model):
    _name = 'tour.guide.evaluation'
    _description = '导游评价'
    _order = 'create_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # === 关联信息 ===
    guide_id = fields.Many2one('tour.guide', string='导游', required=True, index=True, tracking=True)
    plan_id = fields.Many2one('tour.plan', string='团队', index=True, tracking=True)
    task_id = fields.Many2one('project.task', string='派团任务')

    # === 游客信息 ===
    tourist_name = fields.Char('游客姓名')
    tourist_phone = fields.Char('游客电话')
    tourist_partner_id = fields.Many2one('res.partner', string='游客联系人',
                                         index=True, ondelete='set null',
                                         help='门户提交时回链游客 partner，用于防重复评价')

    # === 评价维度 (1-5 分) ===
    service_score = fields.Float('服务态度', digits=(2, 1), help='1-5 分')
    professional_score = fields.Float('专业水平', digits=(2, 1), help='1-5 分')
    communication_score = fields.Float('沟通能力', digits=(2, 1), help='1-5 分')
    punctuality_score = fields.Float('准时程度', digits=(2, 1), help='1-5 分')

    # === 综合评分 ===
    overall_score = fields.Float('总体评价', digits=(2, 1), compute='_compute_overall_score', store=True, tracking=True)

    # === 评价内容 ===
    comment = fields.Text('评价内容')
    tags = fields.Char('标签', help='如：热情、专业、准时，逗号分隔')

    # === 来源 ===
    source = fields.Selection([
        ('manual', '手动录入'),
        ('portal', '游客门户'),
        ('sms', '短信链接'),
        ('wechat', '微信'),
    ], string='来源', default='manual', tracking=True)

    # === 状态 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已确认'),
        ('anonymous', '匿名'),
    ], string='状态', default='draft', tracking=True)

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)

    @api.depends('service_score', 'professional_score', 'communication_score', 'punctuality_score')
    def _compute_overall_score(self):
        for record in self:
            scores = [record.service_score, record.professional_score,
                      record.communication_score, record.punctuality_score]
            valid_scores = [s for s in scores if s > 0]
            if valid_scores:
                record.overall_score = sum(valid_scores) / len(valid_scores)
            else:
                record.overall_score = 0.0

    @api.constrains('service_score', 'professional_score', 'communication_score', 'punctuality_score')
    def _check_score_range(self):
        for record in self:
            for score_field in ['service_score', 'professional_score', 'communication_score', 'punctuality_score']:
                score = record[score_field]
                if score and (score < 1 or score > 5):
                    raise ValidationError(f'{record._fields[score_field].string}必须在 1-5 分之间')

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_anonymous(self):
        self.write({
            'state': 'anonymous',
            'tourist_name': False,
            'tourist_phone': False,
        })

    def action_draft(self):
        self.write({'state': 'draft'})
