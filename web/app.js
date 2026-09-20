'use strict';
// No framework, no dependencies. Reads data.json (written by build.py) and draws it.
//
//   #/                 all photos
//   #/albums           album covers
//   #/albums/<slug>    one album

const $ = (sel) => document.querySelector(sel);
const view = $('#view');
const lb = $('#lightbox');
const lbImg = $('#lb-img');
const lbStage = $('#lb-stage');
const about = $('#about');
const BASE_TITLE = document.title;

let data = { site: {}, photos: [], albums: [] };
let albums = new Map();

// ---- tiny helpers -----------------------------------------------------------
/** h('a', {href: '#'}, 'text', child) -> element. Builds DOM safely (no innerHTML). */
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    el.setAttribute(k, v === true ? '' : v);
  }
  el.append(...kids.flat().filter((k) => k != null && k !== false));
  return el;
}

const plural = (n) => `${n} photo${n === 1 ? '' : 's'}`;
const setTitle = (part) => { document.title = part ? `${part} – ${BASE_TITLE}` : BASE_TITLE; };

/** 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD' -> readable, in the visitor's language. */
function fmtDate(d) {
  if (!d) return '';
  const [y, m, day] = d.split('-').map(Number);
  if (!m) return String(y);
  const opts = day ? { year: 'numeric', month: 'long', day: 'numeric' } : { year: 'numeric', month: 'long' };
  return new Date(y, m - 1, day || 1).toLocaleDateString(undefined, opts);
}

function loadedImg(src, alt = '') {
  const img = h('img', { alt, loading: 'lazy', decoding: 'async' });
  img.addEventListener('load', () => img.classList.add('in'), { once: true });
  img.src = src;
  return img;
}

function notice(heading, ...paragraphs) {
  return h('div', { class: 'notice' }, h('h1', {}, heading), ...paragraphs);
}

// ---- views --------------------------------------------------------------------
function emptyState() {
  return notice(
    'No photos yet',
    h('p', {}, 'Add images to a folder inside ', h('code', {}, 'photos/'), ' (for example ',
      h('code', {}, 'photos/Iceland/'), '), then push. Each folder becomes an album.'),
  );
}

function photoTile(p, i, showAlbum) {
  const album = showAlbum && p.album ? albums.get(p.album) : null;
  return h('a', { class: 'tile', href: p.src, 'data-i': i },
    loadedImg(p.thumb, p.title || `Photo ${i + 1}`),
    album && h('span', { class: 'tag' }, album.title));
}

