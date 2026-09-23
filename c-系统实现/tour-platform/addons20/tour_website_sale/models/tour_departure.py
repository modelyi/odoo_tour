# -*- coding: utf-8 -*-
"""tour.departure 电商辅助：班期五档价 JSON（前端预估合计用，最终价服务端重算）。"""
import json

from odoo import models


class TourDeparture(models.Model):
    _inherit = 'tour.departure'

    def _price_json(self):
        """五档价 JSON 字符串（前端只读展示，服务端仍重算，不信任客户端）。"""
        self.ensure_one()
        return json.dumps(self.get_online_prices())
