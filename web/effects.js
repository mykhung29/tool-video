// Port of maker/effects.py — keep both in sync so the preview matches the render.
const FX = (() => {
  const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
  const easeOutCubic = p => 1 - (1 - p) ** 3;
  const easeInCubic = p => p ** 3;
  const easeOutBack = (p, s = 1.70158) => { p -= 1; return 1 + (s + 1) * p ** 3 + s * p ** 2; };
  const spring = p => 1 - Math.exp(-6.5 * p) * Math.cos(13.0 * p);
  const bounceOut = p => {
    const n = 7.5625, d = 2.75;
    if (p < 1 / d) return n * p * p;
    if (p < 2 / d) { p -= 1.5 / d; return n * p * p + 0.75; }
    if (p < 2.5 / d) { p -= 2.25 / d; return n * p * p + 0.9375; }
    p -= 2.625 / d; return n * p * p + 0.984375;
  };

  function state(seg, t) {
    const dur = seg.duration;
    const tin = Math.max(seg.in_duration, 0.01);
    const tout = Math.max(seg.out_duration, 0.01);
    let s = 1, o = 1, dx = 0, dy = 0, glow = 0;
    const p = clamp(t / tin);
    switch (seg.effect_in) {
      case 'fade': o = easeOutCubic(p); break;
      case 'pop': s = 0.55 + 0.45 * easeOutBack(p); o = clamp(p * 3); break;
      case 'zoom_in': s = 0.82 + 0.18 * easeOutCubic(p); o = easeOutCubic(p); break;
      case 'slide_up': dy = (1 - easeOutCubic(p)) * 0.35; o = clamp(p * 2); break;
      case 'slide_down': dy = -(1 - easeOutCubic(p)) * 0.35; o = clamp(p * 2); break;
      case 'slide_left': dx = (1 - easeOutCubic(p)); break;
      case 'slide_right': dx = -(1 - easeOutCubic(p)); break;
      case 'bounce': s = Math.max(0.01, spring(p)); o = clamp(p * 4); break;
      case 'drop': dy = -(1 - bounceOut(p)) * 0.4; o = clamp(p * 3); break;
    }
    const after = t - tin;
    if (after > 0) {
      switch (seg.emphasis) {
        case 'pulse': s *= 1 + 0.022 * Math.sin(2 * Math.PI * after / 1.6); break;
        case 'highlight': glow = easeOutCubic(clamp(after / 0.35)) * (0.8 + 0.2 * Math.sin(2 * Math.PI * after / 1.4)); break;
        case 'shake': if (after < 0.45) dx += 0.008 * Math.sin(after * 70) * (1 - after / 0.45); break;
        case 'kenburns': s *= 1 + 0.05 * clamp(after / Math.max(dur - tin, 0.1)); break;
      }
    }
    const q = clamp((t - (dur - tout)) / tout);
    if (q > 0) {
      switch (seg.effect_out) {
        case 'fade': o *= 1 - q; break;
        case 'slide_up': dy -= easeInCubic(q) * 0.4; o *= 1 - q; break;
        case 'slide_left': dx -= easeInCubic(q); break;
        case 'zoom_out': s *= 1 + 0.25 * easeInCubic(q); o *= 1 - q; break;
        case 'pop_out': s *= 1 - 0.6 * easeInCubic(q); o *= 1 - q; break;
        case 'none': if (t >= dur) o = 0; break;
      }
    }
    return { scale: s, opacity: clamp(o), dx, dy, glow };
  }
  // stickers/GIFs: keep in sync with overlay_state / overlay_center in effects.py
  function overlayState(delay, t) {
    const ts = t - delay;
    if (ts < 0) return null;
    const p = clamp(ts / 0.35);
    const s = p < 1 ? Math.max(0.01, easeOutBack(p, 2.2)) : 1;
    const dy = p >= 1 ? 0.004 * Math.sin(2 * Math.PI * (ts - 0.35) / 1.3) : 0;
    return { scale: s, opacity: clamp(p * 3), dy };
  }
  const CORNERS = { top_right: [1, -1], top_left: [-1, -1], bottom_right: [1, 1], bottom_left: [-1, 1] };
  function overlayCenter(pos, cx, cy, bw, bh, w, h) {
    if (pos === 'above') return [cx, cy - bh / 2 - h * 0.45];
    if (pos === 'below') return [cx, cy + bh / 2 + h * 0.45];
    const [sx, sy] = CORNERS[pos] || [1, -1];
    return [cx + sx * (bw / 2 - 0.15 * w), cy + sy * bh / 2];
  }
  // video effect clip: keep in sync with vfx_state in effects.py
  function vfxState(t, dur) {
    const p = clamp(t / 0.25);
    const q = clamp((t - (dur - 0.15)) / 0.15);
    return { scale: 0.85 + 0.15 * easeOutBack(p), opacity: clamp(p * 2) * (1 - q) };
  }
  return { state, overlayState, overlayCenter, vfxState };
})();
