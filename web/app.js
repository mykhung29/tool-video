'use strict';

// ---------------------------------------------------------------- helpers
const $ = sel => document.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) e.append(kid);
  return e;
};
const enc = encodeURIComponent;
const fmt = (s, d = 1) => (Number(s) || 0).toFixed(d);

async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers: {} };
  if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json'; }
  const res = await fetch(path, init);
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) throw new Error((data && data.detail) || `Lỗi ${res.status}`);
  return data;
}

function toast(msg, type = 'info', ms = 4500) {
  const t = el('div', { class: `toast ${type}` }, msg);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), type === 'error' ? Math.max(ms, 9000) : ms);
}
const fail = e => toast(e.message || String(e), 'error');

function debounce(fn, ms) {
  let h;
  const d = (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
  d.flush = (...a) => { clearTimeout(h); return fn(...a); };
  d.cancel = () => clearTimeout(h);
  return d;
}

// ---------------------------------------------------------------- state
const S = {
  settings: null,
  meta: null,
  contents: [],
  selected: new Set(),
  queue: { jobs: [] },
  ed: null,   // editor state
};

const STATUS = {
  new: 'Chưa dựng', queued: 'Đang chờ', rendering: 'Đang dựng', done: 'Đã dựng',
  error: 'Lỗi', missing: 'Đã dựng (không thấy file)',
};

// Field schema shared by the settings page (defaults) and the editor (per content).
// `stale` means changing it alters timing/audio so the preview must be rebuilt.
const FIELDS = [
  { group: 'Giọng đọc', items: [
    { k: 'voice', t: 'select', label: 'Giọng đọc', opts: () => voiceOpts(), stale: 1 },
    { k: 'rate', t: 'range', label: 'Tốc độ', min: -50, max: 100, step: 5, unit: '%', stale: 1 },
    { k: 'pitch', t: 'range', label: 'Cao độ', min: -50, max: 50, step: 1, unit: 'Hz', stale: 1 },
    { k: 'pause', t: 'range', label: 'Nghỉ sau mỗi câu', min: 0, max: 3, step: 0.1, unit: 's', stale: 1 },
    { k: 'voice_delay', t: 'range', label: 'Trễ trước khi đọc', min: 0, max: 1.5, step: 0.05, unit: 's', stale: 1 },
    { k: 'min_duration', t: 'range', label: 'Ảnh không đọc', min: 0.5, max: 10, step: 0.1, unit: 's', stale: 1 },
  ] },
  { group: 'Hiệu ứng', items: [
    { k: 'effect_in', t: 'select', label: 'Xuất hiện', opts: () => Object.entries(S.meta.effects_in) },
    { k: 'effect_out', t: 'select', label: 'Biến mất', opts: () => Object.entries(S.meta.effects_out) },
    { k: 'emphasis', t: 'select', label: 'Nhấn mạnh', opts: () => Object.entries(S.meta.emphasis) },
    { k: 'in_duration', t: 'range', label: 'Thời gian vào', min: 0.1, max: 1.5, step: 0.05, unit: 's', stale: 1 },
    { k: 'out_duration', t: 'range', label: 'Thời gian ra', min: 0.05, max: 1.5, step: 0.05, unit: 's', stale: 1 },
  ] },
  { group: 'Hiệu ứng âm thanh', items: [
    { k: 'sfx_end', t: 'select', label: 'Sau khi đọc xong', opts: () => sfxOpts(), stale: 1 },
    { k: 'sfx_end_gap', t: 'range', label: 'Chờ trước âm sau khi đọc', min: -0.5, max: 1.5, step: 0.05, unit: 's', stale: 1 },
    { k: 'sfx_start', t: 'select', label: 'Lúc ảnh xuất hiện', stale: 1,
      opts: () => [['first', 'Chỉ bình luận đầu tiên'], ['all', 'Mọi bình luận'], ['none', 'Không phát']] },
    { k: 'sfx', t: 'select', label: 'Âm lúc xuất hiện', opts: () => sfxOpts(), stale: 1 },
  ] },
  { group: 'Sticker & GIF', items: [
    { k: 'sticker', t: 'select', label: 'Sticker', opts: () => overlayOpts('sticker'), stale: 1 },
    { k: 'sticker_pos', t: 'select', label: 'Vị trí sticker', opts: () => Object.entries(S.meta.overlay_pos) },
    { k: 'sticker_size', t: 'range', label: 'Cỡ sticker', min: 0.05, max: 0.4, step: 0.01, pct: 1 },
    { k: 'gif', t: 'select', label: 'GIF', opts: () => overlayOpts('gif'), stale: 1 },
    { k: 'gif_pos', t: 'select', label: 'Vị trí GIF', opts: () => Object.entries(S.meta.overlay_pos) },
    { k: 'gif_size', t: 'range', label: 'Cỡ GIF', min: 0.15, max: 0.9, step: 0.01, pct: 1 },
    { k: 'overlay_hold', t: 'range', label: 'Giữ GIF/sticker rồi mới qua bình luận sau', min: 0, max: 3, step: 0.1, unit: 's', stale: 1 },
  ] },
  { group: 'Video effect', items: [
    { k: 'vfx', t: 'select', label: 'Clip sau khi đọc', opts: () => overlayOpts('vfx'), stale: 1 },
    { k: 'vfx_max', t: 'range', label: 'Dài tối đa (0 = cả clip)', min: 0, max: 10, step: 0.5, unit: 's', stale: 1 },
    { k: 'vfx_size', t: 'range', label: 'Cỡ clip', min: 0.2, max: 1, step: 0.01, pct: 1 },
    { k: 'vfx_x', t: 'range', label: 'Vị trí ngang', min: 0, max: 1, step: 0.01, pct: 1 },
    { k: 'vfx_y', t: 'range', label: 'Vị trí dọc', min: 0, max: 1, step: 0.01, pct: 1 },
    { k: 'vfx_volume', t: 'range', label: 'Âm lượng clip', min: 0, max: 200, step: 5, unit: '%', stale: 1 },
  ] },
  { group: 'Bố cục ảnh', items: [
    { k: 'scale', t: 'range', label: 'Độ rộng ảnh', min: 0.3, max: 1, step: 0.01, pct: 1 },
    { k: 'pos_x', t: 'range', label: 'Vị trí ngang', min: 0, max: 1, step: 0.01, pct: 1 },
    { k: 'pos_y', t: 'range', label: 'Vị trí dọc', min: 0, max: 1, step: 0.01, pct: 1 },
    { k: 'max_height', t: 'range', label: 'Cao tối đa', min: 0.2, max: 1, step: 0.01, pct: 1 },
    { k: 'shadow', t: 'check', label: 'Đổ bóng' },
  ] },
  { group: 'Âm thanh', items: [
    { k: 'voice_on', t: 'check', label: 'Giọng đọc', stale: 1 },
    { k: 'voice_volume', t: 'range', label: 'Âm lượng giọng', min: 0, max: 200, step: 5, unit: '%', stale: 1 },
    { k: 'sfx_on', t: 'check', label: 'Hiệu ứng âm', stale: 1 },
    { k: 'sfx_volume', t: 'range', label: 'Âm lượng SFX', min: 0, max: 150, step: 5, unit: '%', stale: 1 },
    { k: 'music_on', t: 'check', label: 'Sound background', stale: 1 },
    { k: 'music', t: 'select', label: 'File nhạc nền', opts: () => [['random', '🎲 Ngẫu nhiên'], ['none', 'Không dùng'], ...S.meta.music.map(m => [m, m])], stale: 1 },
    { k: 'music_volume', t: 'range', label: 'Nhạc so với giọng', min: 0, max: 80, step: 5, unit: '%', stale: 1 },
    { k: 'ducking', t: 'check', label: 'Giảm nhạc khi đọc', stale: 1 },
    { k: 'duck_level', t: 'range', label: 'Mức nhạc khi đọc', min: 0, max: 100, step: 5, unit: '%', stale: 1 },
    { k: 'bg_audio_on', t: 'check', label: 'Tiếng video nền', stale: 1 },
    { k: 'bg_volume', t: 'range', label: 'Âm lượng nền', min: 0, max: 100, step: 5, unit: '%', stale: 1 },
    { k: 'end_padding', t: 'range', label: 'Đệm cuối video', min: 0, max: 3, step: 0.1, unit: 's', stale: 1 },
  ] },
];
// Vietnamese voices first, then multilingual voices (which can also read Vietnamese).
function voiceRank(v) { return v.locale.startsWith('vi') ? 0 : /Multilingual/.test(v.id) ? 1 : 2; }
function voiceOpts(all = true) {
  const groups = ['Tiếng Việt', 'Đa ngôn ngữ (đọc được tiếng Việt)', 'Ngôn ngữ khác'];
  return S.meta.voices.filter(v => all || voiceRank(v) < 2)
    .sort((a, b) => voiceRank(a) - voiceRank(b))
    .map(v => [v.id, v.label, groups[voiceRank(v)]]);
}
const voiceLabel = id => (S.meta.voices.find(v => v.id === id) || { label: id }).label;
function sfxOpts() {
  return [['random', '🎲 Ngẫu nhiên từ SoundEffects'], ['none', 'Không'], ...S.meta.sfx.map(x => [x.id, x.label])];
}
const overlayFiles = kind => (kind === 'gif' ? S.meta.gifs : kind === 'vfx' ? S.meta.vfx.map(v => v.name) : S.meta.stickers);
const vfxLen = name => (S.meta.vfx.find(v => v.name === name) || {}).duration || 0;
function overlayOpts(kind) {
  return [['none', 'Không dùng'], ['random', '🎲 Ngẫu nhiên'], ...overlayFiles(kind).map(n => [n, n])];
}
const isStale = (f, v) => !!(f.stale || (f.staleIf && f.staleIf(v)));

// <option>s, grouped into <optgroup> when entries carry a third (group) element
function optionEls(list) {
  const out = [];
  let grp = null;
  for (const [v, l, g] of list) {
    const o = el('option', { value: v }, l);
    if (!g) { out.push(o); continue; }
    if (!grp || grp.label !== g) { grp = el('optgroup', { label: g }); out.push(grp); }
    grp.append(o);
  }
  return out;
}

const FIELD = Object.fromEntries(FIELDS.flatMap(g => g.items).map(f => [f.k, f]));

function fieldValueLabel(f, v) {
  if (f.pct) return `${Math.round(v * 100)}%`;
  if (f.unit === 's') return `${fmt(v, 2).replace(/0$/, '')}s`;
  return `${v}${f.unit || ''}`;
}

function makeControl(f, value, onChange) {
  if (f.t === 'select') {
    const s = el('select', { onchange: () => onChange(s.value) }, optionEls(f.opts()));
    if (![...s.options].some(o => o.value === String(value))) s.append(el('option', { value }, String(value)));
    s.value = value;
    return s;
  }
  if (f.t === 'check') {
    const c = el('input', { type: 'checkbox', onchange: () => onChange(c.checked) });
    c.checked = !!value;
    return c;
  }
  const val = el('span', { class: 'val' }, fieldValueLabel(f, value));
  const r = el('input', { type: 'range', min: f.min, max: f.max, step: f.step, value });
  r.addEventListener('input', () => { val.textContent = fieldValueLabel(f, +r.value); onChange(+r.value, true); });
  r.addEventListener('change', () => onChange(+r.value, false));
  return [r, val];
}

// Render grouped fields. overrides: object of keys set explicitly (null on the settings page).
function renderFields(container, values, overrides, onChange, onResetGroup) {
  container.innerHTML = '';
  for (const g of FIELDS) {
    const head = el('h4', {}, g.group);
    if (onResetGroup && g.items.some(f => f.k in overrides))
      head.append(el('button', { class: 'icon', title: 'Dùng giá trị mặc định', onclick: () => onResetGroup(g) }, '↺ mặc định'));
    const grp = el('div', { class: 'group' }, head);
    for (const f of g.items) {
      const row = el('div', { class: 'field' + (overrides && f.k in overrides ? ' overridden' : '') },
        el('label', {}, f.label), el('div', { class: 'ctl' }, makeControl(f, values[f.k], (v, live) => onChange(f, v, live))));
      grp.append(row);
    }
    container.append(grp);
  }
}

// ---------------------------------------------------------------- tabs
function showTab(name) {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === `tab-${name}`));
  if (name === 'contents') loadContents();
  if (name === 'settings') renderSettings();
  if (name !== 'editor') pausePreview();
  else if (S.ed) resizeStage();
}
document.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));

