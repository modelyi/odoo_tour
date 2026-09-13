# -*- coding: utf-8 -*-
"""tour_base 迁移验收：菜单/组/加密/config_parameter"""
from odoo.addons.tour_base.models import field_crypto

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('PASS' if cond else 'FAIL'), '-', name, ('| ' + str(detail) if detail else ''))

# 1. 模块状态
mod = env['ir.module.module'].search([('name', '=', 'tour_base')], limit=1)
check('tour_base installed', mod.state == 'installed', mod.state)

# 2. 根菜单归属 tour_base
imd = env['ir.model.data'].search([('name', '=', 'menu_tms_root')], limit=1)
check('menu_tms_root module=tour_base', imd.module == 'tour_base', '%s.%s' % (imd.module, imd.name))

# 3. 无残留 tour_product.menu_tms_root
residual = env['ir.model.data'].search_count([
    ('module', '=', 'tour_product'), ('name', '=', 'menu_tms_root'),
])
check('无残留 tour_product.menu_tms_root', residual == 0, residual)

# 4. 基础安全组存在
for xmlid in ['tour_base.group_tour_user', 'tour_base.group_tour_manager',
              'tour_base.group_tour_sensitive_data']:
    try:
        g = env.ref(xmlid)
        check('组存在 %s' % xmlid, bool(g.id), g.name)
    except ValueError:
        check('组存在 %s' % xmlid, False, 'NOT FOUND')

# 5. 出纳组隐含敏感数据查看组
try:
    treasurer = env.ref('tour_accounting.group_tour_accounting_treasurer')
    sensitive = env.ref('tour_base.group_tour_sensitive_data')
    check('出纳组隐含敏感数据查看组',
          sensitive.id in treasurer.all_implied_ids.ids,
          'implied ids = %s' % treasurer.all_implied_ids.ids)
except ValueError as e:
    check('出纳组隐含敏感数据查看组', False, str(e))

# 6. 分类 category 存在
cat = env['ir.module.category'].search([('name', '=', '旅行社管理')], limit=1)
check('ir.module.category 旅行社管理存在', bool(cat.id))

# 7. 加密工具迁移后仍工作（tour_base.models.field_crypto）
key = field_crypto.get_key(env)
check('密钥就绪(32字节)', key is not None and len(key) == 32,
      'len=%s' % (len(key) if key else 0))
guide = env['tour.guide'].search([], limit=1)
if guide:
    env.cr.execute("SELECT id_num FROM tour_guide WHERE id=%s", [guide.id])
    raw = env.cr.fetchone()[0]
    check('guide.id_num 落盘为密文', bool(raw) and field_crypto.is_encrypted(raw),
          'is_encrypted=%s' % field_crypto.is_encrypted(raw))
    # 默认用户（无敏感数据组）read 掩码
    base_user = env.ref('base.group_user')
    nu = env['res.users'].search([('group_ids', 'in', [base_user.id]),
                                  ('share', '=', False)], limit=1)
    if not nu:
        nu = env.ref('base.user_admin')
    masked_read = env['tour.guide'].with_user(nu).browse(guide.id).read(['id_num'])[0]['id_num']
    check('普通用户 read() 掩码（****后4位）',
          masked_read.startswith('*') and not field_crypto.is_encrypted(masked_read),
          masked_read)
else:
    check('存在导游记录', False, 'no guide data')

# 8. config_parameter 读写（res.config.settings 标准模式）
params = env['ir.config_parameter'].sudo()
params.set_param('tms.guide_default_commission_rate', '12.5')
env.cr.commit()
back = params.get_param('tms.guide_default_commission_rate')
check('config_parameter 写入/读回', back == '12.5', back)
# res.config.settings：config_parameter 字段经 default_get 读取（标准机制）
settings = env['res.config.settings'].create({})
vals = settings.default_get(list(settings._fields))
check('settings.default_get 读取分成比例', str(vals.get('tms_guide_default_commission_rate')) == '12.5',
      vals.get('tms_guide_default_commission_rate'))
settings.unlink()
params.set_param('tms.guide_default_commission_rate', False)
env.cr.commit()

# 9. 默认币种字段可写（settings set_values）
settings2 = env['res.config.settings'].create({'tms_default_currency_id': env.company.currency_id.id})
settings2.set_values()
env.cr.commit()
cur = params.get_param('tms.default_currency_id')
check('settings.set_values 默认币种落 config_parameter', bool(cur), cur)
settings2.unlink()
params.set_param('tms.default_currency_id', False)
env.cr.commit()

fails = [r for r in results if not r[1]]
print('=== 汇总：%s 通过 / %s 失败 ===' % (len(results) - len(fails), len(fails)))
if fails:
    for r in fails:
        print('  FAIL -', r[0])
