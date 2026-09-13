#!/usr/bin/env python3
# 卸载 tour_product 模块（用于重新安装以加载 demo 数据）
mod = env['ir.module.module'].search([('name', '=', 'tour_product')])
print('STATE_BEFORE:', mod.state)
mod.button_immediate_uninstall()
env.cr.commit()
print('UNINSTALL_DONE')
