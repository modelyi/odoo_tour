-- ============================================================================
-- tour_tutor 菜单手动建库 SQL（不 -i 不重启，供 O2C 运行期间先行建菜单）
--
-- 作用：在 O2C 过账运行期间（不能 -i/-u、不能重启容器），用 SQL 直接建立
--       「产品导览」顶级菜单（groups=base.group_system，仅超级用户可见）及两个
--       子菜单，并把 external id 挂到 tour_tutor 模块。
--
-- 幂等：所有插入前先检查 ir_model_data 是否存在，可重复执行不产生重复记录。
-- 说明：controller 路由（/tutor、/tutor/menus）需 -i 加载进 registry 后生效；
--       本脚本只建菜单/动作/组关系，菜单点击在 -i 前会 404。
-- ============================================================================

DO $$
DECLARE
    v_gid_system INTEGER;
    v_act_index  INTEGER;
    v_act_menus  INTEGER;
    v_root       INTEGER;
    v_menu_index INTEGER;
    v_menu_menus INTEGER;
BEGIN
    SELECT res_id INTO v_gid_system
      FROM ir_model_data WHERE module = 'base' AND name = 'group_system';

    -- 1) 动作：产品导览文档（/tutor）
    IF EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'action_tutor_index') THEN
        SELECT res_id INTO v_act_index
          FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'action_tutor_index';
    ELSE
        INSERT INTO ir_act_url (name, type, url, target, binding_type)
        VALUES ('{"en_US": "产品导览文档"}', 'ir.actions.act_url', '/tutor', 'self', 'action')
        RETURNING id INTO v_act_index;
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        VALUES ('tour_tutor', 'action_tutor_index', 'ir.actions.act_url', v_act_index, false);
    END IF;

    -- 2) 动作：角色菜单预览（/tutor/menus）
    IF EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'action_tutor_menus') THEN
        SELECT res_id INTO v_act_menus
          FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'action_tutor_menus';
    ELSE
        INSERT INTO ir_act_url (name, type, url, target, binding_type)
        VALUES ('{"en_US": "角色菜单预览"}', 'ir.actions.act_url', '/tutor/menus', 'self', 'action')
        RETURNING id INTO v_act_menus;
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        VALUES ('tour_tutor', 'action_tutor_menus', 'ir.actions.act_url', v_act_menus, false);
    END IF;

    -- 3) 顶级菜单「产品导览」
    IF EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'menu_tutor_root') THEN
        SELECT res_id INTO v_root
          FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'menu_tutor_root';
    ELSE
        INSERT INTO ir_ui_menu (name, sequence, parent_id, active)
        VALUES ('{"en_US": "产品导览"}', 100, NULL, true)
        RETURNING id INTO v_root;
        UPDATE ir_ui_menu SET parent_path = v_root::text || '/' WHERE id = v_root;
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        VALUES ('tour_tutor', 'menu_tutor_root', 'ir.ui.menu', v_root, false);
    END IF;

    -- 4) 顶级菜单 groups -> base.group_system（仅超级用户可见）
    INSERT INTO ir_ui_menu_group_rel (menu_id, gid)
    SELECT v_root, v_gid_system
     WHERE NOT EXISTS (
        SELECT 1 FROM ir_ui_menu_group_rel WHERE menu_id = v_root AND gid = v_gid_system);

    -- 5) 子菜单：产品导览文档
    IF EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'menu_tutor_index') THEN
        SELECT res_id INTO v_menu_index
          FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'menu_tutor_index';
    ELSE
        INSERT INTO ir_ui_menu (name, sequence, parent_id, action, active)
        VALUES ('{"en_US": "产品导览文档"}', 10, v_root,
                'ir.actions.act_url,' || v_act_index, true)
        RETURNING id INTO v_menu_index;
        UPDATE ir_ui_menu
           SET parent_path = v_root::text || '/' || v_menu_index::text || '/'
         WHERE id = v_menu_index;
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        VALUES ('tour_tutor', 'menu_tutor_index', 'ir.ui.menu', v_menu_index, false);
    END IF;

    -- 6) 子菜单：角色菜单预览
    IF EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'menu_tutor_menus') THEN
        SELECT res_id INTO v_menu_menus
          FROM ir_model_data WHERE module = 'tour_tutor' AND name = 'menu_tutor_menus';
    ELSE
        INSERT INTO ir_ui_menu (name, sequence, parent_id, action, active)
        VALUES ('{"en_US": "角色菜单预览"}', 20, v_root,
                'ir.actions.act_url,' || v_act_menus, true)
        RETURNING id INTO v_menu_menus;
        UPDATE ir_ui_menu
           SET parent_path = v_root::text || '/' || v_menu_menus::text || '/'
         WHERE id = v_menu_menus;
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        VALUES ('tour_tutor', 'menu_tutor_menus', 'ir.ui.menu', v_menu_menus, false);
    END IF;

    RAISE NOTICE 'tour_tutor 菜单就绪：root=%  index=%  menus=%', v_root, v_menu_index, v_menu_menus;
END $$;
