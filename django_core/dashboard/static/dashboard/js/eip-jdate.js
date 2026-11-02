/* Jalali date picker (self-hosted, no dependency). Every <input type="date"> keeps its Gregorian ISO value (what the server
   reads); the visible control is three selects (year / month / day) in the Persian calendar. Opt out: data-no-jalali. */
(function () {
  const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
  const fa = n => String(n).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
  function toJalali(gy, gm, gd) {
    const g = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    const gy2 = gm > 2 ? gy + 1 : gy;
    let days = 355666 + 365 * gy + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) + gd + g[gm - 1];
    let jy = -1595 + 33 * Math.floor(days / 12053); days %= 12053;
    jy += 4 * Math.floor(days / 1461); days %= 1461;
    if (days > 365) { jy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
    const jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
    const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
    return [jy, jm, jd];
  }
  function toGregorian(jy, jm, jd) {
    jy += 1595;
    let days = -355668 + 365 * jy + Math.floor(jy / 33) * 8 + Math.floor(((jy % 33) + 3) / 4) + jd + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
    let gy = 400 * Math.floor(days / 146097); days %= 146097;
    if (days > 36524) { gy += 100 * Math.floor(--days / 36524); days %= 36524; if (days >= 365) days++; }
    gy += 4 * Math.floor(days / 1461); days %= 1461;
    if (days > 365) { gy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
    let gd = days + 1;
    const leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
    const m = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let gm = 0;
    while (gm < 13 && gd > m[gm]) gd -= m[gm++];
    return [gy, gm, gd];
  }
  function opt(sel, value, text, chosen) { const o = document.createElement('option'); o.value = value; o.textContent = text; if (chosen) o.selected = true; sel.appendChild(o); }
  function enhance(input) {
    if (input.dataset.noJalali !== undefined || input.dataset.jalaliDone) return;
    input.dataset.jalaliDone = '1';
    const today = new Date();
    const cur = toJalali(today.getFullYear(), today.getMonth() + 1, today.getDate());
    let iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(input.value);
    let sel = iso ? toJalali(+iso[1], +iso[2], +iso[3]) : null;
    const wrap = document.createElement('div'); wrap.className = 'd-flex gap-1'; wrap.dir = 'rtl';
    const y = document.createElement('select'), m = document.createElement('select'), d = document.createElement('select');
    [y, m, d].forEach(s => { s.className = 'form-select'; });
    y.setAttribute('aria-label', 'سال'); m.setAttribute('aria-label', 'ماه'); d.setAttribute('aria-label', 'روز');
    if (!input.required) { opt(y, '', 'سال', !sel); opt(m, '', 'ماه', !sel); opt(d, '', 'روز', !sel); }
    for (let i = cur[0] - 6; i <= cur[0] + 3; i++) opt(y, i, fa(i), sel && sel[0] === i);
    MONTHS.forEach((n, i) => opt(m, i + 1, n, sel && sel[1] === i + 1));
    for (let i = 1; i <= 31; i++) opt(d, i, fa(i), sel && sel[2] === i);
    if (input.required && !sel) { y.value = cur[0]; m.value = cur[1]; d.value = cur[2]; }
    function sync() {
      if (!y.value || !m.value || !d.value) { input.value = ''; return; }
      let day = Math.min(+d.value, +m.value <= 6 ? 31 : +m.value <= 11 ? 30 : 29);
      const g = toGregorian(+y.value, +m.value, day);
      input.value = g[0] + '-' + String(g[1]).padStart(2, '0') + '-' + String(g[2]).padStart(2, '0');
    }
    [y, m, d].forEach(s => s.addEventListener('change', sync));
    wrap.append(d, m, y);
    input.type = 'hidden';
    input.parentNode.insertBefore(wrap, input.nextSibling);
    sync();
  }
  document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('input[type=date]').forEach(enhance));
})();
