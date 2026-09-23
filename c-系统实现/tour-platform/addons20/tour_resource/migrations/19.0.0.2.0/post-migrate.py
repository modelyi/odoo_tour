# -*- coding: utf-8 -*-
"""Post-migrate: 将 res_partner 中的供应商数据迁移到 tour_supplier 独立表。

此时 ORM 已创建 tour_supplier 表并更新了 FK 列类型。
"""


def migrate(cr, version):
    # 1. 将 res_partner 中 sup_type 不为空的记录复制到 tour_supplier
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'tour_supplier'
    """)
    supplier_cols = {row[0] for row in cr.fetchall()}

    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'res_partner'
    """)
    partner_cols = {row[0] for row in cr.fetchall()}

    common = supplier_cols & partner_cols - {'id', 'create_date', 'write_date',
                                              'create_uid', 'write_uid'}
    common.discard('partner_id')

    cols = sorted(common)
    if not cols:
        return

    col_list = ', '.join(cols)
    cr.execute("""
        INSERT INTO tour_supplier (create_date, write_date, partner_id, %s)
        SELECT NOW(), NOW(), rp.id, %s
        FROM res_partner rp
        WHERE rp.sup_type IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM tour_supplier ts WHERE ts.partner_id = rp.id
          )
    """ % (col_list, col_list))

    # 2. 更新 FK 引用：tour_vehicle.supplier_id
    _remap_fk(cr, 'tour_vehicle', 'supplier_id')

    # 3. 更新 FK 引用：tour_shop_agreement.shop_id
    _remap_fk(cr, 'tour_shop_agreement', 'shop_id')

    # 4. 更新 FK 引用：tour_shop_record.shop_id
    if _table_exists(cr, 'tour_shop_record'):
        _remap_fk(cr, 'tour_shop_record', 'shop_id')

    # 5. 更新 FK 引用：tour_commission.shop_id
    if _table_exists(cr, 'tour_commission'):
        _remap_fk(cr, 'tour_commission', 'shop_id')

    # 6. 更新 FK 引用：project_task.supplier_id
    if _table_exists(cr, 'project_task'):
        _remap_fk_project_task(cr)


def _remap_fk(cr, table, column):
    if not _table_exists(cr, table):
        return
    cr.execute("""
        UPDATE {table} t
        SET {col} = ts.id
        FROM tour_supplier ts
        WHERE ts.partner_id = t.{col}
          AND t.{col} IS NOT NULL
    """.format(table=table, col=column))


def _remap_fk_project_task(cr):
    cr.execute("""
        UPDATE project_task pt
        SET supplier_id = ts.id
        FROM tour_supplier ts
        WHERE ts.partner_id = pt.supplier_id
          AND pt.supplier_id IS NOT NULL
          AND pt.resource_type IN ('hotel', 'meal', 'scenic', 'vehicle')
    """)


def _table_exists(cr, table):
    cr.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (table,))
    return cr.fetchone()
