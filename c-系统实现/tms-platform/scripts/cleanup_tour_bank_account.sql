-- 收尾清理：tour.bank.account 数据库残留（模型文件已删，-u 已清 ir_model/字段/视图/菜单/权限，
-- 但其它模块为其 mail.thread/mail.activity.mixin 自动创建的外部 id 残留 + 表仍在，需手动清理）
-- 执行前提：已备份 tour_bank_account 表数据 + claim.account_id 已改写 + -u tour_accounting 已完成
BEGIN;

-- 1. 删除孤儿 ir_model_data（calendar/rating/mail/portal/sms/snailmail/mass_mailing 等模块
--    为 tour.bank.account 的 mail.thread/mail.activity.mixin 继承与跟踪字段创建的外部 id，
--    底层 ir.model.fields/fields.selection/inherit 已随 ir_model 删除 CASCADE 清除）
DELETE FROM ir_model_data WHERE name LIKE '%tour_bank_account%';

-- 2. 删除表（无任何外键引用：claim.account_id FK 已改为 account_journal）
DROP TABLE IF EXISTS tour_bank_account;

COMMIT;
