# -*- coding: utf-8 -*-
import datetime

from odoo import models, fields
from odoo.exceptions import ValidationError

from odoo.addons.tour_base.models.constants import BIZ_MODE, FROM_TYPE


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # === 旅行社销售字段（薄扩展，语义化字段名，不用 x_ 前缀） ===
    line_id = fields.Many2one('tour.line', string='意向线路', index=True, tracking=True,
                              help='意向线路（报价/建团依据）')
    biz_mode = fields.Selection(BIZ_MODE, string='业务模式', tracking=True,
                                help='业务模式预选（决定建团类型）')
    begin_date = fields.Date('预期出发日期', tracking=True)
    from_type = fields.Selection(FROM_TYPE, string='订单来源', default='1', tracking=True)
    plan_id = fields.Many2one('tour.plan', string='关联团队', readonly=True,
                              copy=False, index=True,
                              help='赢单转团后回写的建团结果（溯源）')

    def action_convert_to_plan(self):
        """「转团」按钮：把线索转成 tour.plan（draft）。幂等：已转则不重复建团。"""
        self.ensure_one()
        if self.plan_id:
            return self.action_open_plan()
        if not self.line_id:
            raise ValidationError('请先填写「意向线路」，再转团。')
        if not self.biz_mode:
            raise ValidationError('请先填写「业务模式」，再转团。')
        if not self.begin_date:
            raise ValidationError('请先填写「预期出发日期」，再转团。')
        plan = self.env['tour.plan'].create(self._prepare_plan_vals())
        self.plan_id = plan.id
        self.message_post(
            body='已转团生成团队订单：%s（%s）' % (plan.plan_code, plan.plan_name))
        return self.action_open_plan()

    def _prepare_plan_vals(self):
        """won → 建团字段映射（只落 draft，不触发 analytic/台账，保持 O2C 主线不变）。"""
        self.ensure_one()
        line = self.line_id
        begin = self.begin_date
        # 返程日期：按线路天数推算（day_num-1 晚），缺省 = 出发日期
        end = begin
        if line.day_num and line.day_num > 1:
            end = begin + datetime.timedelta(days=line.day_num - 1)
        return {
            'plan_code': self.env['ir.sequence'].next_by_code('tour.plan.crm')
                         or ('CRM-%s' % datetime.datetime.now().strftime('%Y%m%d%H%M%S')),
            'plan_name': '%s-%s' % (line.name, begin),
            'line_id': line.id,
            'biz_mode': self.biz_mode,
            'from_type': self.from_type or '1',
            'supplier_id': self.partner_id.id,
            'sales_name': self.user_id.name if self.user_id else False,
            'begin_date': begin,
            'end_date': end,
            'lead_id': self.id,
            'state': 'draft',
        }

    def action_open_plan(self):
        """Smart button：打开该线索转出的团队订单。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '团队订单',
            'res_model': 'tour.plan',
            'res_id': self.plan_id.id,
            'view_mode': 'form',
        }
