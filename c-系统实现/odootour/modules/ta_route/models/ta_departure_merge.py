# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import UserError


class TaDepartureMerge(models.TransientModel):
    _name = 'ta.departure.merge'
    _description = '并团向导'

    target_id = fields.Many2one(
        'ta.departure', string='并入班期（目标）', required=True,
        domain="[('state', 'in', ('open', 'confirmed'))]")
    source_ids = fields.Many2many(
        'ta.departure', string='被并班期（来源）', required=True,
        domain="[('state', 'in', ('open', 'confirmed')), ('seats_used', '>=', 0)]")
    note = fields.Char()

    def action_validate(self):
        self.ensure_one()
        sources = self.source_ids
        if not sources or self.target_id in sources:
            raise UserError("来源班期不能为空，且不能包含目标班期。")
        moved_seats = sum(sources.mapped('seats_used'))
        if self.target_id.seats_used + moved_seats > self.target_id.seats_total:
            raise UserError("目标班期余位不足，无法承接来源班期的已报名人数。")
        for src in sources:
            if src.route_id != self.target_id.route_id:
                # 跨线路并团（关键字并团/内部流转）允许，但留痕提醒
                self.target_id.message_post(
                    body=f"并团注意：来源班期 {src.display_name} 线路不同。")
            if src.seats_used:
                self.target_id.change_seats(src.seats_used)
            # M2 ta_order 接入后在此迁移报名单指向；当前仅转移占位
            src.write({'state': 'merged', 'merge_target_id': self.target_id.id,
                       'seats_used': 0})
        return {'type': 'ir.actions.act_window_close'}