// ---------------------------------------------------------------- contents tab
async function loadContents(quiet = false) {
  try {
    S.contents = await api('/api/contents');
    $('#contentsEmpty').classList.add('hidden');
  } catch (e) {
    S.contents = [];
    $('#contentsEmpty').textContent = e.message + ' — kiểm tra đường dẫn trong tab Cài đặt.';
    $('#contentsEmpty').classList.remove('hidden');
    if (!quiet) fail(e);
  }
  const names = new Set(S.contents.map(c => c.name));
  for (const n of [...S.selected]) if (!names.has(n)) S.selected.delete(n);
  renderContents();
}

function bgLabel(c) {
  if (c.background) return el('span', {}, '📌 ', c.background);
  return el('span', { class: 'muted' }, 'Ngẫu nhiên', c.last_background ? ` (lần trước: ${c.last_background})` : '');
}

function renderContents() {
  const filter = $('#filterStatus').value;
  const rows = S.contents.filter(c => !filter || c.status === filter || (filter === 'done' && c.status === 'missing'));
  const tbody = $('#contentRows');
  tbody.innerHTML = '';
  const jobsByName = {};
  for (const j of S.queue.jobs) if (!j.preview && ['pending', 'running'].includes(j.status)) jobsByName[j.name] = j;
  for (const c of rows) {
    const cb = el('input', { type: 'checkbox', onchange: () => { cb.checked ? S.selected.add(c.name) : S.selected.delete(c.name); renderContents(); } });
    cb.checked = S.selected.has(c.name);
    const job = jobsByName[c.name];
    const status = job ? (job.status === 'running' ? 'rendering' : 'queued') : c.status;
    const stCell = el('td', {}, el('span', { class: `pill ${status}` },
      STATUS[status] || status, job && job.status === 'running' ? ` ${Math.round(job.progress * 100)}%` : ''));
    if (c.status === 'error' && c.error && !job) stCell.append(el('div', { class: 'err-text' }, c.error));
    tbody.append(el('tr', { class: S.selected.has(c.name) ? 'selected' : '' },
      el('td', {}, cb),
      el('td', {}, el('span', { class: 'cname', onclick: () => openEditor(c.name) }, c.name)),
      el('td', {}, `${c.image_count} ảnh`, el('div', { class: 'muted small' }, c.has_project ? `${c.voiced_count} có lời đọc` : 'chưa biên tập')),
      el('td', { class: 'small' }, bgLabel(c)),
      stCell,
      el('td', {}, el('div', { class: 'actions' },
        el('button', { class: 'small-btn', onclick: () => openEditor(c.name) }, 'Biên tập'),
        c.output && c.status === 'done' ? el('button', { class: 'small-btn ghost', onclick: () => window.open(`/media/output?path=${enc(c.output)}`) }, 'Xem') : null,
        c.output && c.status === 'done' ? el('button', { class: 'small-btn ghost', title: 'Mở trong thư mục', onclick: () => openPath(c.output, true) }, '📁') : null,
      )),
    ));
  }
  if (!S.contents.length && $('#contentsEmpty').classList.contains('hidden')) {
    $('#contentsEmpty').innerHTML = `Chưa có content nào. Tạo các thư mục con chứa ảnh bình luận trong <code>${S.settings?.contents_dir || 'Contents'}</code> rồi bấm Làm mới.`;
    $('#contentsEmpty').classList.remove('hidden');
  }
  $('#checkAll').checked = rows.length > 0 && rows.every(c => S.selected.has(c.name));
  const n = S.selected.size;
  $('#btnRender').disabled = n === 0;
  $('#btnRender').textContent = n ? `Tạo video (${n})` : 'Tạo video';
  $('#contentsPath').textContent = S.settings ? `Contents: ${S.settings.contents_dir}  •  ${S.contents.length} content` : '';
}

$('#btnRefresh').onclick = () => loadContents();
$('#filterStatus').onchange = renderContents;
$('#btnSelectAll').onclick = () => { S.contents.forEach(c => S.selected.add(c.name)); renderContents(); };
$('#btnSelectNone').onclick = () => { S.selected.clear(); renderContents(); };
$('#checkAll').onchange = e => { (e.target.checked ? $('#btnSelectAll') : $('#btnSelectNone')).click(); };
$('#btnRender').onclick = async () => {
  const names = S.contents.map(c => c.name).filter(n => S.selected.has(n));
  try {
    const r = await api('/api/queue/add', { body: { names } });
    toast(r.added.length ? `Đã thêm ${r.added.length} video vào hàng đợi.` : 'Các content này đã có trong hàng đợi.', 'ok');
    pollQueue();
  } catch (e) { fail(e); }
};
$('#btnRetryErrors').onclick = async () => {
  try {
    const r = await api('/api/queue/retry_errors', { body: {} });
    toast(r.added.length ? `Đưa ${r.added.length} video lỗi vào hàng đợi.` : 'Không có video lỗi.', 'ok');
    pollQueue();
  } catch (e) { fail(e); }
};
async function openPath(path, select = false) {
  try { await api('/api/open', { body: { path, select } }); } catch (e) { fail(e); }
}
$('#btnOpenContents').onclick = () => openPath(S.settings.contents_dir);
$('#btnOpenOutput').onclick = $('#btnOpenOutput2').onclick = () => openPath(S.settings.output_dir);

// ---------------------------------------------------------------- queue
let lastQueueSig = '';
async function pollQueue() {
  try { S.queue = await api('/api/queue'); } catch (_) { return; }
  const q = S.queue;
  const active = (q.counts.pending || 0) + (q.counts.running || 0);
  const badge = $('#queueBadge');
  badge.textContent = active;
  badge.classList.toggle('hidden', !active);
  const mini = $('#queueMini');
  mini.classList.toggle('hidden', !active);
  if (active) {
    mini.querySelector('i').style.width = `${q.overall * 100}%`;
    mini.querySelector('span').textContent = q.paused ? 'Đã dừng' : `${q.counts.done || 0}/${q.jobs.length} video`;
  }
  renderQueue();
  // refresh the content list whenever a job changes state
  const sig = q.jobs.map(j => j.id + j.status).join();
  if (sig !== lastQueueSig) {
    for (const j of q.jobs) {
      const prev = lastQueueSig.includes(j.id) && !lastQueueSig.includes(j.id + j.status);
      if (prev && j.status === 'done') toast(`✔ Hoàn thành: ${j.name}${j.preview ? ' (preview)' : ''}`, 'ok');
      if (prev && j.status === 'error') toast(`✖ ${j.name}: ${j.error}`, 'error');
      if (prev && j.status === 'done' && j.preview) window.open(`/media/output?path=${enc(j.output)}`);
    }
    lastQueueSig = sig;
    if ($('#tab-contents').classList.contains('active')) loadContents(true);
  } else if ($('#tab-contents').classList.contains('active') && active) {
    renderContents();
  }
}

