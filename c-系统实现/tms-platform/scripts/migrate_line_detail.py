# -*- coding: utf-8 -*-
"""
行程明细补迁：tour.line -> tour.line.detail（按 day_num 逐日生成）
修复 UAT S1.4「行程明细存在」。

运行方式（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms \
      --config /etc/odoo/odoo.conf --no-http --dev '' < migrate_line_detail.py

数据源说明：
    任务假定 line_products.csv 的 LineDetailsRich 为富文本（含「第N天/DAY N」标题
    + 餐饮/住宿/交通）。实际脱敏数据该列 **全部为空**（demo/et_data 两个目录均 0 非空），
    且无独立的逐日明细表。因此本脚本：
      1) 按线路 day_num 逐日生成明细（day_no 连续 1..day_num）；
      2) 标题/城市从线路名称中的地区关键词 + 出发地/目的地提取；
      3) 餐/住宿/交通从线路现有文本字段（srv_text/fee_include/fee_exclude/
         send_traffic/end_traffic）解析；
      4) 原始富文本保留到 src_html（本次为空，字段已补，后续有富文本可回填）；
      5) 剩余可用文本降级放 content 字段，不丢失。

幂等：自然键 (line_id, day_no) 判重，重跑 created=0。
模型改动：tour_line_detail.py 增加 src_html = fields.Html('原文')。
"""
import re

BATCH = 500
MIGRATE_CTX = dict(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)

# 地区关键词（先长后短，命中即止）-> 标准化城市/地区名
REGION_MAP = [
    ('长韶张凤', '张家界'),
    ('梵净', '贵州'),
    ('梵天', '贵州'),
    ('内蒙古', '内蒙古'),
    ('东北', '东北'),
    ('西北', '西北'),
    ('华东', '华东'),
    ('西南', '西南'),
    ('华北', '华北'),
    ('华南', '华南'),
    ('京城', '北京'),
    ('皇城', '北京'),
    ('古北', '北京'),
    ('北京', '北京'),
    ('天津', '天津'),
    ('上海', '上海'),
    ('重庆', '重庆'),
    ('西安', '西安'),
    ('东华市', '西安'),
    ('东市', '西安'),
    ('西市', '西安'),
    ('西线', '西安'),
    ('汉中', '汉中'),
    ('洋县', '汉中'),
    ('三峡', '三峡'),
    ('贵州', '贵州'),
    ('黔', '贵州'),
    ('黄小西', '贵州'),
    ('黄、壶', '延安'),
    ('壶口', '延安'),
    ('延安', '延安'),
    ('烟台', '烟台'),
    ('日照', '日照'),
    ('聊城', '聊城'),
    ('青州', '青州'),
    ('泰安', '泰安'),
    ('沂蒙', '临沂'),
    ('灵岩', '济南'),
    ('馆陶', '邯郸'),
    ('坝上', '河北'),
    ('新疆', '新疆'),
    ('西藏', '西藏'),
    ('云南', '云南'),
    ('海南', '海南'),
    ('四川', '四川'),
    ('湖南', '湖南'),
    ('湖北', '湖北'),
    ('山东', '山东'),
    ('山西', '山西'),
    ('陕西', '陕西'),
    ('河南', '河南'),
    ('河北', '河北'),
    ('广东', '广东'),
    ('广西', '广西'),
    ('福建', '福建'),
    ('江西', '江西'),
    ('安徽', '安徽'),
    ('江苏', '江苏'),
    ('浙江', '浙江'),
    ('甘肃', '甘肃'),
    ('青海', '青海'),
    ('宁夏', '宁夏'),
    ('草原', '内蒙古'),
    ('沙漠', '内蒙古'),
]


def _gc():
    env.cr.commit()
    env.invalidate_all()


def _ensure_src_html_column():
    """src_html 字段已加入模型但未 -u 更新模块，手动补列（幂等）。"""
    env.cr.execute(
        "ALTER TABLE tour_line_detail ADD COLUMN IF NOT EXISTS src_html text")
    env.cr.commit()


def _extract_region(name):
    name = name or ''
    for kw, label in REGION_MAP:
        if kw in name:
            return label
    return ''


def _parse_meals(text):
    t = text or ''
    return {
        'meal_breakfast': bool(re.search(r'早', t)),
        'meal_lunch': bool(re.search(r'午|中餐|正餐|八菜一汤', t)),
        'meal_dinner': bool(re.search(r'晚|正餐|八菜一汤', t)),
    }


