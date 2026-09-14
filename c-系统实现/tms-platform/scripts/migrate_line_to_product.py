# -*- coding: utf-8 -*-
"""tour.line → product.template 委托迁移（第一阶段，幂等）。

将已存在的 tour.line（213）与 tour.line.type（85）迁移到 product 体系：
  - M1 分类：tour.line.type(85) → product.category（扁平原样，parent 空）
  - M2 产品：每条 tour.line 建一个 product.template(type=service) 并回填 product_tmpl_id
    name → name / code → default_code / adult_price → list_price / line_type_id → categ_id
    active → active / audit_state=='approved' → is_published / sale_ok=True

前提：先 `-u tour_product,tour_website` 完成模型改版（tour_line 表新增 product_tmpl_id 列，
旧列 name/code/active/adult_price/line_type_id 与 tour_line_type 表保留为孤儿列/表，供本脚本读取）。

幂等：按「tour_line.product_tmpl_id IS NULL」判断未迁移行；分类按 name 复用已建 product.category。
可重复执行，不会重复建 product.template / product.category。

运行（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms --no-http < scripts/migrate_line_to_product.py
"""


def _fmt_ok(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), '-', name, ('| ' + str(detail) if detail else ''))
    return bool(cond)


def main():
    cr = env.cr

    # ---------------- M1：分类迁移 ----------------
    cr.execute("SELECT id, name FROM tour_line_type ORDER BY id")
    types = cr.fetchall()
    Categ = env['product.category']
    type_to_categ = {}
    created_categ = 0
    for type_id, name in types:
        categ = Categ.search([('name', '=', name)], limit=1)
        if not categ:
            categ = Categ.create({'name': name})
            created_categ += 1
        type_to_categ[type_id] = categ.id
    cr.commit()
    print('[M1 category] source=%d created=%d reused=%d' % (
        len(types), created_categ, len(types) - created_categ))

    # ---------------- M2：产品模板创建 + 回填 ----------------
    cr.execute("""
        SELECT id, name, code, active, adult_price, line_type_id, audit_state
        FROM tour_line
        WHERE product_tmpl_id IS NULL
        ORDER BY id
    """)
    lines = cr.fetchall()
    Template = env['product.template']
    created_tmpl = 0
    uncategoried = 0
    for line_id, name, code, active, adult_price, line_type_id, audit_state in lines:
        categ_id = type_to_categ.get(line_type_id)
        if not categ_id:
            uncategoried += 1
        tmpl = Template.create({
            'name': name or '',
            'type': 'service',
            'default_code': code or '',
            'list_price': float(adult_price or 0.0),
            'categ_id': categ_id,
            'active': bool(active),
            'sale_ok': True,
            'is_published': (audit_state == 'approved'),
        })
        cr.execute(
            "UPDATE tour_line SET product_tmpl_id = %s WHERE id = %s",
            (tmpl.id, line_id))
        created_tmpl += 1
    cr.commit()
    env.invalidate_all()
    print('[M2 template] lines_migrated=%d uncategoried=%d' % (created_tmpl, uncategoried))

    # ---------------- 校验 ----------------
    results = []
    cr.execute("SELECT count(*) FROM tour_line")
    total_line = cr.fetchone()[0]
    cr.execute("SELECT count(*) FROM tour_line WHERE product_tmpl_id IS NOT NULL")
    linked_line = cr.fetchone()[0]
    results.append(_fmt_ok('213 条线路全有 product_tmpl_id', linked_line == total_line,
                           '%d/%d' % (linked_line, total_line)))

    cr.execute("SELECT count(*) FROM tour_line WHERE product_tmpl_id IS NULL")
    null_line = cr.fetchone()[0]
    results.append(_fmt_ok('无残留未迁移线路', null_line == 0, null_line))

    cr.execute("SELECT count(*) FROM product_template WHERE type='service'")
    svc_tmpl = cr.fetchone()[0]
    results.append(_fmt_ok('product.template 新增 service 产品（≥213）', svc_tmpl >= 213, svc_tmpl))

    cr.execute("SELECT count(*) FROM product_category")
    total_categ = cr.fetchone()[0]
    results.append(_fmt_ok('85 条分类已迁入 product.category（≥89 含 demo）',
                           total_categ >= 89, total_categ))

    # 下游 FK 无损：tour.plan.line_id 全部有效
    cr.execute("SELECT count(*) FROM tour_plan WHERE line_id NOT IN (SELECT id FROM tour_line)")
    orphan_plan = cr.fetchone()[0]
    results.append(_fmt_ok('tour.plan.line_id 下游 FK 无损', orphan_plan == 0, orphan_plan))

    cr.execute("SELECT count(*) FROM tour_departure WHERE line_id NOT IN (SELECT id FROM tour_line)")
    orphan_dep = cr.fetchone()[0]
    results.append(_fmt_ok('tour.departure.line_id FK 无损', orphan_dep == 0, orphan_dep))

    # 抽样比对：name / list_price 委托后一致
    cr.execute("""
        SELECT pt.name, pt.list_price
        FROM tour_line tl JOIN product_template pt ON tl.product_tmpl_id = pt.id
        ORDER BY tl.id LIMIT 3
    """)
    samples = cr.fetchall()
    print('--- 抽样（product.template.name / list_price） ---')
    for s in samples:
        print('  ', s)

    fails = [r for r in results if not r]
    print('=== 汇总：%d 通过 / %d 失败 ===' % (len(results) - len(fails), len(fails)))


if __name__ == '__main__':
    main()
