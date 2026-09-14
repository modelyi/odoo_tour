# -*- coding: utf-8 -*-
"""TMS Tutor Controller：产品导览文档 + 角色菜单预览（仅超级用户）。

安全要点：
- 所有路由 auth='user'，进入即强制 user._is_superuser() 校验，非超级用户一律 404
- 只读展示 ir.ui.menu / ir_ui_menu_group_rel 元数据，不写任何业务数据
- 菜单预览用 sudo() 读元数据，按角色组 all_implied_ids（含自身 + 传递隐含组）过滤
"""
from odoo import http
from odoo.http import request

# 角色定义：(key, 中文名, 组 xmlid；None 表示超级用户 = 展示全部)
ROLES = [
    ('superuser', '超级用户', None),
    ('manager', '经理', 'tour_base.group_tour_manager'),
    ('operator', '计调', 'tour_base.group_tour_operator'),
    ('finance', '财务', 'tour_base.group_tour_finance'),
    ('sales', '销售', 'tour_base.group_tour_sales'),
    ('guide', '导游管理', 'tour_base.group_tour_guide_manager'),
]
_ROLE_INDEX = {key: (label, xmlid) for key, label, xmlid in ROLES}

# 功能模块 → 后端顶级菜单 xmlid（用于产品导览文档里的「菜单入口」链接）
_MODULE_MENUS = [
    ('product', 'tour_product.menu_tms_product'),
    ('order', 'tour_order.menu_tms_order'),
    ('operation', 'tour_operation.menu_tms_operation'),
    ('resource', 'tour_resource.menu_tms_resource'),
    ('shopping', 'tour_shopping.menu_tms_shopping'),
    ('finance', 'tour_accounting.menu_tour_finance'),
    ('report', 'tour_report.menu_tms_report'),
    ('base', 'tour_base.menu_tms_root'),
]


class TourTutor(http.Controller):

    # ---------- 权限守卫 ----------
    def _require_superuser(self):
        """非超级用户一律拒绝；通过返回 None，否则返回响应。

        注意：Odoo 19 的 res.users._is_superuser() 仅对技术根用户 uid=1
        （base.user_root）返回 True，而实际登录的超管是 uid=2（base.user_admin）。
        菜单按 groups="base.group_system" 控制可见性，故此处用 _is_system()
        （has_group('base.group_system')）与菜单口径保持一致。
        """
        if not request.env.user._is_system():
            return request.not_found()
        return None

    # ---------- 产品导览文档 ----------
    @http.route('/tutor', type='http', auth='user', website=True)
    def tutor_index(self, **kw):
        denied = self._require_superuser()
        if denied:
            return denied
        return request.render('tour_tutor.tutor_index', {
            'menu_links': self._resolve_menu_links(),
            'website_url': '/tours',
        })

    # ---------- 角色菜单预览 ----------
    @http.route('/tutor/menus', type='http', auth='user', website=True)
    def tutor_menus(self, **kw):
        denied = self._require_superuser()
        if denied:
            return denied
        role = kw.get('role') or 'superuser'
        if role not in _ROLE_INDEX:
            role = 'superuser'
        tree = self._build_menu_tree(role)
        return request.render('tour_tutor.tutor_menus', {
            'roles': ROLES,
            'current_role': role,
            'current_role_label': _ROLE_INDEX[role][0],
            'tree': tree,
            'menu_count': self._count_nodes(tree),
        })

    # ---------- 待实施功能占位页（10 个虚菜单 + 顶级菜单统一跳转至此）----------
    @http.route('/tutor/pending', type='http', auth='user', website=True)
    def tutor_pending(self, **kw):
        denied = self._require_superuser()
        if denied:
            return denied
        name = (kw.get('name') or '').strip()
        return request.render('tour_tutor.tutor_pending', {'name': name})


    # ---------- helpers ----------
    def _resolve_menu_links(self):
        """把各模块顶级菜单 xmlid 解析成可点击的后端链接。

        解析失败（模块未装等）回退为 '#'，避免页面渲染报错。
        """
        links = {}
        for key, xmlid in _MODULE_MENUS:
            try:
                menu = request.env.ref(xmlid)
                links[key] = '/web#menu_id=%s' % menu.id
            except ValueError:
                links[key] = '#'
        return links

    def _role_visible_ids(self, role):
        """返回该角色可见的菜单 id 集合；超级用户返回 None（全部可见）。"""
        label, xmlid = _ROLE_INDEX[role]
        if xmlid is None:
            return None
        group = request.env.ref(xmlid, raise_if_not_found=False)
        if not group:
            return set()
        # all_implied_ids = 组自身 + 传递隐含组（经理组自然含全部业务角色）
        return set(group.all_implied_ids.ids)

    def _build_menu_tree(self, role):
        """构建 menu_tms_root 下 7 个顶级菜单 + 各自子菜单的可见树。"""
        Menu = request.env['ir.ui.menu'].sudo()
        root = request.env.ref('tour_base.menu_tms_root', raise_if_not_found=False)
        if not root:
            return []

        # 取根菜单所有后代（不含根自身），按父菜单分组
        menus = Menu.search([('id', 'child_of', root.id)], order='sequence, id')
        visible_ids = self._role_visible_ids(role)

        by_parent = {}
        for m in menus:
            by_parent.setdefault(m.parent_id.id, []).append(m)

        def _visible(menu):
            if visible_ids is None:
                return True
            if not menu.group_ids:
                return True
            return bool(set(menu.group_ids.ids) & visible_ids)

        def _build(parent_id):
            nodes = []
            children = sorted(by_parent.get(parent_id, []),
                              key=lambda m: (m.sequence or 0, m.id))
            for m in children:
                if not _visible(m):
                    continue
                nodes.append(self._menu_node(m, _build(m.id)))
            return nodes

        return _build(root.id)

    def _menu_node(self, menu, children):
        action = menu.action
        if action:
            url = '/web#action=%s' % action.id
            has_action = True
        else:
            url = '/web#menu_id=%s' % menu.id
            has_action = False
        ext_id = menu.get_external_id().get(menu.id) or ''
        return {
            'id': menu.id,
            'name': menu.name,
            'xmlid': ext_id,
            'groups': [g.name for g in menu.group_ids],
            'has_action': has_action,
            'url': url,
            'children': children,
        }

    @staticmethod
    def _count_nodes(tree):
        total = 0
        for node in tree:
            total += 1 + TourTutor._count_nodes(node['children'])
        return total
