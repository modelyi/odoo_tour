# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


# 报表类型配置：名称 / 目标模型 / 日期字段 / 默认分组 / 分组选项 / 搜索视图
REPORT_TYPES = {
    'plan_profit': {
        'name': '单团利润报表',
        'model': 'tour.plan.account',
        'date_field': 'plan_id.begin_date',
        'default_group_by': 'plan_id',
        'group_options': [
            ('plan_id', '按团'),
            ('department_id', '按部门'),
            ('biz_mode', '按业务模式'),
            ('report_channel_name', '按销售渠道'),
            ('report_from_type', '按订单来源'),
        ],
        'search_view': 'tour_report.view_tour_plan_account_report_search',
    },
    'guide_performance': {
        'name': '导游业绩报表',
        'model': 'tour.commission',
        'date_field': 'plan_id.begin_date',
        'default_group_by': 'guide_id',
        'group_options': [
            ('guide_id', '按导游'),
            ('plan_id', '按团'),
            ('department_id', '按部门'),
        ],
        'search_view': 'tour_report.view_tour_commission_report_search',
    },
    'shop_commission': {
        'name': '购物返佣报表',
        'model': 'tour.shop.record',
        'date_field': 'shop_date',
        'default_group_by': 'shop_id',
        'group_options': [
            ('shop_id', '按购物店'),
            ('plan_id', '按团'),
            ('guide_id', '按导游'),
        ],
        'search_view': 'tour_report.view_tour_shop_record_report_search',
    },
    'daily_income_expense': {
        'name': '每日收支报表',
        'model': 'tour.payment.claim',
        'date_field': 'pay_date',
        'default_group_by': 'pay_date',
        'group_options': [
            ('pay_date', '按日'),
            ('account_id', '按收款账户'),
            ('pay_way_id', '按收付场景'),
            ('pay_channel_id', '按支付渠道'),
        ],
        'search_view': 'tour_report.view_tour_payment_claim_report_search',
    },
}


class TourReportWizard(models.TransientModel):
    _name = 'tour.report.wizard'
    _description = '报表中心向导'

    report_type = fields.Selection([
        ('plan_profit', '单团利润'),
        ('guide_performance', '导游业绩'),
        ('shop_commission', '购物返佣'),
        ('daily_income_expense', '每日收支'),
    ], string='报表类型', required=True, default='plan_profit')

    date_from = fields.Date('开始日期', help='留空表示不限制开始日期')
    date_to = fields.Date('结束日期', help='留空表示不限制结束日期')

    group_by = fields.Selection(
        selection='_selection_group_by', string='分组方式',
        help='报表初始分组维度，进入报表后可在透视/图形视图自由调整')

    def _selection_group_by(self):
        config = REPORT_TYPES.get(self.report_type) or REPORT_TYPES['plan_profit']
        return config['group_options']

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'group_by' in fields_list:
            report_type = (res.get('report_type')
                           or self.env.context.get('default_report_type')
                           or 'plan_profit')
            config = REPORT_TYPES.get(report_type) or REPORT_TYPES['plan_profit']
            res['group_by'] = config['default_group_by']
        return res

    @api.onchange('report_type')
    def _onchange_report_type(self):
        config = REPORT_TYPES.get(self.report_type) or REPORT_TYPES['plan_profit']
        self.group_by = config['default_group_by']

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError('结束日期不能早于开始日期')

    def action_generate_report(self):
        """生成报表：按报表类型/日期范围/分组方式返回原生 pivot/graph 视图 action"""
        self.ensure_one()
        config = REPORT_TYPES.get(self.report_type)
        if not config:
            return {'type': 'ir.actions.act_window_close'}

        domain = []
        date_field = config['date_field']
        if self.date_from:
            domain.append((date_field, '>=', self.date_from))
        if self.date_to:
            domain.append((date_field, '<=', self.date_to))

        group_by = self.group_by or config['default_group_by']
        action = {
            'name': config['name'],
            'type': 'ir.actions.act_window',
            'res_model': config['model'],
            'view_mode': 'pivot,graph,list',
            'domain': domain,
            'context': {'group_by': group_by},
            'target': 'current',
        }
        search_view = self.env.ref(config.get('search_view'), raise_if_not_found=False)
        if search_view:
            action['search_view_id'] = search_view.id
        return action