function renderQueue() {
  const q = S.queue;
  const list = $('#jobList');
  list.innerHTML = '';
  const c = q.counts || {};
  $('#overallBar').style.width = `${(q.overall || 0) * 100}%`;
  $('#overallText').textContent = q.jobs.length
    ? `${c.done || 0} hoàn thành • ${c.error || 0} lỗi • ${c.running || 0} đang dựng • ${c.pending || 0} đang chờ${q.paused ? ' • HÀNG ĐỢI ĐANG DỪNG' : ''}`
    : 'Hàng đợi trống. Chọn content ở tab Content rồi bấm “Tạo video”.';
  $('#btnStop').disabled = q.paused || !(c.running || c.pending);
  $('#btnResume').disabled = !q.paused;
  const label = { pending: 'Đang chờ', running: 'Đang dựng', done: 'Hoàn thành', error: 'Lỗi', cancelled: 'Đã huỷ' };
  for (const j of q.jobs) {
    const msg = j.status === 'error' ? j.error : j.status === 'done' ? j.output : j.message;
    list.append(el('div', { class: `job ${j.status}` },
      el('div', {}, el('div', { class: 'jname' }, j.name, j.preview ? el('span', { class: 'muted small' }, '  • preview nhanh') : ''),
        el('div', { class: 'jmsg' }, `${label[j.status] || j.status}${msg ? ' — ' + msg : ''}`)),
      el('div', {}, el('div', { class: 'bar' }, el('i', { style: `width:${(j.status === 'done' ? 1 : j.progress) * 100}%` })),
        el('div', { class: 'muted small' }, j.status === 'running' ? `${Math.round(j.progress * 100)}%` : '')),
      el('div', { class: 'actions' },
        j.status === 'done' ? el('button', { class: 'small-btn', onclick: () => window.open(`/media/output?path=${enc(j.output)}`) }, 'Xem') : null,
        j.status === 'done' && !j.preview ? el('button', { class: 'small-btn ghost', onclick: () => openPath(j.output, true) }, '📁') : null,
        ['pending', 'running'].includes(j.status) ? el('button', { class: 'small-btn ghost', onclick: () => api(`/api/queue/${j.id}`, { method: 'DELETE' }).then(pollQueue, fail) }, 'Bỏ') : null,
      )));
  }
}
$('#btnStop').onclick = () => api('/api/queue/stop', { body: {} }).then(pollQueue, fail);
$('#btnResume').onclick = () => api('/api/queue/resume', { body: {} }).then(pollQueue, fail);
$('#btnRetry').onclick = () => api('/api/queue/retry', { body: {} }).then(r => { toast(`Dựng lại ${r.retried} video.`); pollQueue(); }, fail);
$('#btnClear').onclick = () => api('/api/queue/clear', { body: {} }).then(pollQueue, fail);

// ---------------------------------------------------------------- editor
const stage = $('#stage');
const ctx = stage.getContext('2d');
const pAudio = $('#previewAudio');
const bgVideo = $('#bgVideo');
const imgCache = new Map();

function loadImg(name, file) {
  const key = `${name}/${file}`;
  if (!imgCache.has(key)) {
    const im = new Image();
    im.onload = () => drawFrame();
    im.src = `/media/content/${enc(name)}/${enc(file)}`;
    imgCache.set(key, im);
  }
  return imgCache.get(key);
}

// Stickers and GIFs. Animated files are decoded frame by frame (WebCodecs ImageDecoder)
// so the preview shows the frame the renderer will use at that moment.
const spriteCache = new Map();
function getSprite(kind, file) {
  const key = `${kind}:${file}`;
  if (spriteCache.has(key)) return spriteCache.get(key);
  const url = `/media/${kind}/${enc(file)}`;
  const sp = { ready: false, w: 0, h: 0, img: null, frames: null, total: 0 };
  spriteCache.set(key, sp);
  const im = new Image();
  im.onload = () => { Object.assign(sp, { img: im, w: im.naturalWidth, h: im.naturalHeight, ready: true }); drawFrame(); };
  im.src = url;
  if (/\.(gif|webp)$/i.test(file) && 'ImageDecoder' in window) decodeFrames(url, sp);
  return sp;
}

async function decodeFrames(url, sp) {
  try {
    const res = await fetch(url);
    const type = res.headers.get('content-type') || 'image/gif';
    const dec = new ImageDecoder({ data: await res.arrayBuffer(), type });
    await dec.tracks.ready;
    const n = Math.min(dec.tracks.selectedTrack.frameCount, 400);
    if (n < 2) return;
    const frames = [];
    let t = 0;
    for (let i = 0; i < n; i++) {
      const { image } = await dec.decode({ frameIndex: i });
      frames.push({ start: t, bmp: await createImageBitmap(image) });
      t += Math.max(0.02, (image.duration || 100000) / 1e6);
      image.close();
    }
    Object.assign(sp, { frames, total: t });
    drawFrame();
  } catch (_) { /* keep the plain <img>; the browser animates it on its own clock */ }
}

function spriteFrame(sp, t) {
  if (!sp.frames) return sp.img;
  const tt = ((t % sp.total) + sp.total) % sp.total;
  let k = 0;
  while (k + 1 < sp.frames.length && sp.frames[k + 1].start <= tt) k++;
  return sp.frames[k].bmp;
}

const effective = () => ({ ...S.settings.defaults, ...(S.ed.project.settings || {}) });

async function openEditor(name) {
  pausePreview();
  try {
    const r = await api(`/api/contents/${enc(name)}`);
    S.ed = { name, project: r.project, timeline: null, stale: true, current: 0, playing: false, mode: 'comment' };
  } catch (e) { return fail(e); }
  $('#editorEmpty').classList.add('hidden');
  $('#editor').classList.remove('hidden');
  showTab('editor');
  renderEditor();
  if (S.settings.auto_ocr) await readTexts();   // fill empty comments from their images first
  if (S.ed?.name === name) buildTimeline();
}

// OCR: read comment text from the images. Without `indices` it fills every comment that has
// no text yet and was never read; with `indices` it re-reads those comments (overwriting).
async function readTexts(indices = null) {
  const ed = S.ed;
  const imgs = ed.project.images;
  const todo = indices ?? imgs.map((img, i) => i).filter(i => !imgs[i].text.trim() && !imgs[i].skip && !imgs[i].ocr);
  if (!todo.length) return;
  if (ed.ocrBusy) return toast('Đang đọc chữ, đợi xong rồi thử lại.');
  ed.ocrBusy = true;
  const errors = [];
  try {
    for (let k = 0; k < todo.length; k++) {
      const i = todo[k];
      const img = imgs[i];
      setPreviewStatus(`🔤 Đang đọc chữ từ ảnh ${k + 1}/${todo.length}…${S.ocrWarm ? '' : ' (lần đầu sẽ lâu hơn để nạp model)'}`);
      const card = document.querySelectorAll('#imageList .img-card')[i];
      card?.classList.add('ocr-busy');
      try {
        const r = await api(`/api/contents/${enc(ed.name)}/ocr`, { body: { file: img.file } });
        S.ocrWarm = true;
        if (S.ed !== ed) return;
        img.text = r.text;
        img.ocr = true;
        syncCardText(imgs.indexOf(img));
        syncPanelText(imgs.indexOf(img));
        if (!r.text) errors.push(`${img.file}: không thấy chữ`);
      } catch (e) {
        errors.push(`${img.file}: ${e.message}`);
      } finally {
        card?.classList.remove('ocr-busy');
      }
    }
  } finally {
    ed.ocrBusy = false;
  }
  await save.flush();
  if (S.ed === ed && ed.mode === 'comment') renderCommentPanel();
  if (errors.length) toast('Đọc chữ chưa được:\n' + errors.join('\n'), 'error');
  else toast(`Đã đọc chữ ${todo.length} ảnh — kiểm tra lại nội dung nếu cần.`, 'ok');
  if (S.ed === ed && ed.timeline) markStale();
}

function renderEditor() {
  const ed = S.ed;
  const p = ed.project;
  $('#edName').textContent = ed.name;
  const total = ed.timeline ? ` • ${fmt(ed.timeline.total)}s` : '';
  $('#edInfo').textContent = `${p.images.length} ảnh${total}`;
  renderImageList();
  renderEdSettings();
  renderBgSelect();
  setMode(ed.mode);
}

function segFor(file) {
  return S.ed.timeline ? S.ed.timeline.segments.find(s => s.file === file) : null;
}

