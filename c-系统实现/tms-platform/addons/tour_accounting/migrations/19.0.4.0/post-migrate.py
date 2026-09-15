# -*- coding: utf-8 -*-
"""post-migrate: 将旧 tour_guide_real_pay/expense_line 数据迁移到 hr_expense。

旧表结构（保留不删）：
- tour_guide_real_pay: id, name, employee_id, guide_id, plan_id, loan_id, state,
    total_amount, move_id, payment_move_id, company_id, report_date
- tour_guide_expense_line: id, real_pay_id, expense_type, amount, invoice_no,
    deductible, account_id, supplier_id

新表：hr_expense（已有标准列）+ x_guide_id, x_plan_id, x_loan_id, x_invoice_no, x_deductible
"""
import logging
from odoo.tools.sql import table_exists

_logger = logging.getLogger(__name__)

EXPENSE_TYPE_TO_CODE = {
    'vehicle': 'EXP_VEHICLE',
    'meal': 'EXP_MEAL',
    'ticket': 'EXP_TICKET',
    'hotel': 'EXP_HOTEL',
    'visa': 'EXP_VISA',
    'guide': 'EXP_GUIDE',
    'other': 'EXP_OTHER',
}

STATE_MAP = {
    'draft': 'draft',
    'audited': 'approved',
    'settled': 'paid',
}


def migrate(cr, version):
    if not table_exists(cr, 'tour_guide_expense_line'):
        _logger.info('旧表 tour_guide_expense_line 不存在，跳过迁移')
        return

    cr.execute("""
        SELECT l.id, l.expense_type, l.amount, l.invoice_no, l.deductible,
               rp.employee_id, rp.guide_id, rp.plan_id, rp.loan_id,
               rp.state, rp.move_id, rp.company_id, rp.report_date, rp.name
        FROM tour_guide_expense_line l
        JOIN tour_guide_real_pay rp ON l.real_pay_id = rp.id
        ORDER BY l.id
    """)
    rows = cr.fetchall()
    if not rows:
        _logger.info('无旧报账数据需迁移')
        return

    cr.execute("""
        SELECT id, default_code FROM product_product
        WHERE default_code IN %s
    """, (tuple(EXPENSE_TYPE_TO_CODE.values()),))
    product_map = {code: pid for pid, code in cr.fetchall()}

    created = 0
    for row in rows:
        (line_id, expense_type, amount, invoice_no, deductible,
         employee_id, guide_id, plan_id, loan_id,
         state, move_id, company_id, report_date, rp_name) = row

        product_id = product_map.get(EXPENSE_TYPE_TO_CODE.get(expense_type, 'EXP_OTHER'))
        new_state = STATE_MAP.get(state, 'draft')

        approval_state = None
        if new_state == 'approved':
            approval_state = 'approved'
        elif new_state == 'paid':
            approval_state = 'approved'

        cr.execute("""
            INSERT INTO hr_expense (
                name, employee_id, product_id, quantity, total_amount_currency,
                total_amount, untaxed_amount_currency, untaxed_amount,
                date, state, approval_state, approval_date,
                payment_mode, company_id, currency_id,
                account_move_id,
                x_guide_id, x_plan_id, x_loan_id, x_invoice_no, x_deductible,
                create_uid, create_date, write_uid, write_date
            ) VALUES (
                %s, %s, %s, 1, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                'own_account', %s,
                (SELECT id FROM res_currency WHERE name = 'CNY' LIMIT 1),
                %s,
                %s, %s, %s, %s, %s,
                1, NOW(), 1, NOW()
            )
        """, (
            '%s-%s' % (rp_name or 'BZ', line_id),
            employee_id,
            product_id,
            amount, amount, amount, amount,
            report_date,
            new_state,
            approval_state,
            report_date and '%s 00:00:00' % report_date if report_date else None,
            company_id,
            move_id,
            guide_id, plan_id, loan_id, invoice_no, deductible or False,
        ))
        created += 1

    _logger.info('迁移 %d 条报账明细到 hr_expense', created)
