# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourSupplier(models.Model):
    _name = 'tour.supplier'
    _description = '供应商档案'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, sup_type'

    # === 身份底座 ===
    partner_id = fields.Many2one('res.partner', string='关联联系人', index=True,
                                 ondelete='set null',
                                 help='供应商的联系人/公司；可选关联，供应商可独立存在')

    # === 核心 ===
    name = fields.Char('供应商名称', required=True, index=True, tracking=True)
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
    active = fields.Boolean('启用状态', default=True, tracking=True)

    # === 基本信息 ===
    et_cmp_code = fields.Char('易途公司编码', index=True)
    help_code = fields.Char('助记码', index=True, help='名称拼音首字母自动生成，支持手工覆盖')
    manager = fields.Char('负责人姓名')
    manager_mobile = fields.Char('负责人手机')
    boss_birthday = fields.Date('负责人（老板）生日')

    # === 合同信息 ===
    contract_no = fields.Char('合同编号')
    contract_date = fields.Date('签约日期')
    contract_begin_date = fields.Date('合同生效日')
    contract_end_date = fields.Date('合同到期日')
    is_contract = fields.Boolean('是否已签约')

    # === 等级与信用 ===
    level_id = fields.Selection([
        ('a', 'A 级'),
        ('b', 'B 级'),
        ('c', 'C 级'),
        ('d', 'D 级'),
    ], string='供应商等级', index=True,
       help='供应商等级评级（A/B/C/D），固定枚举')
    level_name = fields.Char('等级名称')
    credit_lmt = fields.Float('信用额度', digits=(16, 2))
    credit_lmt_type = fields.Char('信用额度类型')
    credit_lmt_sk = fields.Float('收款信用额度', digits=(16, 2))

    # === 开票信息 ===
    tax_payer_no = fields.Char('纳税人识别号')
    invoice_title = fields.Char('发票抬头')
    is_invoice = fields.Boolean('是否开票')
    invoice_rule = fields.Char('开票规则')

    # === 合作协议 ===
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
    free_payment_lmt = fields.Float('免付限额', digits=(16, 2))
    pay_way = fields.Char('结算方式')

    # === 备注 ===
    remark = fields.Text('备注')
    remark2 = fields.Text('备注2')
    image_1920 = fields.Binary('图片')
    image_128 = fields.Binary('图片 128', related='image_1920')

    # === 授权 ===
    grant_num = fields.Integer('授权数')
    author_date = fields.Date('授权日期')

    # === 审核 ===
    audit_chk = fields.Boolean('审核状态')
    audit_user = fields.Char('审核人')
    audit_brief = fields.Text('审核说明')
    audit_date = fields.Datetime('审核时间')

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id and not self.name:
            self.name = self.partner_id.name

    def action_audit_approve(self):
        for rec in self:
            rec.write({
                'audit_chk': True,
                'audit_user': self.env.user.name,
                'audit_date': fields.Datetime.now(),
            })
