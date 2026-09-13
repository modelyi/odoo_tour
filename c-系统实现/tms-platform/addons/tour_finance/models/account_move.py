# -*- coding: utf-8 -*-
from odoo import models, fields

# 合规标注：每条凭证必须标注适用的准则/法规依据 [BS-10 §9.1 / D7]
COMPLIANCE_REF_SELECTION = [
    ('cas14', '[CAS 14] 收入'),
    ('cas14_agent', '[CAS 14-代理人] 净额法'),
    ('cas14_principal', '[CAS 14-主要责任人] 总额法'),
    ('cas14_advance', '[CAS 14-预收]'),
    ('cas22', '[CAS 22] 金融工具确认和计量'),
    ('cas22_settle', '[CAS 22-核销]'),
    ('cas1', '[CAS 1] 存货/成本归集'),
    ('cas8', '[CAS 8] 资产减值'),
    ('cas9', '[CAS 9] 职工薪酬'),
    ('cas30', '[CAS 30] 财务报表列报'),
    ('cas37', '[CAS 37] 金融工具列报'),
    ('vat_diff', '[财税2016-36号] 差额征税'),
    ('vat_reg', '[增值税暂行条例]'),
    ('iit', '[个税法] 代扣代缴'),
    ('iit_labor', '[个税法-劳务报酬]'),
    ('stamp', '[印花税法]'),
    ('ic_sep', '[内控-职务分离]'),
    ('ic_auth', '[内控-授权审批]'),
    ('ic_refund', '[内控-退款审批]'),
    ('ic_audit', '[内控-审计轨迹]'),
    ('pay_settle', '[支付结算办法]'),
    ('cash_reg', '[现金管理暂行条例]'),
]


class AccountMove(models.Model):
    _inherit = 'account.move'

    compliance_ref = fields.Selection(
        COMPLIANCE_REF_SELECTION, string='准则依据',
        help='每条凭证必须标注适用的准则/法规依据 [BS-10 §9.1]')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    compliance_ref = fields.Selection(
        COMPLIANCE_REF_SELECTION, string='准则依据(行级)',
        help='凭证跨多准则时按行覆盖主凭证标签；默认继承 account.move.compliance_ref')
