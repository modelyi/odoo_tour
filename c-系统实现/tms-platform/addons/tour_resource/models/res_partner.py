# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourPartner(models.Model):
    # 扩展 res.partner：显式 _name 等于被扩展模型（否则类名会被自动转成 tour.partner）
    _name = 'res.partner'
    _inherit = ['res.partner', 'tour.encrypted.field.mixin']

    # 敏感字段（AES-256-GCM 落盘加密 + 掩码展示 + 等值检索散列）
    _encrypted_fields = {'manager_id_code': True, 'account_no': True}

    # === 供应商类型（易途 SupTypeID 对应，10 类 + 预留签证） ===
    sup_type = fields.Selection([
        ('customer', '客户'),
        ('ditch', '地接社'),
        ('hotel', '酒店'),
        ('meal', '餐厅'),
        ('vehicle_comp', '车队'),
        ('ticket', '票务'),
        ('scenic', '景区'),
        ('shop', '购物店'),
        ('insurance', '保险'),
        ('self_fee', '自费'),
        ('visa', '签证公司（预留）'),
    ], string='供应商类型', index=True, tracking=True,
       help='供应商类型（10 类 + 预留），由易途 SupTypeID 映射而来')

    # === 基本信息 ===
    et_cmp_code = fields.Char('易途公司编码', index=True)
    help_code = fields.Char('助记码', index=True, help='名称拼音首字母自动生成，支持手工覆盖')
    manager = fields.Char('负责人姓名')
    manager_mobile = fields.Char('负责人手机', help='🟡 敏感字段：界面掩码')
    manager_id_code = fields.Char('负责人身份证', help='🔴 敏感字段：已 AES-256-GCM 加密存储，界面掩码')
    manager_id_code_hash = fields.Char('负责人身份证检索散列', index=True, copy=False,
                                       help='HMAC-SHA256 等值检索辅助列（不存明文）')
    manager_id_code_masked = fields.Char('负责人身份证掩码', compute='_compute_masked_fields',
                                         help='界面/报表/日志/导出默认显示 ****后4位')
    boss_birthday = fields.Date('负责人（老板）生日')

    # === 合同信息 ===
    contract_no = fields.Char('合同编号')
    contract_date = fields.Date('签约日期')
    contract_begin_date = fields.Date('合同生效日')
    contract_end_date = fields.Date('合同到期日')

    # === 等级与信用 ===
    level_id = fields.Many2one('tour.base.item', string='供应商等级')
    level_name = fields.Char('等级名称')
    credit_lmt = fields.Float('信用额度', digits=(16, 2))
    credit_lmt_type = fields.Char('信用额度类型')
    credit_lmt_sk = fields.Float('收款信用额度', digits=(16, 2))

    # === 开票信息 ===
    tax_payer_no = fields.Char('纳税人识别号', help='🟡 敏感字段：界面掩码')
    invoice_title = fields.Char('发票抬头')
    is_invoice = fields.Boolean('是否开票')
    invoice_rule = fields.Char('开票规则')

    # === 合作协议 ===
    is_contract = fields.Boolean('是否已签约')
    cooperation_agreement = fields.Text('合作协议')
    agr_price = fields.Float('协议价', digits=(16, 2))
    any_price = fields.Float('参考价', digits=(16, 2))
    charge_period = fields.Char('账期')

    # === 服务费 ===
    service_type = fields.Char('服务类型')
    service_price = fields.Float('服务价格', digits=(16, 2))
    service_calc_mode = fields.Char('服务费计算方式')
    service_fee_round_way = fields.Char('服务费取整方式')

    # === 区域信息 ===
    province = fields.Char('省')
    city_name = fields.Char('市')
    zone = fields.Char('区县')
    county_town = fields.Char('乡镇')
    latitude = fields.Float('纬度', digits=(16, 6))
    longtitue = fields.Float('经度', digits=(16, 6))
    location = fields.Char('位置描述')
    addr2 = fields.Char('地址2')
    manage_area_set = fields.Char('授权管理区域')

    # === 运营属性 ===
    res_isolation = fields.Boolean('资源隔离')
    isno_repeat = fields.Boolean('是否防重')
    sort_code = fields.Char('排序码')
    verify_user = fields.Char('认证人')
    purchaser = fields.Char('采购员')
    grade = fields.Char('供应商评级')

    # === 结算信息 ===
    bank = fields.Char('开户行')
    account = fields.Char('账号名称')
    account_no = fields.Char('银行账号', help='🔴 敏感字段：已 AES-256-GCM 加密存储，界面掩码')
    account_no_hash = fields.Char('银行账号检索散列', index=True, copy=False,
                                  help='HMAC-SHA256 等值检索辅助列（不存明文）')
    account_no_masked = fields.Char('银行账号掩码', compute='_compute_masked_fields',
                                    help='界面/报表/日志/导出默认显示 ****后4位')
    free_payment_lmt = fields.Float('免付限额', digits=(16, 2))
    pay_way = fields.Char('结算方式')

    # === 备注 ===
    remark = fields.Text('备注')
    remark2 = fields.Text('备注2')

    # === 授权 ===
    grant_num = fields.Integer('授权数')
    author_date = fields.Date('授权日期')

    # === 审核 ===
    audit_chk = fields.Boolean('审核状态')
    audit_user = fields.Char('审核人')
    audit_brief = fields.Text('审核说明')
    audit_date = fields.Datetime('审核时间')

    @api.depends('manager_id_code', 'account_no')
    def _compute_masked_fields(self):
        for rec in self:
            rec.manager_id_code_masked = rec._encrypt_mask('manager_id_code')
            rec.account_no_masked = rec._encrypt_mask('account_no')
