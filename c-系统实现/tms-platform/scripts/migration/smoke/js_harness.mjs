// 无浏览器情况下验证重写后的预订 JS 的**计算与接线**（不是"语法能过"，node --check 只能证明那个）。
// 桩件只实现文件真正用到的那几样 DOM API。
import fs from 'node:fs';
import vm from 'node:vm';

const src = fs.readFileSync('/tmp/b0/b1addons/tour_website_sale/static/src/js/tour_website_sale.js', 'utf8');

function el(props = {}) {
  const listeners = {};
  return {
    name: props.name ?? '',
    value: props.value ?? '',
    textContent: '',
    dataset: props.dataset ?? {},
    listeners,
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
    fire(type) { for (const fn of listeners[type] || []) fn(); },
    _opts: props.options ?? null,
  };
}

function wrapOf(deps) {
  const totalEl = el();
  const select = el();
  select.options = deps.options.map(o => o);
  select.selectedIndex = deps.selectedIndex ?? 0;
  const counts = deps.counts.map(c => el(c));
  return {
    totalEl, select, counts,
    querySelector(sel) {
      if (sel === '#tour_departure_select') return select;
      if (sel === '#tour_total_preview') return totalEl;
      return null;
    },
    querySelectorAll(sel) { return sel === '.tour_count' ? counts : []; },
  };
}

const OPT = (prices) => ({ dataset: prices === null ? {} : { prices: JSON.stringify(prices) } });
const PRICES = { adult: 1200, child: 550, old_man: 720, student: 640, baby: 120 };

function run(wrap) {
  const sandbox = { document: { querySelectorAll: () => [wrap] } };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return wrap;
}

let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log('%s  %s  got=%s want=%s', ok ? 'PASS' : 'FAIL', label.padEnd(40), JSON.stringify(got), JSON.stringify(want));
}

// 1) 初始渲染就有一次合计（模板默认成人 1）
let w = run(wrapOf({ options: [OPT(PRICES)], counts: [
  { name: 'adult_num', value: '2' }, { name: 'child_num', value: '1' },
  { name: 'old_man_num', value: '0' }, { name: 'student_num', value: '0' },
  { name: 'baby_num', value: '3' }] }));
check('初次 refresh（2成人+1儿童+3婴儿）', w.totalEl.textContent, '¥' + (2 * 1200 + 550 + 3 * 120).toFixed(2));

// 2) 改人数 → input 监听真的接上了
w.counts[0].value = '3';
w.counts[0].fire('input');
check('改 input 后重算（3 成人）', w.totalEl.textContent, '¥' + (3 * 1200 + 550 + 360).toFixed(2));

// 3) 换班期 → change 监听真的接上了
w.select.options.push(OPT({ ...PRICES, adult: 100 }));
w.select.selectedIndex = 1;
w.select.fire('change');
check('切班期后重算（成人单价 100）', w.totalEl.textContent, '¥' + (3 * 100 + 550 + 360).toFixed(2));

// 4) 档位靠 name 而非位置：乱序 + 一个不认识的 name + 非数字
w = run(wrapOf({ options: [OPT(PRICES)], counts: [
  { name: 'baby_num', value: '1' }, { name: 'dog_num', value: '9' },
  { name: 'adult_num', value: 'abc' }, { name: 'student_num', value: '2' }] }));
check('乱序/未知档/非数字', w.totalEl.textContent, '¥' + (120 + 0 + 2 * 640).toFixed(2));

// 5) 首个 option 是「请选择」没有 data-prices → 不报错，显示占位
w = run(wrapOf({ options: [OPT(null), OPT(PRICES)], selectedIndex: 0,
  counts: [{ name: 'adult_num', value: '1' }] }));
check('未选班期时是占位而非 NaN', w.totalEl.textContent, '—');

// 6) 坏 JSON 不抛
w = run(wrapOf({ options: [{ dataset: { prices: '{bad' } }], counts: [{ name: 'adult_num', value: '1' }] }));
check('data-prices 坏 JSON', w.totalEl.textContent, '—');

// 7) 缺 select/total 元素时静默返回（模板 t-if 不成立时 DOM 不完整）
w = wrapOf({ options: [OPT(PRICES)], counts: [] });
w.querySelector = () => null;
w.querySelectorAll = () => [];
try { run(w); check('缺元素不抛', 'ok', 'ok'); } catch (e) { check('缺元素不抛', String(e), 'ok'); }

console.log(fails ? `\nFAIL ${fails}` : '\nALL PASS');
process.exit(fails ? 1 : 0);