// short labels for what a comment changes compared with the video settings
function overrideBadges(img) {
  const ov = img.overrides;
  const name = v => (v === 'none' ? 'không' : v === 'random' ? 'ngẫu nhiên' : v);
  const b = [];
  if (ov.voice) b.push('🎙 ' + voiceLabel(ov.voice).split(' (')[0]);
  if (ov.sfx_end) b.push('🔊 ' + name(ov.sfx_end));
  if (ov.sfx) b.push('🔔 ' + name(ov.sfx));
  if (ov.sticker) b.push('😀 ' + name(ov.sticker));
  if (ov.gif) b.push('🎞 ' + name(ov.gif));
  if (ov.vfx) b.push('🎬 ' + name(ov.vfx));
  const rest = Object.keys(ov).filter(k => !['voice', 'sfx_end', 'sfx', 'sticker', 'gif', 'vfx'].includes(k)).length;
  if (rest) b.push(`⚙ ${rest} chỉnh khác`);
  return b;
}

function renderImageList() {
  const ed = S.ed;
  const list = $('#imageList');
  list.innerHTML = '';
  ed.project.images.forEach((img, i) => {
    const seg = segFor(img.file);
    const ta = el('textarea', { placeholder: 'Nội dung bình luận cần đọc (để trống = không đọc)', rows: 3 });
    ta.value = img.text;
    ta.addEventListener('input', () => { img.text = ta.value; markStale(); save(); syncPanelText(i); });
    const skip = el('input', { type: 'checkbox', onchange: () => { img.skip = skip.checked; card.classList.toggle('skipped', img.skip); markStale(); save(); if (ed.current === i) renderCommentPanel(); } });
    skip.checked = img.skip;
    const badges = overrideBadges(img);
    const card = el('div', { class: `img-card${img.skip ? ' skipped' : ''}${ed.current === i ? ' current' : ''}`, draggable: 'true' },
      el('img', { class: 'thumb', src: `/media/content/${enc(ed.name)}/${enc(img.file)}`, title: 'Chỉnh bình luận này' }),
      el('div', { class: 'img-meta' },
        el('div', { class: 'img-top' },
          el('span', { class: 'drag-handle', title: 'Kéo để đổi thứ tự' }, '⋮⋮'),
          el('span', { class: 'fname' }, `${i + 1}. ${img.file}`),
          el('span', { class: 'dur-chip' }, seg ? `${fmt(seg.duration)}s` : ''),
          el('button', { class: 'icon', title: 'Lên', disabled: i === 0, onclick: () => moveImage(i, i - 1) }, '▲'),
          el('button', { class: 'icon', title: 'Xuống', disabled: i === ed.project.images.length - 1, onclick: () => moveImage(i, i + 1) }, '▼'),
        ),
        ta,
        badges.length ? el('div', { class: 'badges' }, badges.map(b => el('span', { class: 'badge-o' }, b))) : null,
        el('div', { class: 'img-top' },
          el('label', { class: 'row gap muted' }, skip, 'Không đọc'),
          el('span', { class: 'spacer' }),
          el('button', { class: 'small-btn ghost', title: 'Đọc lại chữ từ ảnh (thay nội dung hiện tại)', onclick: () => readTexts([i]) }, '🔤 Đọc chữ'),
          el('button', { class: 'small-btn ghost', onclick: () => testVoice(img.text, img.overrides.voice) }, '🔊 Nghe'),
          el('button', { class: 'small-btn ghost', onclick: () => playSegment(i) }, '▶ Xem'),
          el('button', { class: 'small-btn edit-btn' + (ed.current === i ? ' primary' : ' ghost'), onclick: () => selectComment(i) }, '✎ Chỉnh riêng'),
        ),
      ),
    );
    // clicking anywhere on the card (except its controls) opens this comment's editor
    card.addEventListener('click', e => { if (!e.target.closest('button, textarea, input, label, select')) selectComment(i); });
    card.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', String(i)); card.classList.add('dragging'); });
    card.addEventListener('dragend', () => card.classList.remove('dragging'));
    card.addEventListener('dragover', e => { e.preventDefault(); card.classList.add('drop-target'); });
    card.addEventListener('dragleave', () => card.classList.remove('drop-target'));
    card.addEventListener('drop', e => { e.preventDefault(); card.classList.remove('drop-target'); moveImage(+e.dataTransfer.getData('text/plain'), i); });
    ta.addEventListener('mousedown', e => e.stopPropagation());
    ta.draggable = false;
    list.append(card);
  });
}

function setMode(mode) {
  S.ed.mode = mode;
  $('#modeComment').classList.toggle('active', mode === 'comment');
  $('#modeVideo').classList.toggle('active', mode === 'video');
  $('#commentPanel').classList.toggle('hidden', mode !== 'comment');
  $('#videoPanel').classList.toggle('hidden', mode !== 'video');
  if (mode === 'comment') renderCommentPanel();
}
$('#modeComment').onclick = () => setMode('comment');
$('#modeVideo').onclick = () => setMode('video');

function selectComment(i, seek = true) {
  const ed = S.ed;
  if (i < 0 || i >= ed.project.images.length) return;
  ed.current = i;
  document.querySelectorAll('#imageList .img-card').forEach((c, k) => {
    c.classList.toggle('current', k === i);
    const b = c.querySelector('.edit-btn');
    if (b) b.className = 'small-btn edit-btn' + (k === i ? ' primary' : ' ghost');
  });
  setMode('comment');
  const seg = segFor(ed.project.images[i].file);
  if (seek && seg && !ed.playing) seekTo(seg.start + Math.min(seg.in_duration + 0.5, seg.duration / 2));
}

function syncPanelText(i) {
  if (S.ed.current !== i) return;
  const t = $('#cpText');
  if (t && document.activeElement !== t) t.value = S.ed.project.images[i].text;
}
function syncCardText(i) {
  const card = document.querySelectorAll('#imageList .img-card')[i];
  if (card) card.querySelector('textarea').value = S.ed.project.images[i].text;
}

function playSfx(name) {
  if (!name) return toast('Âm thanh ngẫu nhiên đang được chọn — đợi preview cập nhật xong rồi nghe lại.');
  const a = new Audio(`/media/sfx/${enc(name)}`);
  a.volume = Math.min(1, effective().sfx_volume / 100 + 0.2);
  a.play().catch(fail);
}

// "🎬 Video effect" part of the comment editor: pick a clip, cut it, size/volume/position.
function vfxSection(img, seg, eff, set, sliderFor, pct, label) {
  const ov = img.overrides;
  const files = overlayFiles('vfx');
  const sec = el('div', { class: 'cp-section' }, el('h4', {}, '🎬 Video effect (sau khi đọc xong)'),
    el('div', { class: 'muted small' }, 'Clip phát ngay sau khi đọc xong (có tiếng). Bình luận được giữ lại đến khi clip hết rồi mới sang bình luận tiếp theo. Kéo clip trên khung preview để đổi vị trí.'));
  if (!files.length) { sec.append(el('div', { class: 'muted small' }, 'Thư mục VideoEffects chưa có clip nào.')); return sec; }
  const cur = ov.vfx ?? '';
  sec.append(el('div', { class: 'picker' }, [['', `Mặc định (${label(eff.vfx)})`], ['none', 'Không'], ['random', '🎲 Ngẫu nhiên'], ...files.map(f => [f, null])]
    .map(([v, text]) => el('button', { class: 'pick-item' + (cur === v ? ' active' : ''), title: v || 'Theo cài đặt cả video', onclick: () => set('vfx', v, true) },
      text ? el('span', {}, text) : el('video', { src: `/media/vfx/${enc(v)}#t=0.5`, muted: true, preload: 'metadata' })))));

  // the clip this comment will actually use (random is resolved by the server)
  const choice = ov.vfx ?? eff.vfx;
  const file = choice === 'random' ? seg?.vfx?.file : (choice && choice !== 'none' ? choice : null);
  if (!file) return sec;
  const len = vfxLen(file);
  const a0 = +(ov.vfx_trim_start ?? 0);
  const b0 = +(ov.vfx_trim_end || 0) > 0 ? Math.min(+ov.vfx_trim_end, len) : len;
  const used = seg?.vfx ? seg.vfx.dur : Math.max(0, b0 - a0);

  // mini player for cutting
  const player = el('video', { class: 'vfx-player', src: `/media/vfx/${enc(file)}`, controls: true, preload: 'auto' });
  player.addEventListener('loadedmetadata', () => { player.currentTime = a0; });
  player.addEventListener('timeupdate', () => { if (player.currentTime >= b0 && !player.paused) { player.pause(); player.currentTime = b0; } });
  const startVal = el('span', { class: 'val' }, `${fmt(a0)}s`);
  const endVal = el('span', { class: 'val' }, `${fmt(b0)}s`);
  const rs = el('input', { type: 'range', min: 0, max: len, step: 0.1, value: a0 });
  const re = el('input', { type: 'range', min: 0, max: len, step: 0.1, value: b0 });
  rs.addEventListener('input', () => { startVal.textContent = `${fmt(rs.value)}s`; player.currentTime = +rs.value; });
  re.addEventListener('input', () => { endVal.textContent = `${fmt(re.value)}s`; player.currentTime = +re.value; });
  const commit = (a, b) => {
    a = Math.max(0, Math.min(a, len - 0.1));
    b = Math.max(a + 0.1, Math.min(b, len));
    ov.vfx_trim_start = Math.round(a * 10) / 10;
    if (b >= len - 0.05) delete ov.vfx_trim_end; else ov.vfx_trim_end = Math.round(b * 10) / 10;
    if (!ov.vfx_trim_start) delete ov.vfx_trim_start;
    set('vfx', ov.vfx, true);
  };
  rs.addEventListener('change', () => commit(+rs.value, b0));
  re.addEventListener('change', () => commit(a0, +re.value));
  const row = (lbl, ...ctl) => el('div', { class: 'field' }, el('label', {}, lbl), el('div', { class: 'ctl' }, ...ctl));
  sec.append(
    el('div', { class: 'muted small' }, `Clip: ${file} • dài ${fmt(len)}s`),
    player,
    el('div', { class: 'row gap' },
      el('button', { class: 'small-btn', onclick: () => { player.pause(); player.currentTime = a0; player.play(); } }, '▶ Nghe/xem đoạn cắt'),
      el('button', { class: 'small-btn ghost', title: 'Đặt điểm bắt đầu tại vị trí đang xem', onclick: () => commit(player.currentTime, b0) }, '⇤ Đầu tại đây'),
      el('button', { class: 'small-btn ghost', title: 'Đặt điểm kết thúc tại vị trí đang xem', onclick: () => commit(a0, player.currentTime) }, '⇥ Cuối tại đây')),
    row('Bắt đầu', rs, startVal),
    row('Kết thúc', re, endVal),
    el('div', { class: 'small vfx-used' }, `Đoạn dùng: ${fmt(a0)}s → ${fmt(a0 + used)}s (${fmt(used)}s)`,
      +eff.vfx_max > 0 && used < b0 - a0 - 0.05 ? el('span', { class: 'muted' }, ` • đang giới hạn ${eff.vfx_max}s ở “Cài đặt cả video”`) : ''),
    row('Kích thước', ...sliderFor('vfx_size', 0.2, 1, 0.01, pct)),
    row('Âm lượng clip', ...sliderFor('vfx_volume', 0, 200, 5, v => `${v}%`, true)),
    row('Vị trí ngang', ...sliderFor('vfx_x', 0, 1, 0.01, pct)),
    row('Vị trí dọc', ...sliderFor('vfx_y', 0, 1, 0.01, pct)),
    el('div', { class: 'row gap' }, el('button', { class: 'small-btn', disabled: !seg?.vfx, onclick: () => playVfx(seg) }, '▶ Xem trong video')),
  );
  return sec;
}