def _extract_hotel(text):
    """从文本抽取住宿说明（宿 XX / 住宿 XX / X 酒店 / 蒙古包 / 准X）。"""
    t = text or ''
    if not t:
        return ''
    for pat in (r'住宿[:：]?\s*([^\s,，;；。\n]{0,30})',
                r'宿[:：]?\s*([^\s,，;；。\n]{0,30})',
                r'([^\s,，;；。\n]{0,20}酒店)',
                r'([^\s,，;；。\n]{0,20}蒙古包)'):
        m = re.search(pat, t)
        if m and m.group(1).strip():
            return m.group(1).strip()[:30]
    return ''


def _extract_traffic(text, send_traffic='', end_traffic='', day_no=1, day_num=1):
    if day_no == 1 and send_traffic:
        return send_traffic
    if day_no == day_num and day_num > 1 and end_traffic:
        return end_traffic
    t = text or ''
    for kw in ('飞机', '高铁', '动车', '火车', '大巴', '专车', '游船', '轮船'):
        if kw in t:
            return kw
    return send_traffic or ''


def _build_content(day_no, day_num, line):
    """首日放线路可用行程/费用文本，末日放费用说明，中间日不臆造内容。"""
    parts = []
    if day_no == 1:
        if line.srv_text:
            parts.append(line.srv_text)
        if line.fee_include:
            parts.append('费用包含：' + line.fee_include)
        if line.fee_exclude:
            parts.append('费用不含：' + line.fee_exclude)
    elif day_no == day_num and day_num > 1:
        if line.fee_include:
            parts.append('费用包含：' + line.fee_include)
        if line.fee_exclude:
            parts.append('费用不含：' + line.fee_exclude)
    return '<br/>'.join(parts) if parts else ''


def import_line_details():
    Det = env['tour.line.detail']
    _ensure_src_html_column()

    # 幂等：现有自然键 (line_id, day_no)
    existing = set()
    for r in Det.search_read([], ['line_id', 'day_no']):
        existing.add((r['line_id'][0], r['day_no']))

    lines = env['tour.line'].search([])
    created = skipped = 0
    create_buf = []

    for line in lines:
        day_num = max(1, int(line.day_num or 1))
        region = _extract_region(line.name)
        city = line.send_place or line.end_place or region or ''
        combined = ' '.join([p for p in (line.srv_text or '', line.fee_include or '',
                                         line.fee_exclude or '') if p])
        meals = _parse_meals(combined)
        hotel = _extract_hotel(combined)

        for day_no in range(1, day_num + 1):
            key = (line.id, day_no)
            if key in existing:
                skipped += 1
                continue
            if day_no == 1 and line.send_place:
                title = '%s出发' % line.send_place
            elif day_no == day_num and day_num > 1 and line.end_place:
                title = '%s返程' % line.end_place
            elif day_no == 1:
                title = '出发'
            elif day_no == day_num and day_num > 1:
                title = '返程'
            else:
                title = region or '行程'
            day_city = city
            if day_no == day_num and day_num > 1 and line.end_place:
                day_city = line.end_place or city
            traffic = _extract_traffic(combined, line.send_traffic or '',
                                       line.end_traffic or '', day_no, day_num)
            vals = {
                'line_id': line.id,
                'day_no': day_no,
                'title': title,
                'city': day_city,
                'meal_breakfast': meals['meal_breakfast'],
                'meal_lunch': meals['meal_lunch'],
                'meal_dinner': meals['meal_dinner'],
                'hotel': hotel if day_no in (1, day_num) else hotel,
                'traffic': traffic,
                'content': _build_content(day_no, day_num, line),
                'src_html': (line.details_rich or ''),
                'sequence': day_no * 10,
            }
            create_buf.append(vals)
            existing.add(key)
            if len(create_buf) >= BATCH:
                Det.with_context(**MIGRATE_CTX).create(create_buf)
                created += len(create_buf)
                create_buf.clear()
                _gc()
    if create_buf:
        Det.with_context(**MIGRATE_CTX).create(create_buf)
        created += len(create_buf)
        create_buf.clear()
        _gc()

    print('[line.detail] created=%d skipped=%d total=%d' % (created, skipped, created + skipped))
    print('  tour.line.detail 总数 = %d' % Det.search_count([]))


def main():
    import_line_details()


if __name__ == '__main__':
    main()
