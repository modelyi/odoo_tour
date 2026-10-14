# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import AccessError, UserError


class TaCompanyMixin(models.AbstractModel):
    """SaaS 预留原则①：全部业务模型挂 company_id 并配 record rule。"""
    _name = 'ta.mixin'
    _description = 'Travel Agency Base Mixin'

    company_id = fields.Many2one(
        'res.company', string='公司', required=True, index=True,
        default=lambda self: self.env.company)

    def _ta_check_company(self):
        if any(rec.company_id != self.env.company for rec in self):
            raise AccessError("不允许跨公司操作系统数据。")

    def _ta_get_account(self, code, name, account_type):
        """批6 P0-6：按 code+公司解析会计科目（Odoo 20 的 account.code 为
        company 相关计算字段，须在 with_company 上下文下搜索；缺失时 sudo 幂等
        补建）。同款逻辑见 ta_guide_commission._get_commission_account。"""
        company = self.company_id or self.env.company
        Account = self.env['account.account'].with_company(company)
        hit = Account.search(
            [('company_ids', 'in', company.ids), ('code', '=', code)], limit=1)
        if hit:
            return hit
        try:
            return Account.sudo().create({
                'code': code, 'name': name, 'account_type': account_type,
                'company_ids': [(6, 0, company.ids)],
            })
        except (AccessError, ValueError) as exc:
            raise UserError(
                f"缺少会计科目 {code} {name}（公司：{company.name}），"
                f"自动创建失败：{exc}。请会计补建该科目后重试。") from exc