// play the preview from the clip's start until it ends
function playVfx(seg) {
  if (!seg?.vfx) return;
  pausePreview();
  seekTo(Math.max(0, seg.vfx.at - 0.6));
  segmentEnd = seg.vfx.at + seg.vfx.dur + 0.2;
  playPreview();
}

// Per-comment editor shown in the right column.
function renderCommentPanel() {
  const ed = S.ed;
  const panel = $('#commentPanel');
  panel.innerHTML = '';
  const i = ed.current;
  const img = ed.project.images[i];
  if (!img) return;
  const ov = img.overrides;
  const eff = effective();
  const seg = segFor(img.file);
  const n = ed.project.images.length;

  const set = (k, v, stale) => {
    if (v === '' || v === null || v === undefined || Number.isNaN(v)) delete ov[k]; else ov[k] = v;
    if (stale) markStale();
    save();
    drawFrame();
    renderImageList();
    renderCommentPanel();
  };
  const section = (title, ...kids) => el('div', { class: 'cp-section' }, el('h4', {}, title), ...kids);
  const row = (label, k, ...ctl) => el('div', { class: 'field' + (k && k in ov ? ' overridden' : '') },
    el('label', {}, label), el('div', { class: 'ctl' }, ...ctl));
  const selectFor = (k, defLabel, opts, stale) => {
    const s = el('select', { onchange: () => set(k, s.value, stale(s.value)) },
      el('option', { value: '' }, defLabel), optionEls(opts));
    if (ov[k] && ![...s.options].some(o => o.value === ov[k])) s.append(el('option', { value: ov[k] }, ov[k]));
    s.value = ov[k] ?? '';
    return s;
  };
  const sliderFor = (k, min, max, step, show, stale = false) => {
    const val = el('span', { class: 'val' }, show(ov[k] ?? eff[k]));
    const r = el('input', { type: 'range', min, max, step, value: ov[k] ?? eff[k] });
    r.addEventListener('input', () => { val.textContent = show(+r.value); ov[k] = +r.value; drawFrame(); });
    r.addEventListener('change', () => set(k, +r.value, stale));
    const reset = k in ov ? el('button', { class: 'icon', title: 'Về mặc định', onclick: () => set(k, '', stale) }, '↺') : null;
    return [r, val, reset];
  };
  const pct = v => `${Math.round(v * 100)}%`;
  const label = v => (v === 'random' ? 'ngẫu nhiên' : v === 'none' ? 'không' : v);
  const eventSound = kind => (seg && !ed.stale ? (seg.sfx_events || []).find(e => e.kind === kind)?.sfx : null);

  panel.append(el('div', { class: 'cp-head' },
    el('button', { class: 'icon', title: 'Bình luận trước', disabled: i === 0, onclick: () => selectComment(i - 1) }, '◀'),
    el('div', { class: 'cp-title' }, `Bình luận ${i + 1}/${n}`, el('div', { class: 'muted small' }, img.file)),
    el('button', { class: 'icon', title: 'Bình luận sau', disabled: i === n - 1, onclick: () => selectComment(i + 1) }, '▶'),
  ));
  panel.append(el('img', { class: 'cp-thumb', src: `/media/content/${enc(ed.name)}/${enc(img.file)}` }));

  // text + voice
  const text = el('textarea', { id: 'cpText', rows: 3, placeholder: 'Nội dung bình luận cần đọc' });
  text.value = img.text;
  text.addEventListener('input', () => { img.text = text.value; markStale(); save(); syncCardText(i); });
  const skip = el('input', { type: 'checkbox', onchange: () => { img.skip = skip.checked; markStale(); save(); renderImageList(); } });
  skip.checked = img.skip;
  panel.append(section('🎙 Lời đọc & giọng đọc', text,
    el('label', { class: 'row gap muted small' }, skip, 'Không đọc bình luận này'),
    row('Giọng đọc', 'voice', selectFor('voice', `Mặc định (${voiceLabel(eff.voice)})`, voiceOpts(true), () => true)),
    el('div', { class: 'row gap' }, el('button', { class: 'small-btn', onclick: () => testVoice(img.text, ov.voice) }, '🔊 Nghe thử giọng này'))));

  // sound effects
  const startDefault = eff.sfx_start === 'all' || (eff.sfx_start === 'first' && i === 0)
    ? `Mặc định (${label(eff.sfx)})` : 'Mặc định (không phát)';
  const playChoice = (k, kind) => {
    const v = ov[k];
    if (v === 'none') return toast('Đang chọn “Không”.');
    playSfx(v && v !== 'random' ? v : eventSound(kind));
  };
  panel.append(section('🔊 Sound effect',
    row('Sau khi đọc xong', 'sfx_end', selectFor('sfx_end', `Mặc định (${label(eff.sfx_end)})`, sfxOpts(), () => true),
      el('button', { class: 'icon', title: 'Nghe', onclick: () => playChoice('sfx_end', 'end') }, '▶')),
    row('Lúc xuất hiện', 'sfx', selectFor('sfx', startDefault, sfxOpts(), () => true),
      el('button', { class: 'icon', title: 'Nghe', onclick: () => playChoice('sfx', 'start') }, '▶')),
    el('div', { class: 'muted small' }, 'Chọn riêng ở “Lúc xuất hiện” thì bình luận này luôn có âm khi hiện ra.')));

  // sticker & GIF pickers
  for (const [kind, title, sizeMax] of [['sticker', '😀 Sticker', 0.4], ['gif', '🎞 GIF', 0.9]]) {
    const files = overlayFiles(kind);
    const cur = ov[kind] ?? '';
    const pick = v => set(kind, v, true);  // sticker/GIF timing depends on the timeline
    const items = [['', `Mặc định (${label(eff[kind])})`], ['none', 'Không'], ['random', '🎲 Ngẫu nhiên'], ...files.map(f => [f, null])];
    const grid = el('div', { class: 'picker' }, items.map(([v, text]) => el('button', {
      class: 'pick-item' + (cur === v ? ' active' : ''), title: v || 'Theo cài đặt cả video', onclick: () => pick(v),
    }, text ? el('span', {}, text) : el('img', { src: `/media/${kind}/${enc(v)}`, loading: 'lazy' }))));
    panel.append(section(title, files.length ? grid
      : el('div', { class: 'muted small' }, `Thư mục ${kind === 'gif' ? 'GIFs' : 'Stickers'} chưa có file nào.`),
      row('Vị trí', `${kind}_pos`, selectFor(`${kind}_pos`, `Mặc định (${S.meta.overlay_pos[eff[`${kind}_pos`]]})`, Object.entries(S.meta.overlay_pos), () => false)),
      row('Kích thước', `${kind}_size`, ...sliderFor(`${kind}_size`, 0.05, sizeMax, 0.01, pct))));
  }

  panel.append(vfxSection(img, seg, eff, set, sliderFor, pct, label));

  // effects & layout
  const fx = k => selectFor(k, `Mặc định (${(Object.fromEntries(FIELD[k].opts()))[eff[k]] || eff[k]})`, FIELD[k].opts(), () => false);
  const num = (k, ph) => {
    const nEl = el('input', { type: 'number', step: 0.1, min: 0, placeholder: ph });
    nEl.value = ov[k] ?? '';
    nEl.addEventListener('change', () => set(k, nEl.value === '' ? '' : +nEl.value, true));
    return nEl;
  };
  panel.append(section('✨ Hiệu ứng & bố cục',
    row('Xuất hiện', 'effect_in', fx('effect_in')), row('Biến mất', 'effect_out', fx('effect_out')),
    row('Nhấn mạnh', 'emphasis', fx('emphasis')),
    row('Độ rộng ảnh', 'scale', ...sliderFor('scale', 0.3, 1, 0.01, pct)),
    row('Vị trí ngang', 'pos_x', ...sliderFor('pos_x', 0, 1, 0.01, pct)),
    row('Vị trí dọc', 'pos_y', ...sliderFor('pos_y', 0, 1, 0.01, pct)),
    row('Thời lượng tối thiểu', 'duration', num('duration', 'tự động')),
    row('Giữ thêm (s)', 'extra_hold', num('extra_hold', '0'))));

  panel.append(el('div', { class: 'row gap cp-actions' },
    el('button', { class: 'small-btn', onclick: () => playSegment(i) }, '▶ Xem bình luận này'),
    el('button', { class: 'small-btn ghost', disabled: !Object.keys(ov).length, onclick: () => { img.overrides = {}; markStale(); save(); renderImageList(); renderCommentPanel(); drawFrame(); } }, 'Xoá mọi chỉnh riêng')));
}

