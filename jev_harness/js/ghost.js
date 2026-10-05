([x, y]) => {
  let c = document.getElementById('__jev_cursor');
  if (!c) {
    c = document.createElement('div');
    c.id = '__jev_cursor';
    c.style.cssText = 'position:fixed;z-index:2147483647;width:16px;height:16px;margin:-8px 0 0 -8px;' +
      'border-radius:50%;background:#7aa2ff;border:2px solid #fff;box-shadow:0 0 0 3px #7aa2ff66;' +
      'pointer-events:none;transition:none';
    document.documentElement.appendChild(c);
  }
  c.style.left = x + 'px';
  c.style.top = y + 'px';
}
