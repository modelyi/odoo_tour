# -*- coding: utf-8 -*-
"""TMS 系统级配置（res.config.settings）。

遵循 Odoo 标准模式：get_values / set_values + ir.config_parameter，
不硬编码，不直接 hack 数据库。配置项为跨模块共享的系统级参数。
"""
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # 配置参数键（ir.config_parameter key）
    PARAM_DEFAULT_CURRENCY = 'tms.default_currency_id'
    PARAM_DEFAULT_PAYMENT_TERM = 'tms.default_payment_term'
    PARAM_GUIDE_COMMISSION_RATE = 'tms.guide_default_commission_rate'
    PARAM_SENSITIVE_DATA_GROUP = 'tms.sensitive_data_group_xmlid'

    # === 系统级参数（落点：ir.config_parameter，跨公司共享） ===
    tms_default_currency_id = fields.Many2one(
        'res.currency', string='默认币种',
        config_parameter=PARAM_DEFAULT_CURRENCY,
        help='系统级默认币种，供业务模块在未显式指定币种时兜底使用。')

    tms_default_payment_term = fields.Char(
        string='默认付款条件',
        config_parameter=PARAM_DEFAULT_PAYMENT_TERM,
        help='默认付款条件的 XML ID（如 account.account_payment_term_net）。'
             '由财务模块在生成单据时解析，避免 tour_base 反向依赖 account。')

    tms_guide_default_commission_rate = fields.Float(
        string='导游默认分成比例(%)',
        config_parameter=PARAM_GUIDE_COMMISSION_RATE,
        digits=(5, 2),
        help='导游分成/佣金默认比例（百分比），业务模块在未指定时兜底。')

    # 敏感数据查看组：设置界面用 Many2one 选组，落点存组 XML ID（config_parameter），
    # 与 tour.encrypted.field.mixin 的 _full_access_group_xmlid 口径一致。
    tms_sensitive_data_group_id = fields.Many2one(
        'res.groups', string='敏感数据查看组',
        help='可查看敏感字段完整值（身份证/卡号等）的权限组。'
             '默认 tour_base.group_tour_sensitive_data。')

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        group_xmlid = params.get_param(self.PARAM_SENSITIVE_DATA_GROUP) or ''
        res.update(tms_sensitive_data_group_id=self._xmlid_to_group(group_xmlid))
        return res

    def set_values(self):
        super().set_values()
        group_xmlid = self._group_to_xmlid(self.tms_sensitive_data_group_id)
        self.env['ir.config_parameter'].sudo().set_param(
            self.PARAM_SENSITIVE_DATA_GROUP, group_xmlid or False)

    # === 工具：res.groups <-> XML ID 互转 ===
    @api.model
    def _xmlid_to_group(self, xmlid):
        """XML ID -> res.groups id；无效返回 False（不抛异常）。"""
        if not xmlid:
            return False
        try:
            return self.env.ref(xmlid).id
        except (ValueError, KeyError):
            return False

    def _group_to_xmlid(self, group):
        """res.groups -> 'module.xmlid'；无对应外部 ID 返回 False。"""
        if not group:
            return False
        data = self.env['ir.model.data'].sudo().search(
            [('model', '=', 'res.groups'), ('res_id', '=', group.id)], limit=1)
        if data:
            return '%s.%s' % (data.module, data.name)
        return False
