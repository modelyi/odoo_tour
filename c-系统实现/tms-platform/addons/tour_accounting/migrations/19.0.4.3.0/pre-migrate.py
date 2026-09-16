# -*- coding: utf-8 -*-
"""pre-migrate: 确保 hr_expense 表有旅行社扩展列（在 ORM 加载前加列）。"""
from odoo.tools.sql import column_exists, create_column


def migrate(cr, version):
    if not column_exists(cr, 'hr_expense', 'x_guide_id'):
        create_column(cr, 'hr_expense', 'x_guide_id', 'int4')
    if not column_exists(cr, 'hr_expense', 'x_plan_id'):
        create_column(cr, 'hr_expense', 'x_plan_id', 'int4')
    if not column_exists(cr, 'hr_expense', 'x_loan_id'):
        create_column(cr, 'hr_expense', 'x_loan_id', 'int4')
    if not column_exists(cr, 'hr_expense', 'x_invoice_no'):
        create_column(cr, 'hr_expense', 'x_invoice_no', 'varchar')
    if not column_exists(cr, 'hr_expense', 'x_deductible'):
        create_column(cr, 'hr_expense', 'x_deductible', 'bool')
    if not column_exists(cr, 'product_product', 'x_expense_type'):
        create_column(cr, 'product_product', 'x_expense_type', 'varchar')
