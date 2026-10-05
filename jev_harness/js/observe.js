(maxItems) => {
  const SEL = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem],' +
    '[role=checkbox],[role=radio],[role=option],[role=combobox],[contenteditable=""],[contenteditable=true],[onclick]';
  const out = [], seen = new Set();
  for (const el of document.querySelectorAll(SEL)) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width < 6 || r.height < 6 || s.visibility === 'hidden' || s.display === 'none' ||
        Number(s.opacity) === 0) continue;
    if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) continue;
    const cx = Math.min(innerWidth - 1, Math.max(0, r.left + r.width / 2));
    const cy = Math.min(innerHeight - 1, Math.max(0, r.top + r.height / 2));
    const top = document.elementFromPoint(cx, cy);
    if (!top || !(el.contains(top) || top.contains(el))) continue;
    const key = Math.round(cx) + ',' + Math.round(cy);
    if (seen.has(key)) continue;
    seen.add(key);
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    const label = el.labels && el.labels[0] && el.labels[0].innerText;
    const img = el.querySelector('img') && el.querySelector('img').alt;
    const name = (el.getAttribute('aria-label') || label || el.innerText || el.getAttribute('placeholder') ||
      el.title || el.getAttribute('alt') || img || (tag === 'select' ? '' : el.value) || '')
      .replace(/\s+/g, ' ').trim().slice(0, 70);
    const isSel = tag === 'select';
    const selected = isSel ? ((el.options[el.selectedIndex] || {}).text || '').trim().slice(0, 40) : '';
    const typed = type === 'password' ? (el.value ? '(rempli)' : '') : (el.value || '').toString().slice(0, 40);
    out.push({
      tag, type, role: el.getAttribute('role') || '', name, value: isSel ? selected : typed,
      options: isSel ? Array.from(el.options).slice(0, 40).map(o => o.text.trim().slice(0, 40)) : [],
      selIndex: isSel ? Array.from(document.querySelectorAll('select')).indexOf(el) : -1,
      checked: !!el.checked, disabled: !!el.disabled, focused: document.activeElement === el,
      x: Math.round(cx), y: Math.round(cy), w: Math.round(r.width), h: Math.round(r.height),
    });
    if (out.length >= maxItems) break;
  }
  const max = Math.max(0, document.documentElement.scrollHeight - innerHeight);
  return {
    items: out, title: document.title, url: location.href, scrollY: Math.round(scrollY),
    scrollMax: Math.round(max), w: innerWidth, h: innerHeight,
  };
}
