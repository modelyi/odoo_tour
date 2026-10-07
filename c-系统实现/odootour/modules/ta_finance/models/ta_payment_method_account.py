# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    """批4-A 防御（库级缺陷）：bank/cash 日记账的付款方式行缺过渡科目
    payment_account_id 时自动回填 default_account_id。

    根因：Odoo 20 核心 _compute_inbound/_outbound_payment_method_line_ids 生成
    默认付款方式行时不带 payment_account_id；account.payment.outstanding_account_id
    由该行计算 → 为空 → _generate_journal_entry 的 need_move 过滤把付款排除 →
    登记付款生成"已付款"但不落凭证，供应商账单余额永远不清偿。
    """
    _inherit = 'account.journal'

    def _ta_fill_payment_method_accounts(self):
        """bank/cash 日记账：付款方式行缺过渡科目 → 回填 default_account_id。"""
        for journal in self:
            if journal.type not in ('bank', 'cash') or not journal.default_account_id:
                continue
            lines = (journal.inbound_payment_method_line_ids
                     + journal.outbound_payment_method_line_ids).filtered(
                lambda l: not l.payment_account_id)
            if lines:
                lines.payment_account_id = journal.default_account_id

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        journals._ta_fill_payment_method_accounts()
        return journals

    def write(self, vals):
        res = super().write(vals)
        self._ta_fill_payment_method_accounts()
        return res


class AccountPayment(models.Model):
    """批4-A 防御（第二道网，兜住存量行）：创建付款时若所选方式行缺过渡科目，
    从 journal.default_account_id 回填该行；journal 也无默认科目则 raise，
    明确指引配置位置（会计 → 配置 → 日记账 → 默认借贷科目 / 收付款方式行）。
    """
    _inherit = 'account.payment'

    def _ta_fill_payment_method_account_from_journal(self):
        """方式行缺过渡科目 → 回填 journal.default_account_id，并强制重算
        outstanding_account_id（核心 compute 只 depends 于 payment_method_line_id，
        改行字段不触发重算，需 invalidate）。journal 无默认科目时 raise。"""
        self.ensure_one()
        line = self.payment_method_line_id
        if not line or line.payment_account_id:
            return
        journal = self.journal_id or line.journal_id
        if not journal or not journal.default_account_id:
            raise UserError(_(
                '付款方式「%(line)s」缺少过渡科目，且日记账「%(journal)s」未设置默认科目，'
                '无法生成付款凭证。\n请到 会计 → 配置 → 日记账 打开该日记账，'
                '设置「默认借贷科目」，或在「收/付款方式」中给该方式行补上过渡科目后重试。',
                line=line.name, journal=journal.display_name or '（未关联日记账）'))
        line.payment_account_id = journal.default_account_id
        self.invalidate_recordset(['outstanding_account_id'])

    @api.model_create_multi
    def create(self, vals_list):
        Line = self.env['account.payment.method.line']
        Journal = self.env['account.journal']
        for vals in vals_list:
            line_id = vals.get('payment_method_line_id')
            if not line_id:
                continue  # 方式行由核心 compute 兜底指定 → 建后兜底处理
            # 注：Odoo 20 模型类不是 type 实例，isinstance(x, Model) 会 TypeError，
            # 一律按 int 判定是 id 还是记录。
            line = Line.browse(line_id) if isinstance(line_id, int) else line_id
            if line.payment_account_id:
                continue
            journal_id = vals.get('journal_id')
            if journal_id:
                journal = Journal.browse(journal_id) if isinstance(journal_id, int) \
                    else journal_id
            else:
                journal = line.journal_id
            if not journal or not journal.default_account_id:
                raise UserError(_(
                    '付款方式「%(line)s」缺少过渡科目，且日记账「%(journal)s」未设置默认科目，'
                    '无法生成付款凭证。\n请到 会计 → 配置 → 日记账 打开该日记账，'
                    '设置「默认借贷科目」，或在「收/付款方式」中给该方式行补上过渡科目后重试。',
                    line=line.name, journal=journal.display_name or '（未关联日记账）'))
            # 必须在 super().create() 前回填行：outstanding_account_id 是 stored
            # compute，create 时即读取方式行的 payment_account_id。
            line.payment_account_id = journal.default_account_id
        payments = super().create(vals_list)
        # 兜底：vals 未显式给方式行、由核心 compute 指定时，同样回填并重算
        for pay in payments:
            if pay.payment_method_line_id and not pay.payment_method_line_id.payment_account_id:
                pay._ta_fill_payment_method_account_from_journal()
        return payments
