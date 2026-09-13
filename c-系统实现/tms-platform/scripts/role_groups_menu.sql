-- TMS 菜单角色化：建 4 个业务角色权限组 + 菜单 groups 可见性映射
-- 立即生效（SQL 直插），幂等（ON CONFLICT DO NOTHING），源码真源见各模块 XML。
-- 约定：role 组隐含 group_tour_user(98)，98 隐含 base.group_user(1)；
--       经理(99) 隐含 4 个 role 组 + 已有 98，从而看全部菜单。
BEGIN;

DO $$
DECLARE
    g_op    INT;
    g_fin   INT;
    g_sales INT;
    g_guide INT;
BEGIN
    -- 1) 建 4 个角色组（TMS privilege id=20，Odoo 19 无 category_id）
    INSERT INTO res_groups (name, sequence, privilege_id, comment) VALUES
        ('{"en_US":"计调"}'::jsonb,     40, 20, '{"en_US":"计调角色：线路产品、订单管理、计调操作、资源管理。"}'::jsonb),
        ('{"en_US":"财务"}'::jsonb,     50, 20, '{"en_US":"财务角色：订单管理、财务管理、报表中心。"}'::jsonb),
        ('{"en_US":"销售"}'::jsonb,     60, 20, '{"en_US":"销售/门店角色：线路产品、订单管理。"}'::jsonb),
        ('{"en_US":"导游管理"}'::jsonb, 70, 20, '{"en_US":"导游管理角色：资源管理、购物管理。"}'::jsonb)
    ON CONFLICT (privilege_id, name) DO NOTHING;

    SELECT id INTO g_op    FROM res_groups WHERE privilege_id = 20 AND name = '{"en_US":"计调"}'::jsonb;
    SELECT id INTO g_fin   FROM res_groups WHERE privilege_id = 20 AND name = '{"en_US":"财务"}'::jsonb;
    SELECT id INTO g_sales FROM res_groups WHERE privilege_id = 20 AND name = '{"en_US":"销售"}'::jsonb;
    SELECT id INTO g_guide FROM res_groups WHERE privilege_id = 20 AND name = '{"en_US":"导游管理"}'::jsonb;

    -- 2) 注册外部 ID（tour_base 命名空间，幂等）
    INSERT INTO ir_model_data (module, name, model, res_id, noupdate) VALUES
        ('tour_base', 'group_tour_operator',      'res.groups', g_op,    false),
        ('tour_base', 'group_tour_finance',       'res.groups', g_fin,   false),
        ('tour_base', 'group_tour_sales',         'res.groups', g_sales, false),
        ('tour_base', 'group_tour_guide_manager', 'res.groups', g_guide, false)
    ON CONFLICT (module, name) DO UPDATE SET res_id = EXCLUDED.res_id;

    -- 3) role 组隐含 group_tour_user(98)（98 → base.group_user(1)）
    INSERT INTO res_groups_implied_rel (gid, hid) VALUES
        (g_op, 98), (g_fin, 98), (g_sales, 98), (g_guide, 98)
    ON CONFLICT DO NOTHING;

    -- 4) 经理(99) 隐含 4 个 role 组
    INSERT INTO res_groups_implied_rel (gid, hid) VALUES
        (99, g_op), (99, g_fin), (99, g_sales), (99, g_guide)
    ON CONFLICT DO NOTHING;

    -- 5) 顶级菜单 groups 映射（menu_id, gid）
    INSERT INTO ir_ui_menu_group_rel (menu_id, gid) VALUES
        (221, g_op), (221, g_sales),                       -- 线路产品 → 计调 + 销售
        (261, g_op), (261, g_fin), (261, g_sales),         -- 订单管理 → 计调 + 财务 + 销售
        (266, g_op),                                       -- 计调操作 → 计调
        (256, g_op), (256, g_guide),                       -- 资源管理 → 计调 + 导游管理
        (275, g_guide),                                    -- 购物管理 → 导游管理
        (268, g_fin),                                      -- 财务管理 → 财务
        (277, g_fin)                                       -- 报表中心 → 财务
    ON CONFLICT DO NOTHING;
END $$;

COMMIT;
