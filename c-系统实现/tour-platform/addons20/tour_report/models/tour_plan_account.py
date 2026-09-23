# -*- coding: utf-8 -*-
"""报表维度扩展：把承载团的销售渠道/订单来源带到单团核算上，供 pivot/graph 多维分析。

tour.plan.account 是「一团一行」的核算台账，plan_id 指向承载团；团上的
channel_name（渠道名称）/ from_type（订单来源）需要成为本模型可直接分组的字段，
才能在报表中心按「渠道 × 团/部门/业务模式 × 收入/成本/毛利」做多维分析。

用 store=True 的 related：单团核算行随团生成时即物化，聚合（group by）走本表列，
不产生跨表实时连接。团渠道变更时由 ORM 触发重算。
"""
from odoo import fields, models


class TourPlanAccount(models.Model):
    _inherit = 'tour.plan.account'

    report_channel_name = fields.Char(
        '销售渠道', related='plan_id.channel_name', store=True, index=True,
        help='承载团的渠道名称（直客门店/电话微信/企业客户/老客转介/同业分销/'
             '官网线上/电商-飞猪·携程·美团·抖音 等），供报表按渠道多维分析')
    report_from_type = fields.Selection(
        string='订单来源', related='plan_id.from_type', store=True, index=True,
        help='承载团的订单来源编码，渠道分析的第一层分类')
