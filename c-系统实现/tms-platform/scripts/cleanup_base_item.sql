-- 收尾清理：tour.base.item 数据库残留（模型文件已删，DB 残留需手动清理）
-- 执行前提：tms-odoo 已停止
BEGIN;

-- 1. 删除 res_partner.level_id -> tour_base_item 的外键（阻塞 DROP TABLE）
ALTER TABLE res_partner DROP CONSTRAINT IF EXISTS res_partner_level_id_fkey;

-- 2. 删除 ir_model_data（先删外部 id，再删底层记录）
-- 2a. 迁移数据残留 et_migrate.et_item_*（model='tour.base.item'）
DELETE FROM ir_model_data WHERE model = 'tour.base.item';

-- 2b. tour_product 定义的 tour.base.item 相关外部 id
DELETE FROM ir_model_data WHERE model = 'ir.model' AND res_id = 550;  -- model_tour_base_item
DELETE FROM ir_model_data WHERE model = 'ir.model.fields'
  AND res_id IN (SELECT id FROM ir_model_fields WHERE model_id = 550);  -- field_tour_base_item__*
DELETE FROM ir_model_data WHERE model = 'ir.model.fields.selection'
  AND res_id IN (SELECT id FROM ir_model_fields_selection
                 WHERE field_id IN (SELECT id FROM ir_model_fields WHERE model_id = 550));  -- selection__*
DELETE FROM ir_model_data WHERE model = 'ir.model.access' AND res_id IN (566, 567, 580, 581);
DELETE FROM ir_model_data WHERE model = 'ir.actions.act_window' AND res_id = 314;  -- action_tour_base_item
DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id IN (911, 912);  -- view_tour_base_item_list/form
DELETE FROM ir_model_data WHERE model = 'ir.ui.menu' AND res_id = 228;  -- menu_tour_base_item

-- 2c. res.users.level_id 孤儿字段（代码已删除，无列，relation=tour.base.item）
DELETE FROM ir_model_data WHERE model = 'ir.model.fields' AND res_id = 8808;  -- field_res_users__level_id

-- 3. 删除底层记录（注意 FK：selection->field->model）
DELETE FROM ir_model_fields_selection
  WHERE field_id IN (SELECT id FROM ir_model_fields WHERE model_id = 550);
DELETE FROM ir_model_constraint WHERE model = 550;
DELETE FROM ir_model_access WHERE model_id = 550;
DELETE FROM ir_model_fields WHERE model_id = 550;
DELETE FROM ir_ui_menu WHERE id = 228;
DELETE FROM ir_ui_view WHERE id IN (911, 912);
DELETE FROM ir_act_window WHERE id = 314;
DELETE FROM ir_model WHERE id = 550;

-- 4. res.users.level_id 孤儿字段记录
DELETE FROM ir_model_fields WHERE id = 8808;

-- 5. 删除表
DROP TABLE IF EXISTS tour_base_item;

COMMIT;
