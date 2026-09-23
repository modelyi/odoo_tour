/** @odoo-module **/
// 线路班期 + 人数预估合计（只读预览，最终价由服务端重算）。
//
// 19 版这里是 `publicWidget.registry.XXX = publicWidget.Widget.extend({...})`。
// 20 删掉了 `web.public.widget` 整套注册表（19 还留着 legacy 层），而这个组件
// 既没有模板也不发 rpc，只是给服务端已经渲染好的 DOM 加监听 —— 所以按 20 的
// 前端事实改成普通 ES 模块，不引入 OWL 组件（`web.assets_frontend` 是
// `type="module"`，执行时 DOM 已解析完，不需要再等 DOMContentLoaded）。
//
// 五档人数原来靠 `.tour_count` 的**位置**去对 `KEYS[i]`，现在改成按输入的
// `name="<档名>_num"` 取档：位置一变就静默算错钱，这种耦合不该留。

const PRICE_KEYS = ['adult', 'child', 'old_man', 'student', 'baby'];

function formatTotal(total) {
    return '¥' + total.toFixed(2);
}

function setupBooking(wrap) {
    const select = wrap.querySelector('#tour_departure_select');
    const totalEl = wrap.querySelector('#tour_total_preview');
    const countEls = [...wrap.querySelectorAll('.tour_count')];
    if (!select || !totalEl) {
        return;
    }
    const refresh = () => {
        const option = select.options[select.selectedIndex];
        let prices = null;
        try {
            prices = JSON.parse(option?.dataset.prices || 'null');
        } catch {
            prices = null;
        }
        if (!prices) {
            totalEl.textContent = '—';
            return;
        }
        let total = 0;
        for (const el of countEls) {
            const key = (el.name || '').replace(/_num$/, '');
            if (!PRICE_KEYS.includes(key)) {
                continue;
            }
            total += (parseInt(el.value, 10) || 0) * (prices[key] || 0);
        }
        totalEl.textContent = formatTotal(total);
    };
    select.addEventListener('change', refresh);
    for (const el of countEls) {
        el.addEventListener('input', refresh);
    }
    refresh();
}

for (const wrap of document.querySelectorAll('#tour_booking_wrap')) {
    setupBooking(wrap);
}
