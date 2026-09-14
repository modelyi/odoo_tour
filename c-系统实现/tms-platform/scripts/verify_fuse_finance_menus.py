# -*- coding: utf-8 -*-
"""验证融合后菜单可见性：用 Odoo 自身 _visible_menu_ids() 实测。
只读 + 临时用户，跑完即删。"""
import time

Menu = env['ir.ui.menu']
Users = env['res.users']
Groups = env['res.groups']

ACC_TOP = env.ref('account.menu_finance')                # 151
TOUR_FIN = env.ref('tour_accounting.menu_tour_finance')  # 646
biz_xmlids = [
    'tour_accounting.menu_tour_payment_claim',
    'tour_accounting.menu_tour_pay_request',
    'tour_accounting.menu_tour_reconciliation',
    'tour_accounting.menu_tour_commission',
    'tour_accounting.menu_tour_plan_account',
    'tour_accounting.menu_tour_guide_loan',
    'tour_accounting.menu_tour_guide_real_pay',
    'tour_accounting.menu_tour_dunning',
    'tour_accounting.menu_tour_plan_account_aging',
]
biz_ids = {env.ref(x).id for x in biz_xmlids}

suffix = str(int(time.time()))
created = []

def test(label, group_xmlids, expect_acc, expect_fin):
    gids = [env.ref(x).id for x in group_xmlids]
    login = 'fuse_verify_%s_%s' % (label, suffix)
    u = Users.create({'name': '融合验证-' + label, 'login': login,
                      'group_ids': [(6, 0, gids)]})
    created.append(u.id)
    u.flush_recordset()
    visible = set(Menu.with_user(u)._visible_menu_ids())
    acc_ok = ACC_TOP.id in visible
    fin_ok = TOUR_FIN.id in visible
    biz_visible = sorted(biz_ids & visible)
    print('%-12s acc=%s(%s) 旅行社财务=%s(%s) 业务菜单可见=%s/%s'
          % (label, acc_ok, '预期%d' % expect_acc, fin_ok, '预期%d' % expect_fin,
             len(biz_visible), len(biz_ids)))
    return acc_ok, fin_ok, biz_visible

print('=== _visible_menu_ids() 实测 ===')
acc, fin, biz = test('财务', ['tour_base.group_tour_finance'], 1, 1)
acc2, fin2, biz2 = test('计调', ['tour_base.group_tour_operator'], 0, 0)
acc3, fin3, biz3 = test('销售', ['tour_base.group_tour_sales'], 0, 0)
acc4, fin4, biz4 = test('纯开票(非TMS财务)', ['account.group_account_invoice'], 1, 0)

ok = (acc and fin and len(biz) == len(biz_ids)
      and (not acc2) and (not fin2)
      and (not acc3) and (not fin3)
      and acc4 and (not fin4) and len(biz4) == 0)

if created:
    Users.browse(created).unlink()
    env.cr.commit()
print('清理临时用户: %s' % created)
print('RESULT: %s' % ('PASS' if ok else 'FAIL'))
