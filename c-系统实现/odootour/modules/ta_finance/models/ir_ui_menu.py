# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def ta_rename_finance_menu(self):
        """core 会计应用根菜单中文被 om 本地化 po 译作"发票"，
        口径混乱（其下是完整财务功能）→ 各语言统一改称"财务/Finance"。

        由 data/menu_renames.xml 的 <function> 在每次 -u 本模块时调用，
        晚于 core account 的 po 重载，覆盖稳定。
        """
        menu = self.env.ref('account.menu_finance', raise_if_not_found=False)
        if not menu:
            return
        # 按语言写 jsonb 对应键（Odoo 20 翻译内嵌字段）
        menu.with_context(lang='en_US').name = 'Finance'
        menu.with_context(lang='zh_CN').name = '财务'