function moveImage(from, to) {
  const imgs = S.ed.project.images;
  if (from === to || from < 0 || to < 0 || from >= imgs.length || to >= imgs.length) return;
  const [it] = imgs.splice(from, 1);
  imgs.splice(to, 0, it);
  markStale();
  save();
  renderImageList();
}

function renderEdSettings() {
  const p = S.ed.project;
  renderFields($('#edSettings'), effective(), p.settings, (f, v, live) => {
    p.settings[f.k] = v;
    if (isStale(f, v) && !live) markStale();
    if (!live) { save(); renderEdSettings(); if (!f.stale) renderImageList(); }
    drawFrame();
  }, g => {
    g.items.forEach(f => delete p.settings[f.k]);
    if (g.items.some(f => f.stale)) markStale();
    save(); renderEdSettings(); drawFrame();
  });
}
$('#btnResetAll').onclick = () => {
  if (!S.ed) return;
  S.ed.project.settings = {};
  S.ed.project.images.forEach(i => { i.overrides = {}; });
  markStale(); save(); renderEditor(); drawFrame();
};

function renderBgSelect() {
  const p = S.ed.project;
  const s = $('#edBg');
  s.innerHTML = '';
  s.append(el('option', { value: '' }, '🎲 Ngẫu nhiên mỗi lần dựng'));
  for (const b of S.meta.backgrounds) s.append(el('option', { value: b.name }, `${b.name} (${fmt(b.duration)}s)`));
  s.value = p.background || '';
  const tlbg = S.ed.timeline?.background;
  $('#edBgNote').textContent = !S.meta.backgrounds.length ? 'Thư mục Backgrounds chưa có video nào.'
    : p.background ? 'Background cố định cho content này.'
      : tlbg ? `Preview đang dùng: ${tlbg}. Khi dựng sẽ chọn ngẫu nhiên (tránh lặp lại gần nhất).` : '';
}
$('#edBg').onchange = () => {
  S.ed.project.background = $('#edBg').value || null;
  save(); loadBgVideo(S.ed.project.background || S.ed.timeline?.background); renderBgSelect();
};
$('#btnBgShuffle').onclick = async () => {
  try {
    const cur = S.ed.project.background || S.ed.timeline?.background;
    let r = await api(`/api/contents/${enc(S.ed.name)}/random_bg`, { body: {} });
    if (r.background === cur && S.meta.backgrounds.length > 1) r = await api(`/api/contents/${enc(S.ed.name)}/random_bg`, { body: {} });
    S.ed.project.background = r.background;
    save(); renderBgSelect(); loadBgVideo(r.background);
  } catch (e) { fail(e); }
};

const save = debounce(async () => {
  const ed = S.ed;
  if (!ed) return;
  $('#saveState').textContent = 'Đang lưu…';
  try {
    const p = ed.project;
    await api(`/api/contents/${enc(ed.name)}`, { method: 'PUT', body: { settings: p.settings, background: p.background, images: p.images } });
    $('#saveState').textContent = '✓ Đã lưu';
  } catch (e) { $('#saveState').textContent = 'Lỗi lưu'; fail(e); }
}, 500);

function setPreviewStatus(text, kind = '') {
  const el_ = $('#previewStatus');
  el_.textContent = text;
  el_.className = `preview-status small ${kind || 'muted'}`;
  $('#btnBuild').classList.toggle('hidden', kind !== 'error');
}

// Any change that affects voice/timing/audio marks the preview stale; it is rebuilt
// automatically shortly after the last change (typing keeps postponing it).
const autoBuild = debounce(() => buildTimeline(), 1200);
function markStale() {
  if (!S.ed) return;
  S.ed.stale = true;
  setPreviewStatus('⟳ Có thay đổi — preview sẽ tự cập nhật…');
  autoBuild();
}

async function buildTimeline() {
  const ed = S.ed;
  if (!ed) return;
  if (ed.building) { ed.rebuild = true; return; }   // run again once the current build ends
  ed.building = true;
  autoBuild.cancel?.();
  const first = !ed.timeline;
  const resumeAt = curTime();
  const wasPlaying = ed.playing;
  await save.flush();
  const msg = $('#stageMsg');
  if (first) {
    msg.textContent = 'Đang tạo giọng đọc và trộn âm thanh…';
    msg.classList.remove('hidden');
  }
  setPreviewStatus('⟳ Đang cập nhật preview (giọng đọc, âm thanh)…');
  try {
    const tl = await api(`/api/contents/${enc(ed.name)}/timeline`, { body: { background: ed.timeline?.background } });
    if (S.ed !== ed) return;
    ed.timeline = tl;
    ed.stale = ed.rebuild;
    ed.lastError = null;
    if (wasPlaying) pausePreview();
    pAudio.src = tl.audio;
    loadBgVideo(ed.project.background || tl.background);
    msg.classList.add('hidden');
    if (first) renderEditor(); else refreshAfterBuild();
    const at = first ? 0 : Math.min(resumeAt, Math.max(0, tl.total - 0.05));
    await new Promise(r => { pAudio.addEventListener('loadedmetadata', r, { once: true }); setTimeout(r, 1500); });
    seekTo(at);
    if (wasPlaying) playPreview();
    if (!ed.rebuild) setPreviewStatus(`✓ Preview đã cập nhật • ${fmt(tl.total)}s`, 'ok');
  } catch (e) {
    if (first) msg.textContent = '⚠ ' + e.message;
    setPreviewStatus('⚠ ' + e.message, 'error');
    if (ed.lastError !== e.message) fail(e);   // don't repeat the same toast on every auto-retry
    ed.lastError = e.message;
  } finally {
    ed.building = false;
    if (ed.rebuild && S.ed === ed) { ed.rebuild = false; buildTimeline(); }
  }
}

// update durations etc. without re-rendering inputs the user may be typing in
function refreshAfterBuild() {
  const ed = S.ed;
  $('#edInfo').textContent = `${ed.project.images.length} ảnh • ${fmt(ed.timeline.total)}s`;
  document.querySelectorAll('#imageList .img-card').forEach((card, i) => {
    const seg = segFor(ed.project.images[i]?.file);
    const chip = card.querySelector('.dur-chip');
    if (chip) chip.textContent = seg ? `${fmt(seg.duration)}s` : '';
  });
  renderBgSelect();
  const panel = $('#commentPanel');
  if (ed.mode === 'comment' && !panel.contains(document.activeElement)) renderCommentPanel();
}

$('#btnBuild').onclick = buildTimeline;

function loadBgVideo(name) {
  if (!name) { bgVideo.removeAttribute('src'); return; }
  const src = `/media/bg/${enc(name)}`;
  if (bgVideo.dataset.name !== name) {
    bgVideo.dataset.name = name;
    bgVideo.src = src;
    bgVideo.addEventListener('loadeddata', () => syncBg(true), { once: true });
  }
}

// ---- playback
let rafId = 0;
let tickId = 0;
let segmentEnd = null;
const curTime = () => pAudio.currentTime || 0;

function syncBg(force) {
  const tl = S.ed?.timeline;
  if (!tl || !bgVideo.duration) return drawFrame();
  const want = (tl.bg_offset + curTime()) % bgVideo.duration;
  if (force || Math.abs(bgVideo.currentTime - want) > 0.25) bgVideo.currentTime = want;
  drawFrame();
}
bgVideo.addEventListener('seeked', () => drawFrame());