/** A square mosaic. Clicking a tile opens the viewer on that list of photos. */
function grid(list, showAlbum) {
  const el = h('div', { class: 'grid' });
  const frag = document.createDocumentFragment();
  list.forEach((p, i) => frag.append(photoTile(p, i, showAlbum)));
  el.append(frag);
  el.addEventListener('click', (e) => {
    const a = e.target.closest('a.tile');
    if (!a || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; // let "open in new tab" work
    e.preventDefault();
    openViewer(list, Number(a.dataset.i));
  });
  return el;
}

function photosView() {
  return data.photos.length ? grid(data.photos, true) : emptyState();
}

function albumsView() {
  if (!data.albums.length) {
    return data.photos.length
      ? notice('No albums yet', h('p', {}, 'Put photos in a folder inside ', h('code', {}, 'photos/'),
        ' and each folder shows up here as an album.'))
      : emptyState();
  }
  const el = h('div', { class: 'grid albums' });
  for (const a of data.albums) {
    const date = fmtDate(a.date);
    el.append(h('a', { class: 'tile', href: `#/albums/${a.slug}` },
      loadedImg(a.cover),
      h('div', { class: 'cap' },
        h('b', {}, a.title),
        h('span', {}, plural(a.photos.length)),
        date && h('span', {}, date))));
  }
  return el;
}

function albumView(slug) {
  const a = albums.get(slug);
  if (!a) { location.replace('#/albums'); return null; }
  const list = a.photos.map((i) => data.photos[i]);
  const date = fmtDate(a.date);
  const back = h('a', { class: 'back', href: '#/albums' });
  back.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>Albums'; // static markup
  setTitle(a.title);
  return h('div', {},
    h('div', { class: 'head' }, back, h('h1', {}, a.title),
      h('div', { class: 'meta' }, h('span', {}, plural(list.length)), date && h('span', {}, date))),
    grid(list, false));
}

// ---- routing ----------------------------------------------------------------
function route(scrollToTop) {
  const [tab, arg] = location.hash.replace(/^#\/?/, '').split('/');
  let node;
  let active = 'photos';
  if (tab === 'albums') {
    active = 'albums';
    if (arg) node = albumView(arg);
    else { node = albumsView(); setTitle('Albums'); }
  } else {
    node = photosView();
    setTitle('');
  }
  if (!node) return; // redirecting
  view.replaceChildren(node);
  document.querySelectorAll('nav a').forEach((a) => {
    if (a.dataset.tab === active) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  if (scrollToTop) window.scrollTo(0, 0);
}

// ---- photo viewer ------------------------------------------------------------
const viewer = { list: [], i: 0 };

function openViewer(list, i) {
  viewer.list = list;
  viewer.i = i;
  lb.classList.toggle('single', list.length < 2);
  showPhoto();
  lb.showModal();
  history.pushState({ viewer: true }, ''); // so the Back button closes the viewer
}

function showPhoto() {
  const { list, i } = viewer;
  const p = list[i];
  const n = list.length;
  const album = p.album && albums.get(p.album);

  lbImg.src = p.src;
  lbImg.alt = p.title || `Photo ${i + 1} of ${n}`;
  $('#lb-count').textContent = n > 1 ? `${i + 1} / ${n}` : '';

  const name = p.title || (album && album.title) || '';
  const sub = p.title && album ? album.title : '';
  $('#lb-where').replaceChildren(...[name && h('b', {}, name), sub && h('span', {}, sub)].filter(Boolean));
  $('#lb-exif').replaceChildren(...Object.entries(p.exif || {}).map(
    ([k, v]) => h('span', {}, k === 'date' ? fmtDate(v.slice(0, 10)) : v)));

  for (const d of [1, -1]) { // warm the cache for the next/previous photo
    const near = list[(i + d + n) % n];
    if (near) new Image().src = near.src;
  }
}

function step(d) {
  const n = viewer.list.length;
  if (n < 2) return;
  viewer.i = (viewer.i + d + n) % n;
  showPhoto();
}

$('#lb-close').addEventListener('click', () => lb.close());
$('#lb-prev').addEventListener('click', () => step(-1));
$('#lb-next').addEventListener('click', () => step(1));
lb.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight') step(1);
  else if (e.key === 'ArrowLeft') step(-1);
});
lb.addEventListener('close', () => {
  lbImg.removeAttribute('src');
  if (history.state && history.state.viewer) history.back();
});
addEventListener('popstate', () => { if (lb.open) lb.close(); });

// Swipe left/right on touch screens; click on the empty area around the photo to close.
let start = null;
let swiped = false;
lbStage.addEventListener('pointerdown', (e) => { start = { x: e.clientX, y: e.clientY }; });
lbStage.addEventListener('pointercancel', () => { start = null; });
lbStage.addEventListener('pointerup', (e) => {
  if (!start) return;
  const dx = e.clientX - start.x;
  const dy = e.clientY - start.y;
  start = null;
  if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) {
    swiped = true;
    step(dx < 0 ? 1 : -1);
  }
});
lb.addEventListener('click', (e) => {
  if (swiped) { swiped = false; return; }
  if (e.target === lb || e.target === lbStage) lb.close();
});

// ---- about drawer & footer -----------------------------------------------------
function initAbout(site) {
  const paragraphs = (site.bio || '').split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);
  const links = [...(site.links || [])];
  if (site.email) links.push({ label: 'Email', url: `mailto:${site.email}` });
  if (!paragraphs.length && !links.length) return; // nothing to show, so no About button

  $('#about-body').append(
    h('h2', {}, site.author || site.title),
    ...paragraphs.map((t) => h('p', {}, t)),
    links.length ? h('ul', {}, ...links.map((l) => h('li', {},
      h('a', { href: l.url, ...(l.url.startsWith('http') ? { target: '_blank', rel: 'noopener' } : {}) }, l.label)))) : null,
  );
  const open = $('#about-open');
  open.hidden = false;
  open.addEventListener('click', () => about.showModal());
  $('#about-close').addEventListener('click', () => about.close());
  about.addEventListener('click', (e) => { if (e.target === about) about.close(); });
}

// ---- start ---------------------------------------------------------------------
async function init() {
  try {
    const res = await fetch(`data.json?v=${document.documentElement.dataset.build}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (err) {
    view.replaceChildren(location.protocol === 'file:'
      ? notice('Open this site through a web server',
        h('p', {}, 'Browsers block a page opened straight from disk from reading its photo list. Run ',
          h('code', {}, 'python build.py'), ' then ', h('code', {}, 'python -m http.server -d _site'),
          ' and visit ', h('code', {}, 'http://localhost:8000'), '.'))
      : notice('Couldn’t load the photo list',
        h('p', {}, 'data.json is missing or unreadable. If you just deployed, wait a minute and reload; otherwise check the build log.')));
    return;
  }
  albums = new Map(data.albums.map((a) => [a.slug, a]));
  initAbout(data.site);
  if (data.site.author) $('#foot').textContent = `© ${new Date().getFullYear()} ${data.site.author}`;
  addEventListener('hashchange', () => route(true));
  route(false);
}

init();
