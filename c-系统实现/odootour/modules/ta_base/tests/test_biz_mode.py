# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBizMode(TransactionCase):

    def test_loaded_15_codes(self):
        modes = self.env['ta.biz.mode'].with_context(active_test=False).search([])
        self.assertEqual(len(modes), 15, '业务模式码应装载 15 项（BS-02 §5）')
        self.assertEqual(len(modes.filtered('is_alias')), 3)
        for alias in modes.filtered('is_alias'):
            self.assertTrue(alias.alias_of)
            self.assertFalse(alias.alias_of.is_alias)

    def test_unique_code(self):
        with self.assertRaises(Exception):
            self.env['ta.biz.mode'].create({'code': '1', 'name': '重复'})

    def test_alias_requires_target(self):
        with self.assertRaises(Exception):
            self.env['ta.biz.mode'].create({'code': '99', 'name': 'x', 'is_alias': True})