function playPreview() {
  if (!S.ed?.timeline) return;
  if (curTime() >= S.ed.timeline.total - 0.05) pAudio.currentTime = 0;
  S.ed.playing = true;
  pAudio.play().catch(fail);
  syncBg(true);
  bgVideo.play().catch(() => {});
  $('#btnPlay').textContent = '❚❚';
  cancelAnimationFrame(rafId);
  clearInterval(tickId);
  let last = 0;
  const step = () => {
    if (!S.ed?.playing) return false;
    if (segmentEnd !== null && curTime() >= segmentEnd) { pausePreview(); return false; }
    last = performance.now();
    syncBg(false);
    return true;
  };
  const loop = () => { if (step()) rafId = requestAnimationFrame(loop); };
  rafId = requestAnimationFrame(loop);
  // fallback when the browser throttles animation frames (busy or background window)
  tickId = setInterval(() => { if (performance.now() - last > 60) step(); }, 40);
}
function pausePreview() {
  segmentEnd = null;
  if (S.ed) S.ed.playing = false;
  pAudio.pause();
  bgVideo.pause();
  vfxVideos.forEach(v => v.pause());
  $('#btnPlay').textContent = '▶';
  cancelAnimationFrame(rafId);
  clearInterval(tickId);
}
pAudio.addEventListener('ended', pausePreview);
$('#btnPlay').onclick = () => (S.ed?.playing ? pausePreview() : (segmentEnd = null, playPreview()));

function seekTo(t) {
  pAudio.currentTime = Math.max(0, t);
  syncBg(true);
}
$('#seek').addEventListener('input', e => {
  if (!S.ed?.timeline) return;
  pausePreview();
  seekTo(+e.target.value / 1000 * S.ed.timeline.total);
});
$('#btnPlay').disabled = false;

function playSegment(i) {
  const ed = S.ed;
  selectComment(i, false);
  const seg = segFor(ed.project.images[i].file);
  if (!seg || ed.stale) {
    if (ed.stale) toast('Preview đang cập nhật theo thay đổi mới…');
    if (!seg) return drawFrame();
  }
  pausePreview();
  seekTo(seg.start);
  segmentEnd = seg.start + seg.duration;
  playPreview();
}

// visual props come from the live project so layout/effect tweaks show instantly
function visualSeg(seg) {
  const img = S.ed.project.images.find(x => x.file === seg.file);
  const eff = effective();
  const ov = img ? img.overrides : {};
  const pick = k => (ov[k] ?? eff[k]);
  return { ...seg, effect_in: pick('effect_in'), effect_out: pick('effect_out'), emphasis: pick('emphasis'),
    scale: +pick('scale'), pos_x: +pick('pos_x'), pos_y: +pick('pos_y'),
    overlays: ['gif', 'sticker'].map(kind => {
      const file = overlayFor(kind, pick(kind), seg);
      return file && { kind, file, pos: pick(`${kind}_pos`), size: +pick(`${kind}_size`), delay: seg.overlay_delay ?? 0 };
    }).filter(Boolean),
    vfx: seg.vfx ? { ...seg.vfx, size: +pick('vfx_size'), x: +pick('vfx_x'), y: +pick('vfx_y') } : null };
}

// "random" is resolved on the server (stable per comment); explicit choices apply live
function overlayFor(kind, choice, seg) {
  if (!choice || choice === 'none') return null;
  if (choice === 'random') return (seg.overlays || []).find(o => o.kind === kind)?.file || null;
  return overlayFiles(kind).includes(choice) ? choice : null;
}

function layoutOf(seg, im, W, H, eff) {
  let w = W * seg.scale;
  let h = im.naturalHeight * w / im.naturalWidth;
  const maxH = H * eff.max_height;
  if (h > maxH) { h = maxH; w = im.naturalWidth * h / im.naturalHeight; }
  return { w, h };
}

function rectPath(x, y, w, h) {
  ctx.beginPath();
  ctx.rect(x, y, w, h);
}

function drawFrame() {
  const W = stage.width, H = stage.height;
  ctx.clearRect(0, 0, W, H);
  const ed = S.ed;
  const tl = ed?.timeline;
  if (!tl) return;
  const t = curTime();
  $('#timeLabel').textContent = `${fmt(t)} / ${fmt(tl.total)}s`;
  if (document.activeElement !== $('#seek')) $('#seek').value = Math.round(t / tl.total * 1000);
  const eff = effective();
  const unit = W / 1080;
  for (const raw of tl.segments) {
    const lt = t - raw.start;
    if (lt < 0 || lt >= raw.duration) continue;
    const seg = visualSeg(raw);
    const im = loadImg(ed.name, seg.file);
    if (!im.complete || !im.naturalWidth) continue;
    const st = FX.state(seg, lt);
    if (st.opacity <= 0.004 || st.scale <= 0.02) continue;
    const { w, h } = layoutOf(seg, im, W, H, eff);
    const cx = (seg.pos_x + st.dx) * W, cy = (seg.pos_y + st.dy) * H;
    const sw = w * st.scale, sh = h * st.scale;
    const x = cx - sw / 2, y = cy - sh / 2;
    ctx.save();
    ctx.globalAlpha = st.opacity;
    if (st.glow > 0.01) {
      ctx.save();
      ctx.globalAlpha = st.opacity * st.glow;
      ctx.shadowColor = 'rgb(255,214,64)';
      ctx.shadowBlur = 26 * unit;
      ctx.strokeStyle = 'rgb(255,214,64)';
      ctx.lineWidth = 8 * unit;
      rectPath(x, y, sw, sh);
      ctx.stroke();
      ctx.restore();
    }
    if (eff.shadow) {
      ctx.save();
      ctx.shadowColor = 'rgba(0,0,0,0.5)';
      ctx.shadowBlur = 28 * unit;
      ctx.shadowOffsetY = 8 * unit;
      ctx.fillStyle = 'rgba(0,0,0,0.01)';
      rectPath(x, y, sw, sh);
      ctx.fill();
      ctx.restore();
    }
    ctx.drawImage(im, x, y, sw, sh);
    ctx.restore();
    raw._box = { x, y, w: sw, h: sh };
    for (const o of seg.overlays) drawOverlay(o, lt, st, cx, cy, sw, sh, W, H);
  }
  // video effects on top, like the renderer
  for (const raw of tl.segments) {
    raw._vfxBox = null;
    if (raw.vfx) drawVfx(raw, visualSeg(raw), t, W, H);
  }
}

// Clip <video> elements are muted: their sound is already in the server-mixed preview audio.
const vfxVideos = new Map();
function getVfxVideo(file) {
  if (!vfxVideos.has(file)) {
    const v = document.createElement('video');
    Object.assign(v, { muted: true, playsInline: true, preload: 'auto', src: `/media/vfx/${enc(file)}` });
    v.addEventListener('seeked', () => { if (!S.ed?.playing) drawFrame(); });
    v.addEventListener('loadeddata', () => drawFrame());
    // kept in the DOM (off-screen): detached media elements start playing noticeably later
    v.className = 'offscreen-media';
    document.body.append(v);
    vfxVideos.set(file, v);
  }
  return vfxVideos.get(file);
}

function drawVfx(raw, seg, t, W, H) {
  const v = seg.vfx;
  const vid = getVfxVideo(v.file);
  const vt = t - v.at;
  if (vt < 0 || vt >= v.dur) {
    if (!vid.paused) vid.pause();
    // cue the clip up shortly before it is due so it starts without a seek delay
    if (vt < 0 && vt > -1.2 && !vid.seeking && Math.abs(vid.currentTime - v.trim_start) > 0.05) vid.currentTime = v.trim_start;
    return;
  }
  const want = v.trim_start + vt;
  if (S.ed.playing) {
    if (vid.paused) {
      if (Math.abs(vid.currentTime - want) > 0.3) vid.currentTime = want;  // cued clips start without seeking
      vid.play().catch(() => {});
    }
    else if (Math.abs(vid.currentTime - want) > 0.3) vid.currentTime = want;
  } else {
    if (!vid.paused) vid.pause();
    if (!vid.seeking && Math.abs(vid.currentTime - want) > 0.05) vid.currentTime = want;
  }
  if (vid.readyState < 2 || !vid.videoWidth) return;
  const vs = FX.vfxState(vt, v.dur);
  let w = W * v.size, h = vid.videoHeight * w / vid.videoWidth;
  if (h > H * 0.8) { h = H * 0.8; w = vid.videoWidth * h / vid.videoHeight; }
  const sw = w * vs.scale, sh = h * vs.scale;
  const x = v.x * W - sw / 2, y = v.y * H - sh / 2;
  ctx.save();
  ctx.globalAlpha = vs.opacity;
  ctx.drawImage(vid, x, y, sw, sh);
  ctx.restore();
  raw._vfxBox = { x, y, w: sw, h: sh };
}

// mirrors the overlay branch of the frame loop in maker/render.py
function drawOverlay(o, lt, st, cx, cy, bw, bh, W, H) {
  const sp = getSprite(o.kind, o.file);
  if (!sp.ready) return;
  const ks = FX.overlayState(o.delay, lt);
  if (!ks || ks.opacity <= 0.004) return;
  let w0 = W * o.size, h0 = sp.h * w0 / sp.w;
  if (h0 > w0 * 1.4) { h0 = w0 * 1.4; w0 = sp.w * h0 / sp.h; }
  const [ocx, ocy] = FX.overlayCenter(o.pos, cx, cy, bw, bh, w0 * st.scale, h0 * st.scale);
  const k = st.scale * ks.scale;
  ctx.save();
  ctx.globalAlpha = st.opacity * ks.opacity;
  ctx.drawImage(spriteFrame(sp, lt - o.delay), ocx - w0 * k / 2, ocy + ks.dy * H - h0 * k / 2, w0 * k, h0 * k);
  ctx.restore();
}

