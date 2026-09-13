-- =============================================================================
-- 待实施功能虚菜单 → 占位 action（act_url → /tutor/pending）挂载脚本
-- -----------------------------------------------------------------------------
-- 目的：给上一轮已建的「待实施功能」顶级菜单(632) + 10 个虚子菜单(633-642)
--       挂上 act_url 占位 action，让叶子菜单在 _visible_menu_ids 中变为 True，
--       从而在界面可见可点击（点击跳 /tutor/pending 提示页）。
--
-- 关键修正：Odoo 的 _visible_menu_ids 对「无 groups 的菜单」视为全员可见，
--           并不会「继承父菜单的 group 限制」。上一轮子菜单没挂 group，若只加
--           action，普通用户将能看到这些叶子菜单（父菜单被 group 隐藏，但子菜单
--           无 group 且带 action，会单独进入 visible 集合）。因此本脚本同时给
--           10 个子菜单补上 base.group_system(gid=4) 组限制，确保仅超管可见。
--
-- 幂等：所有插入/更新前先查 ir_model_data / 现有值，可重复执行不产生重复记录。
-- 真源：与 tour_base/views/menu.xml 一一对应（action xmlid + menuitem groups 属性）。
-- =============================================================================

DO $$
DECLARE
    v_gid_system INTEGER;
    r            RECORD;
    v_act_id     INTEGER;
    v_menu_id    INTEGER;
BEGIN
    SELECT res_id INTO v_gid_system
      FROM ir_model_data WHERE module = 'base' AND name = 'group_system';

    FOR r IN
        SELECT * FROM (VALUES
            ('menu_tms_pending',          'action_tms_pending',          '待实施功能',             '/tutor/pending?name=待实施功能'),
            ('menu_tms_pending_ticket',   'action_tms_pending_ticket',   '票务管理（待实施）',      '/tutor/pending?name=票务管理'),
            ('menu_tms_pending_b2b',      'action_tms_pending_b2b',      '同业分销 B2B（待实施）',  '/tutor/pending?name=同业分销 B2B'),
            ('menu_tms_pending_miniapp',  'action_tms_pending_miniapp',  '小程序 API（待实施）',    '/tutor/pending?name=小程序 API'),
            ('menu_tms_pending_alipay',   'action_tms_pending_alipay',   '支付宝费控（待实施）',    '/tutor/pending?name=支付宝费控'),
            ('menu_tms_pending_oa',       'action_tms_pending_oa',       '办公管理 OA（待实施）',   '/tutor/pending?name=办公管理 OA'),
            ('menu_tms_pending_visa',     'action_tms_pending_visa',     '签证管理（待实施）',      '/tutor/pending?name=签证管理'),
            ('menu_tms_pending_platform', 'action_tms_pending_platform', '平台商管理（待实施）',    '/tutor/pending?name=平台商管理'),
            ('menu_tms_pending_fleet',    'action_tms_pending_fleet',    '车队管理系统（待实施）',  '/tutor/pending?name=车队管理系统'),
            ('menu_tms_pending_approval', 'action_tms_pending_approval', '通用审批引擎（待实施）',  '/tutor/pending?name=通用审批引擎'),
            ('menu_tms_pending_bi',       'action_tms_pending_bi',       '独立 BI（待实施）',       '/tutor/pending?name=独立 BI')
        ) AS t(menu_xmlid, action_xmlid, action_name, url)
    LOOP
        -- 1) 创建 / 取 act_url（幂等：按 xmlid 查重）
        SELECT d.res_id INTO v_act_id
          FROM ir_model_data d
         WHERE d.module = 'tour_base' AND d.name = r.action_xmlid
           AND d.model = 'ir.actions.act_url';

        IF v_act_id IS NULL THEN
            INSERT INTO ir_act_url (name, type, url, target, binding_type)
            VALUES (jsonb_build_object('en_US', r.action_name),
                    'ir.actions.act_url', r.url, 'self', 'action')
            RETURNING id INTO v_act_id;

            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES ('tour_base', r.action_xmlid, 'ir.actions.act_url', v_act_id, false);
        END IF;

        -- 2) 取菜单 id
        SELECT d.res_id INTO v_menu_id
          FROM ir_model_data d
         WHERE d.module = 'tour_base' AND d.name = r.menu_xmlid
           AND d.model = 'ir.ui.menu';

        -- 3) 挂 action（ir_ui_menu.action → 'ir.actions.act_url,<id>'）
        IF v_menu_id IS NOT NULL THEN
            UPDATE ir_ui_menu
               SET action = 'ir.actions.act_url,' || v_act_id
             WHERE id = v_menu_id
               AND (action IS NULL OR action <> 'ir.actions.act_url,' || v_act_id);
        END IF;

        -- 4) 子菜单（非顶级）补 base.group_system 组限制，确保仅超管可见
        IF r.menu_xmlid <> 'menu_tms_pending' AND v_menu_id IS NOT NULL THEN
            INSERT INTO ir_ui_menu_group_rel (menu_id, gid)
            SELECT v_menu_id, v_gid_system
             WHERE NOT EXISTS (
                SELECT 1 FROM ir_ui_menu_group_rel rel
                 WHERE rel.menu_id = v_menu_id AND rel.gid = v_gid_system);
        END IF;
    END LOOP;
END $$;

-- 5) 通知运行中的 Web 进程失效菜单缓存（跨进程 orm_signaling），无需重启
INSERT INTO orm_signaling_default DEFAULT VALUES;
