# -*- coding: utf-8 -*-
"""Rename amount → total_amount before ORM loads the new field definition."""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'tour_shop_record' AND column_name = 'amount'
    """)
    if cr.fetchone():
        cr.execute("""
            ALTER TABLE tour_shop_record
            RENAME COLUMN amount TO total_amount
        """)
