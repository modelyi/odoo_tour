-- =============================================================================
-- 待实施功能占位菜单（虚菜单，仅超级用户可见，不实现逻辑）
-- -----------------------------------------------------------------------------
-- 目的：为 10 项「暂不做、未来实施」的功能在菜单树里保留占位入口。
--   顶级菜单「待实施功能」挂在 menu_tms_root(=220) 下，sequence=90 放最后，
--   仅 base.group_system(gid=4) 可见；其下 10 个虚子菜单无 action、纯占位，
--   菜单名统一加「（待实施）」后缀。
--
-- 与 XML 真源一一对应（tour_base/views/menu.xml），xmlid 完全一致，
-- 保证下次 -i 时 Odoo 按 xmlid 匹配更新、不重复建菜单。
-- 本 SQL 幂等：先按 ir_model_data(module,name) 查重，已存在则跳过。
-- =============================================================================

DO $$
DECLARE
    root_id    INTEGER := 220;          -- tour_base.menu_tms_root（旅行社管理）
    pending_id INTEGER;
    child_id   INTEGER;
    m          RECORD;
    top_name   TEXT := '待实施功能';
BEGIN
    -- 1) 顶级菜单「待实施功能」
    SELECT d.res_id INTO pending_id
      FROM ir_model_data d
     WHERE d.module = 'tour_base' AND d.name = 'menu_tms_pending';

    IF pending_id IS NULL THEN
        INSERT INTO ir_ui_menu (sequence, parent_id, name, parent_path, active)
        VALUES (90, root_id, jsonb_build_object('en_US', top_name), NULL, true)
        RETURNING id INTO pending_id;

        UPDATE ir_ui_menu
           SET parent_path = (SELECT parent_path FROM ir_ui_menu WHERE id = root_id)
                             || pending_id || '/'
         WHERE id = pending_id;

        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        VALUES ('tour_base', 'menu_tms_pending', 'ir.ui.menu', pending_id, false);

        -- 仅超级用户（base.group_system, gid=4）可见
        INSERT INTO ir_ui_menu_group_rel (menu_id, gid) VALUES (pending_id, 4);
    END IF;

    -- 2) 10 个虚子菜单（无 action、纯占位，继承父菜单的超级用户可见性）
    FOR m IN
        SELECT * FROM (VALUES
            ('menu_tms_pending_ticket',   '票务管理（待实施）',     10),
            ('menu_tms_pending_b2b',      '同业分销 B2B（待实施）',  20),
            ('menu_tms_pending_miniapp',  '小程序 API（待实施）',   30),
            ('menu_tms_pending_alipay',   '支付宝费控（待实施）',    40),
            ('menu_tms_pending_oa',       '办公管理 OA（待实施）',   50),
            ('menu_tms_pending_visa',     '签证管理（待实施）',      60),
            ('menu_tms_pending_platform', '平台商管理（待实施）',    70),
            ('menu_tms_pending_fleet',    '车队管理系统（待实施）',  80),
            ('menu_tms_pending_approval', '通用审批引擎（待实施）',  90),
            ('menu_tms_pending_bi',       '独立 BI（待实施）',       100)
        ) AS t(xmlid, label, seq)
    LOOP
        SELECT d.res_id INTO child_id
          FROM ir_model_data d
         WHERE d.module = 'tour_base' AND d.name = m.xmlid;

        IF child_id IS NULL THEN
            INSERT INTO ir_ui_menu (sequence, parent_id, name, parent_path, active)
            VALUES (m.seq, pending_id, jsonb_build_object('en_US', m.label), NULL, true)
            RETURNING id INTO child_id;

            UPDATE ir_ui_menu
               SET parent_path = (SELECT parent_path FROM ir_ui_menu WHERE id = pending_id)
                                 || child_id || '/'
             WHERE id = child_id;

            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES ('tour_base', m.xmlid, 'ir.ui.menu', child_id, false);
        END IF;
    END LOOP;
END $$;

-- =============================================================================
-- 3) 通知运行中的 Web 进程失效菜单缓存（等价于通过 ORM write 触发 signal_changes）
--    Odoo 19 多进程用 orm_signaling_* 表做跨进程缓存失效：本菜单用 @tools.ormcache
--    落在 default 缓存，插入一行即可让所有 worker 在下次 check_signaling 时清缓存、
--    重新查询菜单树，无需重启容器。幂等（仅递增计数，无副作用）。
-- =============================================================================
INSERT INTO orm_signaling_default DEFAULT VALUES;
