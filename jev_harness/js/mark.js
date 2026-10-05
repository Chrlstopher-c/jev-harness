([x, y, w, h]) => {
  const d = document.createElement('div');
  d.style.cssText = `position:fixed;z-index:2147483646;left:${x - w / 2 - 4}px;top:${y - h / 2 - 4}px;` +
    `width:${w + 8}px;height:${h + 8}px;border:3px solid #ff5d5d;border-radius:6px;pointer-events:none;` +
    'box-shadow:0 0 12px #ff5d5d99';
  document.documentElement.appendChild(d);
  setTimeout(() => d.remove(), 900);
}
