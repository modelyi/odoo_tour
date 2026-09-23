# -*- coding: utf-8 -*-
from odoo import api, models


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _tour_write_brand_name(self, name):
        """给首个站点改品牌名。

        19 的种子数据里 `website.default_website` 是 website 模块建的记录；
        20 把它移到了 `base.default_website` 且只在已有站点时惰性登记
        （`_ensure_default_website_consistency`），所以按 xid 取记录在 20 必炸。
        改成"取第一个站点"，两版同语义。
        """
        site = self.sudo().search([], limit=1, order='sequence, id')
        if site and site.name != name:
            site.name = name
        return True