function resizeStage() { drawFrame(); }

// drag the visible image to reposition it (saved as a per-image override)
let drag = null;
stage.addEventListener('mousedown', e => {
  const tl = S.ed?.timeline;
  if (!tl) return;
  const rect = stage.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / rect.width, my = (e.clientY - rect.top) / rect.height;
  const t = curTime();
  const px = mx * stage.width, py = my * stage.height;
  const hit = tl.segments.find(s => s._vfxBox && px >= s._vfxBox.x && px <= s._vfxBox.x + s._vfxBox.w
    && py >= s._vfxBox.y && py <= s._vfxBox.y + s._vfxBox.h);
  if (hit) {
    const vimg = S.ed.project.images.find(x => x.file === hit.file);
    const vv = visualSeg(hit).vfx;
    if (S.ed.project.images.indexOf(vimg) !== S.ed.current) selectComment(S.ed.project.images.indexOf(vimg), false);
    drag = { img: vimg, kind: 'vfx', dx: vv.x - mx, dy: vv.y - my };
    pausePreview();
    return;
  }
  const seg = [...tl.segments].reverse().find(s => t >= s.start && t < s.start + s.duration);
  if (!seg) return;
  const img = S.ed.project.images.find(x => x.file === seg.file);
  if (S.ed.project.images.indexOf(img) !== S.ed.current) selectComment(S.ed.project.images.indexOf(img), false);
  const v = visualSeg(seg);
  drag = { img, dx: v.pos_x - mx, dy: v.pos_y - my };
  pausePreview();
});
window.addEventListener('mousemove', e => {
  if (!drag) return;
  const rect = stage.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / rect.width, my = (e.clientY - rect.top) / rect.height;
  const c = v => Math.round(Math.min(1, Math.max(0, v)) * 1000) / 1000;
  const [kx, ky] = drag.kind === 'vfx' ? ['vfx_x', 'vfx_y'] : ['pos_x', 'pos_y'];
  drag.img.overrides[kx] = c(mx + drag.dx);
  drag.img.overrides[ky] = c(my + drag.dy);
  drawFrame();
});
window.addEventListener('mouseup', () => {
  if (!drag) return;
  drag = null;
  save();
  renderImageList();
  if (S.ed.mode === 'comment') renderCommentPanel();
});

async function testVoice(text, voice) {
  if (!text || !text.trim()) return toast('Ảnh này chưa có nội dung đọc.');
  const eff = S.ed ? effective() : S.settings.defaults;
  try {
    toast('Đang tạo giọng đọc thử…', 'info', 1500);
    const r = await api('/api/tts/test', { body: { text, voice: voice || eff.voice, rate: eff.rate, pitch: eff.pitch } });
    const a = $('#voiceTest');
    a.src = r.url;
    a.volume = Math.min(1, eff.voice_volume / 100);
    a.play();
  } catch (e) { fail(e); }
}

async function queueOne(preview) {
  const ed = S.ed;
  if (!ed) return;
  await save.flush();
  try {
    await api('/api/queue/add', { body: { names: [ed.name], preview } });
    toast(preview ? 'Đang xuất preview nhanh… video sẽ tự mở khi xong.' : `Đã thêm “${ed.name}” vào hàng đợi.`, 'ok');
    pollQueue();
  } catch (e) { fail(e); }
}
$('#btnQuickRender').onclick = () => queueOne(true);
$('#btnRenderOne').onclick = () => queueOne(false);

// ---------------------------------------------------------------- settings page
const FOLDERS = [
  ['backgrounds_dir', 'Backgrounds'], ['contents_dir', 'Contents'], ['sfx_dir', 'SoundEffects'],
  ['music_dir', 'SoundBackground'], ['stickers_dir', 'Stickers'], ['gifs_dir', 'GIFs'], ['vfx_dir', 'VideoEffects'], ['output_dir', 'Output'],
];
const EXPORT = [
  { k: 'width', label: 'Chiều rộng', t: 'number' }, { k: 'height', label: 'Chiều cao', t: 'number' },
  { k: 'fps', label: 'FPS', t: 'number' }, { k: 'crf', label: 'Chất lượng CRF (thấp = đẹp hơn)', t: 'number' },
  { k: 'preset', label: 'Tốc độ mã hoá', t: 'select', opts: ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow'] },
  { k: 'audio_bitrate', label: 'Bitrate âm thanh', t: 'select', opts: ['128k', '160k', '192k', '256k', '320k'] },
  { k: 'preview_scale', label: 'Tỉ lệ preview nhanh', t: 'select', opts: ['0.33', '0.5', '0.75'] },
  { k: 'avoid_repeat', label: 'Tránh lặp N background gần nhất', t: 'number' },
  { k: 'name_pattern', label: 'Quy tắc đặt tên file', t: 'text' },
  { k: 'auto_ocr', label: 'Tự đọc chữ từ ảnh khi chưa có lời đọc', t: 'check' },
];
let draft = null;

function renderSettings() {
  draft = JSON.parse(JSON.stringify(S.settings));
  const ff = $('#folderFields');
  ff.innerHTML = '';
  for (const [k, label] of FOLDERS) {
    const inp = el('input', { value: draft[k], oninput: () => { draft[k] = inp.value; } });
    ff.append(el('div', { class: 'folder-row' }, el('label', {}, label), inp,
      el('button', { class: 'small-btn', onclick: async () => {
        const r = await api('/api/pick_folder', { body: { initial: inp.value } }).catch(fail);
        if (r && r.path) { inp.value = r.path; draft[k] = r.path; }
      } }, 'Chọn…'),
      el('button', { class: 'small-btn ghost', onclick: () => openPath(inp.value) }, '📁')));
  }
  const ex = $('#exportFields');
  ex.innerHTML = '';
  for (const f of EXPORT) {
    let ctl;
    if (f.t === 'select') {
      ctl = el('select', {}, f.opts.map(o => el('option', { value: o }, o)));
      ctl.value = String(draft[f.k]);
    } else if (f.t === 'check') {
      ctl = el('input', { type: 'checkbox' });
      ctl.checked = !!draft[f.k];
    } else {
      ctl = el('input', { type: f.t, value: draft[f.k] });
    }
    ctl.addEventListener('change', () => {
      draft[f.k] = f.t === 'check' ? ctl.checked
        : f.t === 'text' || f.k === 'audio_bitrate' || f.k === 'preset' ? ctl.value : +ctl.value;
    });
    ex.append(el('div', { class: 'field' }, el('label', {}, f.label), el('div', { class: 'ctl' }, ctl)));
  }
  const renderDefaults = () => renderFields($('#defaultFields'), draft.defaults, null, (f, v, live) => {
    draft.defaults[f.k] = v;
  });
  renderDefaults();
  const hist = $('#bgHistory');
  hist.innerHTML = '';
  const h = S.meta.bg_history || [];
  if (!h.length) hist.append(el('div', { class: 'muted' }, 'Chưa có video nào được dựng.'));
  for (const it of h) hist.append(el('div', { class: 'hist-item' },
    el('span', { class: 'muted mono' }, new Date(it.time * 1000).toLocaleString('vi-VN')),
    el('span', {}, it.background), el('span', { class: 'muted' }, '→ ' + it.content)));
}

$('#btnSaveSettings').onclick = async () => {
  try {
    S.settings = await api('/api/settings', { body: draft });
    S.meta = await api('/api/meta');
    $('#settingsSaved').textContent = '✓ Đã lưu ' + new Date().toLocaleTimeString('vi-VN');
    toast('Đã lưu cài đặt.', 'ok');
    renderSettings();
    loadContents(true);
  } catch (e) { fail(e); }
};
$('#btnTtsTest').onclick = async () => {
  const d = draft ? draft.defaults : S.settings.defaults;
  try {
    const r = await api('/api/tts/test', { body: { text: $('#ttsTestText').value, voice: d.voice, rate: d.rate, pitch: d.pitch } });
    const a = $('#voiceTest');
    a.src = r.url;
    a.play();
  } catch (e) { fail(e); }
};
$('#btnVoicesRefresh').onclick = async () => {
  try {
    S.meta.voices = await api('/api/voices/refresh', { body: {} });
    toast(`Đã tải ${S.meta.voices.length} giọng đọc.`, 'ok');
    renderSettings();
  } catch (e) { fail(e); }
};

// ---------------------------------------------------------------- boot
(async function boot() {
  try {
    [S.settings, S.meta] = await Promise.all([api('/api/settings'), api('/api/meta')]);
  } catch (e) {
    document.body.prepend(el('div', { class: 'note' }, 'Không kết nối được máy chủ Video Maker: ' + e.message));
    return;
  }
  await loadContents(true);
  pollQueue();
  setInterval(pollQueue, 1000);
  // pick up new content folders automatically
  setInterval(() => { if ($('#tab-contents').classList.contains('active') && !document.hidden) loadContents(true); }, 5000);
  // refresh background/music lists periodically (new files dropped into folders)
  setInterval(async () => { try { const m = await api('/api/meta'); S.meta = m; } catch (_) {} }, 15000);
  drawFrame();
})();
