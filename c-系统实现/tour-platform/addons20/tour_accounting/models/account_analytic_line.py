# -*- coding: utf-8 -*-
from odoo import models
from odoo.tools import SQL


class AccountAnalyticLine(models.Model):
    """修补 account.analytic.line 的 _field_to_sql，解决 Odoo 19 分析行
    auto_account_id 非存储计算字段无法转换为 SQL 的问题。

    根因：
      account.analytic.account.line_ids 的自动反向字段是
      account.analytic.line.auto_account_id（非存储计算字段）。
      当 ORM 的 modified() 触发器通过 related 字段链
      （tour.plan.account.analytic_line_ids → analytic_account_id.line_ids）
      搜索 tour.plan.account 时，需要将 auto_account_id 转换为 SQL，
      但该字段无数据库列，导致 ValueError: Cannot convert ... to SQL because it is not stored。

    修复：
      在 _field_to_sql 中拦截 auto_account_id，将其重定向到实际存储列。
      当前仅有一个分析计划（Project），其列名为 account_id，
      auto_account_id 在计算时等价于 account_id。
    """
    _inherit = 'account.analytic.line'

    def _field_to_sql(self, alias: str, field_expr: str, query=None) -> SQL:
        if field_expr == 'auto_account_id':
            # 重定向到实际存储的分析计划列（当前唯一计划 Project → account_id）
            plan = self.env['account.analytic.plan'].search([], limit=1)
            if plan:
                field_expr = plan._column_name()
            else:
                field_expr = 'account_id'  # 安全回退
        return super()._field_to_sql(alias, field_expr, query)
