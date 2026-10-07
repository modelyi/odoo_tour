# -*- coding: utf-8 -*-
from odoo import models, fields


class TaDepartureGuide(models.Model):
    """发团计划扩展（P1-2 / BS-08 §3.2）：司机/陪同人员。

    字段定义放在 ta_guide 而非 ta_route（ta.departure 所在模块）：
    - 多层分成引擎在 ta_guide，字段与引擎同模块、同版本号，便于批量迭代统一发布；
    - 影子库验收流程只 -u ta_guide,ta_dispatch,ta_base,ta_finance（不含 ta_route），
      通过 _inherit 挂字段保证升级路径干净。

    行程中可改（不设 readonly）：修改后由购物记录确认触发引擎重算草稿佣金单。
    """
    _inherit = 'ta.departure'

    driver_id = fields.Many2one('res.partner', string='司机', tracking=True,
                                help='多层分成：司机分成行取数来源（BS-08 §3.2），行程中可改。')
    escort_id = fields.Many2one('res.partner', string='陪同', tracking=True,
                                help='多层分成：陪同分成行取数来源（BS-08 §3.2），行程中可改。')
