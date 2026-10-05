(sel) => {
  const e = document.querySelector(sel);
  if (!e) return null;
  const r = e.getBoundingClientRect();
  return {
    x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
    w: Math.round(r.width), h: Math.round(r.height),
  };
}
