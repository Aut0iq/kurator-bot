"use strict";

const tg = window.Telegram?.WebApp;
try { tg?.ready(); tg?.expand(); tg?.setHeaderColor?.("secondary_bg_color"); tg?.disableVerticalSwipes?.(); } catch (_) {}


const IN_TG = !!(tg && tg.initData);
const NATIVE = window.KuratorApp || null;
if (!IN_TG) document.documentElement.classList.add("standalone");


const ACCENTS = {
  violet: { name: "Фиолетовый", a: ["#8b5cf6", "#6366f1", "#3b82f6"], c: "#6d5efc" },
  blue:   { name: "Синий",      a: ["#38bdf8", "#3b82f6", "#2563eb"], c: "#2f6cf6" },
  green:  { name: "Зелёный",    a: ["#34d399", "#10b981", "#059669"], c: "#0f9f76" },
  orange: { name: "Оранжевый",  a: ["#fbbf24", "#f97316", "#ef4444"], c: "#ef6c1a" },
  pink:   { name: "Розовый",    a: ["#f472b6", "#ec4899", "#d946ef"], c: "#e0428f" },
  graphite: { name: "Графит",   a: ["#94a3b8", "#64748b", "#334155"], c: "#55657d" },
};
const THEME_BG = { light: ["#ffffff", "#f2f3f7"], dark: ["#16171c", "#0b0c10"] };
const mqDark = window.matchMedia?.("(prefers-color-scheme: dark)");
function themePrefs() {
  let p = {};
  try { p = JSON.parse(localStorage.getItem("kb_theme") || "{}") || {}; } catch (_) {}
  return { mode: ["system", "light", "dark"].includes(p.mode) ? p.mode : "system", accent: ACCENTS[p.accent] ? p.accent : "violet" };
}
function applyTheme(p = themePrefs()) {
  const root = document.documentElement;

  const sysDark = IN_TG ? tg.colorScheme === "dark" : !!mqDark?.matches;
  const dark = p.mode === "dark" || (p.mode === "system" && sysDark);
  root.classList.toggle("dark", dark);
  if (IN_TG && p.mode === "system") root.removeAttribute("data-theme");
  else root.dataset.theme = dark ? "dark" : "light";
  const ac = ACCENTS[p.accent];
  if (p.accent === "violet") ["--a1", "--a2", "--a3", "--accent", "--link"].forEach(k => root.style.removeProperty(k));
  else {
    ac.a.forEach((c, i) => root.style.setProperty("--a" + (i + 1), c));
    root.style.setProperty("--accent", ac.c);
    root.style.setProperty("--link", dark ? `color-mix(in srgb, ${ac.c} 70%, #fff)` : ac.c);
  }
  root.dataset.accent = p.accent;
  try {
    if (IN_TG && p.mode !== "system") { tg.setHeaderColor?.(THEME_BG[dark ? "dark" : "light"][1]); tg.setBackgroundColor?.(THEME_BG[dark ? "dark" : "light"][1]); }
    else if (IN_TG) { tg.setHeaderColor?.("secondary_bg_color"); tg.setBackgroundColor?.("secondary_bg_color"); }
  } catch (_) {}
  try { NATIVE?.setDark?.(dark); } catch (_) {}
}
function setThemePrefs(patch) {
  const p = Object.assign(themePrefs(), patch);
  try { localStorage.setItem("kb_theme", JSON.stringify(p)); } catch (_) {}
  document.documentElement.classList.add("theme-anim");
  applyTheme(p);
  setTimeout(() => document.documentElement.classList.remove("theme-anim"), 450);
  return p;
}
applyTheme();
mqDark?.addEventListener?.("change", () => applyTheme());
try { tg?.onEvent?.("themeChanged", () => applyTheme()); } catch (_) {}
const AUTH = {
  get() { try { return NATIVE?.getToken?.() || localStorage.getItem("kb_token") || ""; } catch (_) { return ""; } },
  set(t) { try { NATIVE?.setToken?.(t); } catch (_) {} try { localStorage.setItem("kb_token", t); } catch (_) {} },
  clear() { try { quick.clear(); } catch (_) {} try { NATIVE?.setToken?.(""); } catch (_) {} try { localStorage.removeItem("kb_token"); } catch (_) {} },
};
function openLink(url) {
  if (IN_TG && /^https:\/\/t\.me\//.test(url)) { try { return tg.openTelegramLink(url); } catch (_) {} }
  if (IN_TG) { try { return tg.openLink(url); } catch (_) {} }
  if (NATIVE?.openExternal) return NATIVE.openExternal(url);
  window.open(url, "_blank") || (location.href = url);
}

function goToBotChat() {
  if (IN_TG) { try { tg.close(); } catch (_) {} return; }
  if (S.me?.bot) openLink((NATIVE ? "tg://resolve?domain=" : "https://t.me/") + S.me.bot);
}

const WD = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
const WDS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"];
const MONTHS_G = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const ST = { P: "На паре", L: "Опоздал", A: "Не был", E: "Уважит.", N: "Не ответил" };
const ST_SHORT = { P: "✓", L: "О", A: "Н", E: "У", N: "—" };
const PARITY = ["Каждую неделю", "Только нечётная", "Только чётная"];
const PERIODS = { holiday: "Каникулы", session: "Сессия", practice: "Практика" };
const KINDS = ["Лекция", "Практика", "Семинар", "Лабораторная", "Зачёт", "Экзамен", "Консультация"];
const KIND_SHORT = { "Лекция": "Лек", "Практика": "Пр", "Семинар": "Сем", "Лабораторная": "Лаб", "Зачёт": "Зач", "Экзамен": "Экз", "Консультация": "Конс" };

const S = { me: null, tab: "home", sub: null, statsDays: 30, journalMonth: null, journalDate: null };
const $app = document.getElementById("app");


const ICON_PATHS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  calendar: "M8 2v4M16 2v4M3 9h18M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
  journal: "M8 2v4M16 2v4M3 9h18M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM8 14l2.5 2.5L16 12",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  more: "M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM19 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM5 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  chart: "M3 3v18h18M7 15v2M12 10v7M17 6v11",
  alert: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  mega: "M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13",
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  check: "M20 6 9 17l-5-5", x: "M18 6 6 18M6 6l12 12", plus: "M12 5v14M5 12h14",
  right: "m9 18 6-6-6-6", left: "m15 18-6-6 6-6", down: "m6 9 6 6 6-6",
  share: "M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  pin: "M12 17v5M9 10.8V5h6v5.8l3 3.2v1H6v-1z",
  trash: "M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  key: "M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4",
  sparkles: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z",
  help: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  link: "M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7",
  copy: "M20 9h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
  refresh: "M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15",
  palm: "M12 22v-9M12 13c0-4-3-7-8-7 2 0 5 1 6 3M12 13c0-4 3-7 8-7-2 0-5 1-6 3M12 9c-1-3-4-5-7-5M12 9c1-3 4-5 7-5",
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  table: "M3 3h18v18H3zM3 9h18M3 15h18M9 3v18",
  mobile: "M8 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM11 18h2",
  phone: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z",
  award: "M12 15a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM8.2 13.9 7 23l5-3 5 3-1.2-9.1",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  server: "M4 3h16a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM4 13h16a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1zM7 7h.01M7 17h.01M11 7h6M11 17h6",
};
function icon(name, cls = "") {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "i " + cls);
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", ICON_PATHS[name] || ICON_PATHS.help);
  svg.append(p);
  return svg;
}


function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;
    else if (k === "d") el.style.setProperty("--d", v);
    else if (k in el && k !== "list" && k !== "type") el[k] = v;
    else el.setAttribute(k, v);
  }
  append(el, kids);
  return el;
}
function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
function mount(anim, ...kids) {
  $app.replaceChildren();
  append($app, kids);
  if (S.flip) pageIn();
  else if (anim) { $app.classList.remove("view-slide-l", "view-slide-r", "fade"); void $app.offsetWidth; $app.classList.add(anim); }
  let i = 0;
  for (const el of $app.querySelectorAll(".rise")) if (!el.style.getPropertyValue("--d")) el.style.setProperty("--d", Math.min(i++, 12));
}

const can = (...p) => p.some(x => (S.me?.perms || []).includes(x));
const isStaff = () => can("journal", "attendance");
const vib = ms => { try { NATIVE?.vibrate?.(ms); } catch (_) {} };
const haptic = (t = "light") => { if (!IN_TG) return vib(t === "heavy" ? 25 : 12); try { tg?.HapticFeedback?.impactOccurred(t); } catch (_) {} };
const notify = (t = "success") => { if (!IN_TG) return vib(t === "error" ? 60 : 20); try { tg?.HapticFeedback?.notificationOccurred(t); } catch (_) {} };
const selTick = () => { if (!IN_TG) return vib(6); try { tg?.HapticFeedback?.selectionChanged(); } catch (_) {} };
const store = {
  get(k, d) { try { const v = localStorage.getItem("kb_" + k); return v == null ? d : JSON.parse(v); } catch (_) { return d; } },
  set(k, v) { try { localStorage.setItem("kb_" + k, JSON.stringify(v)); } catch (_) {} },
};


document.addEventListener("pointerdown", e => {
  const b = e.target.closest(".btn, .qa, .answer, .chip");
  if (!b) return;
  const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height);
  const dot = h("span", { class: "ripple", style: `width:${s}px;height:${s}px;left:${e.clientX - r.left - s / 2}px;top:${e.clientY - r.top - s / 2}px` });
  if (getComputedStyle(b).position === "static") b.style.position = "relative";
  b.style.overflow = "hidden";
  b.append(dot); setTimeout(() => dot.remove(), 600);
});


function toast(msg, ic = null) {
  const t = document.getElementById("toast");
  t.replaceChildren(...(ic ? [icon(ic, "sm")] : []), document.createTextNode(msg));
  t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 2600);
}


const QUICK = /^\/(me|day\?|live|announcements|homework$|achievements)/;
const quickKey = () => {
  if (S.demoToken) return null;
  const who = IN_TG ? (tg.initDataUnsafe?.user?.id || "") : AUTH.get().slice(-12);
  return who ? "kb_q_" + who : null;
};
const quick = {
  all() { try { return JSON.parse(localStorage.getItem(quickKey()) || "{}"); } catch (_) { return {}; } },
  get(path) { if (!quickKey()) return null; return this.all()[path] || null; },
  set(path, data) {
    const k = quickKey(); if (!k) return;
    try { const all = this.all(); all[path] = data; localStorage.setItem(k, JSON.stringify(all)); } catch (_) {}
  },
  clear() { try { Object.keys(localStorage).filter(x => x.startsWith("kb_q_")).forEach(x => localStorage.removeItem(x)); } catch (_) {} },
};


async function api(path, opts = {}) {
  const isGet = !opts.body && (!opts.method || opts.method === "GET");
  if (S.fromCache && !opts.fresh && isGet && QUICK.test(path)) { const c = quick.get(path); if (c) return JSON.parse(JSON.stringify(c)); }
  const res = await fetch("/api" + path, {
    method: opts.method || (opts.body ? "POST" : "GET"),
    headers: Object.assign({ "Content-Type": "application/json", "ngrok-skip-browser-warning": "1" },
      S.demoToken ? { Authorization: "Bearer " + S.demoToken }
        : IN_TG ? { "X-Init-Data": tg.initData } : (AUTH.get() ? { Authorization: "Bearer " + AUTH.get() } : {})),
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (_) { if (!res.ok) data = { error: "Сервер недоступен" }; }
  if (res.status === 401 && S.demoToken) { S.demoToken = null; setTimeout(() => boot(), 0); }
  else if (res.status === 401 && !IN_TG && !path.startsWith("/applogin") && !path.startsWith("/auth/")) { AUTH.clear(); setTimeout(() => boot(), 0); }
  if (res.status === 423 && data.locked) { setTimeout(() => renderLocked(data.error), 0); }
  if (res.status === 426 && data.update) { setTimeout(() => renderUpdate(data.error), 0); }
  if (!res.ok) { const e = new Error(data.error || "Ошибка " + res.status); e.status = res.status; throw e; }
  if (isGet && QUICK.test(path)) quick.set(path, data);
  return data;
}

function authHeaders() {
  return S.demoToken ? { Authorization: "Bearer " + S.demoToken }
    : IN_TG ? { "X-Init-Data": tg.initData } : (AUTH.get() ? { Authorization: "Bearer " + AUTH.get() } : {});
}
async function apiUpload(path, fields, file) {
  const fd = new FormData();
  Object.entries(fields || {}).forEach(([k, v]) => fd.append(k, v));
  fd.append("file", file);
  const res = await fetch("/api" + path, { method: "POST", headers: Object.assign({ "ngrok-skip-browser-warning": "1" }, authHeaders()), body: fd });
  const data = await res.json().catch(() => ({ error: "Ошибка " + res.status }));
  if (!res.ok) { const e = new Error(data.error || "Ошибка " + res.status); e.status = res.status; throw e; }
  return data;
}
async function downloadFile(path, fallback = "file") {
  if (NATIVE?.openExternal) {
    const tok = S.demoToken || AUTH.get() || "";
    NATIVE.openExternal(location.origin + "/api" + path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(tok));
    return fallback;
  }
  const res = await fetch("/api" + path, { headers: Object.assign({ "ngrok-skip-browser-warning": "1" }, authHeaders()) });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || "Ошибка " + res.status); }
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  const name = decodeURIComponent(m ? (m[1] || m[2]) : fallback);
  const url = URL.createObjectURL(await res.blob());
  const a = h("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return name;
}

function pickFile(accept) {
  return new Promise(resolve => {
    const inp = h("input", { type: "file", accept, style: "display:none" });
    inp.onchange = () => resolve(inp.files[0] || null);
    document.body.append(inp); inp.click(); setTimeout(() => inp.remove(), 60000);
  });
}
async function safe(fn, btn) {
  let old;
  if (btn) { old = [...btn.childNodes]; btn.disabled = true; btn.replaceChildren(h("span", { class: "spin" })); }
  try { return await fn(); }
  catch (e) { toast(e.message, "alert"); notify("error"); throw e; }
  finally { if (btn) { btn.disabled = false; btn.replaceChildren(...old); } }
}

const act = fn => e => { const b = e.currentTarget; safe(() => fn(b), b).catch(() => {}); };


const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseIso = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (s, n) => { const d = parseIso(s); d.setDate(d.getDate() + n); return iso(d); };
const wdOf = s => (parseIso(s).getDay() + 6) % 7;
const fmtDate = s => { const d = parseIso(s); return `${d.getDate()} ${MONTHS_G[d.getMonth()]}`; };
const fmtDateLong = s => `${WD[wdOf(s)]}, ${fmtDate(s)}`;
const short = s => s.slice(8) + "." + s.slice(5, 7);
const toMin = t => { const [a, b] = t.split(":").map(Number); return a * 60 + b; };
const plural = (n, a, b, c) => { const m = n % 10, mm = n % 100; return m === 1 && mm !== 11 ? a : m >= 2 && m <= 4 && (mm < 10 || mm >= 20) ? b : c; };
const initials = name => name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase();
const groupMark = name => (name.match(/[A-Za-zА-Яа-яЁё0-9]/g) || ["Г"]).slice(0, 2).join("").toUpperCase();
const hue = s => { let x = 0; for (const c of s) x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const ava = name => h("div", { class: "ava", style: `background:linear-gradient(135deg,hsl(${hue(name)} 70% 62%),hsl(${(hue(name) + 40) % 360} 70% 52%))` }, initials(name));

const WELCOME = (() => {
  const t0 = performance.now();
  let el = document.getElementById("welcome");
  if (!el) {
    el = document.createElement("div");
    el.id = "welcome";
    el.innerHTML = '<div class="wl-glow"></div><div class="wl-logo"><img src="/static/logo.webp" alt="" width="128" height="128"></div>' +
      '<div class="wl-name">Куратор <b>+</b></div><div class="wl-hello">&nbsp;</div><div class="wl-dots"><i></i><i></i><i></i></div>';
    document.body.append(el);
  }
  let done = false;
  const finish = name => {
    if (done) return;
    done = true;
    el.querySelector(".wl-hello").textContent = name ? `${greeting()}, ${name}!` : "Добро пожаловать!";
    el.classList.add("hi");

    const again = store.get("seen_welcome", 0);
    const wait = Math.max(0, (again ? 350 : 900) - (performance.now() - t0)) + (again ? 450 : 700);
    store.set("seen_welcome", 1);
    setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 550); }, wait);
  };
  setTimeout(() => finish(null), 7000);
  return { finish };
})();

const greeting = () => { const hr = new Date().getHours(); return hr < 5 ? "Доброй ночи" : hr < 12 ? "Доброе утро" : hr < 18 ? "Добрый день" : "Добрый вечер"; };


function countUp(el, to, suffix = "", dur = 900, dec = null) {
  const from = 0, t0 = performance.now();
  if (dec == null) dec = String(to).includes(".") ? 1 : 0;
  const fmt = v => (dec === 2 ? v.toFixed(2).replace(".", ",") : v.toFixed(dec)) + suffix;
  const step = t => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  return el;
}


let sheetStack = [];
function openSheet(...kids) {
  const body = h("div", { class: "sheet-body" }, h("div", { class: "grabber" }), kids);
  const wrap = h("div", { class: "sheet" }, h("div", { class: "backdrop", onclick: () => closeSheet() }), body);
  document.body.append(wrap);
  sheetStack.push(wrap);

  let y0 = null, dy = 0;
  body.addEventListener("touchstart", e => { if (body.scrollTop <= 0) { y0 = e.touches[0].clientY; dy = 0; body.style.transition = "none"; } }, { passive: true });
  body.addEventListener("touchmove", e => { if (y0 == null) return; dy = Math.max(0, e.touches[0].clientY - y0); body.style.transform = `translateY(${dy}px)`; }, { passive: true });
  body.addEventListener("touchend", () => {
    if (y0 == null) return; body.style.transition = "transform .3s var(--ease)";
    if (dy > 110) closeSheet(); else body.style.transform = "";
    y0 = null;
  });
  try { tg?.BackButton?.show(); } catch (_) {}
  haptic("soft");
  return body;
}
function closeSheet() {
  const w = sheetStack.pop();
  if (!w) return;
  w.classList.add("closing");
  setTimeout(() => w.remove(), 260);
  if (!sheetStack.length) { try { tg?.BackButton?.hide(); } catch (_) {} if (S.sub) tg?.BackButton?.show(); }
}
function closeAllSheets() { while (sheetStack.length) closeSheet(); }
try { tg?.BackButton?.onClick(() => { if (sheetStack.length) closeSheet(); else if (S.sub) go(S.tab); }); } catch (_) {}

window.__appBack = () => {
  if (sheetStack.length) { closeSheet(); return true; }
  if (S.sub) { go(S.tab); return true; }
  if (S.tab === "journal" && S.journalDate) { S.journalDate = null; S.anim = "view-slide-r"; render(); return true; }
  if (S.me?.member && S.tab !== "home") { go("home"); return true; }
  return false;
};
function confirmDo(text, fn) {
  if (tg?.showConfirm && tg.platform !== "unknown") tg.showConfirm(text, ok => ok && fn());
  else if (confirm(text)) fn();
}


function confetti() {
  const c = document.getElementById("confetti"), ctx = c.getContext("2d");
  c.width = innerWidth * devicePixelRatio; c.height = innerHeight * devicePixelRatio; ctx.scale(devicePixelRatio, devicePixelRatio);
  const colors = ["#8b5cf6", "#6366f1", "#3b82f6", "#22c55e", "#f59e0b", "#ec4899"];
  const parts = Array.from({ length: 110 }, () => ({
    x: innerWidth / 2, y: innerHeight * .35, vx: (Math.random() - .5) * 13, vy: -Math.random() * 12 - 4,
    s: Math.random() * 7 + 4, r: Math.random() * 6, vr: (Math.random() - .5) * .4, c: colors[Math.random() * colors.length | 0],
  }));
  let t = 0;
  const step = () => {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    for (const p of parts) {
      p.vy += .35; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c; ctx.globalAlpha = Math.max(0, 1 - t / 110);
      ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); ctx.restore();
    }
    if (++t < 120) requestAnimationFrame(step); else ctx.clearRect(0, 0, innerWidth, innerHeight);
  };
  step();
}


function ring(parts, total, label, sub) {
  const ns = "http://www.w3.org/2000/svg", R = 44, C = 2 * Math.PI * R;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  const bg = document.createElementNS(ns, "circle");
  Object.entries({ cx: 50, cy: 50, r: R, stroke: "var(--soft)" }).forEach(([k, v]) => bg.setAttribute(k, v));
  svg.append(bg);
  let off = 0;
  const segs = [];
  for (const [color, n] of parts) {
    if (!n || !total) continue;
    const len = C * n / total;
    const c = document.createElementNS(ns, "circle");
    Object.entries({ cx: 50, cy: 50, r: R, stroke: color, class: "seg", "stroke-dasharray": `0 ${C}`, "stroke-dashoffset": -off }).forEach(([k, v]) => c.setAttribute(k, v));
    segs.push([c, len]);
    svg.append(c);
    off += len;
  }
  requestAnimationFrame(() => requestAnimationFrame(() => segs.forEach(([c, len]) => c.setAttribute("stroke-dasharray", `${Math.max(0, len - 1.2)} ${C}`))));
  const lbl = h("div", { class: "lbl" }, h("b", { class: "num" }, label), h("span", {}, sub));
  return h("div", { class: "ring" }, svg, lbl);
}


function sparkline(values) {
  const ns = "http://www.w3.org/2000/svg", W = 300, H = 70, P = 6;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("preserveAspectRatio", "none"); svg.setAttribute("class", "spark");
  if (values.length < 2) return svg;
  const min = Math.min(...values, 50), max = 100;
  const pts = values.map((v, i) => [P + i * (W - 2 * P) / (values.length - 1), H - P - (v - min) / Math.max(1, max - min) * (H - 2 * P)]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  svg.innerHTML = `<defs><linearGradient id="sparkfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6366f1" stop-opacity=".28"/><stop offset="1" stop-color="#6366f1" stop-opacity="0"/></linearGradient></defs>
    <path class="area" d="${d} L ${pts.at(-1)[0]} ${H} L ${pts[0][0]} ${H} Z"/><path class="line" d="${d}"/>`;
  return svg;
}


const skeleton = (...hs) => mount("fade", h("div", { style: "height:18px" }), hs.map((x, i) => h("div", { class: "sk", style: `height:${x}px;margin-bottom:12px;opacity:${1 - i * .12}` })));


function tabsFor() {
  return isStaff()
    ? [["home", "home", "Главная"], ["journal", "journal", "Журнал"], ["schedule", "calendar", "Расписание"], ["students", "users", "Студенты"], ["more", "settings", "Ещё"]]
    : [["home", "home", "Главная"], ["schedule", "calendar", "Расписание"], ["grades", "award", "Оценки"], ["stats", "chart", "Пропуски"], ["more", "settings", "Ещё"]];
}
function renderTabs() {
  const nav = document.getElementById("tabs");
  const tabs = tabsFor();
  const ind = h("div", { class: "ind" });
  const btns = tabs.map(([id, ic, name]) => h("button", { class: S.tab === id ? "on" : "", "data-tab": id, onclick: () => { selTick(); go(id); } }, icon(ic), name));
  nav.replaceChildren(ind, ...btns);
  nav.classList.remove("hidden");
  requestAnimationFrame(() => moveInd(false));
}
function moveInd(animate = true) {
  const nav = document.getElementById("tabs"), ind = nav.querySelector(".ind"), on = nav.querySelector("button.on");
  if (!ind || !on) { if (ind) ind.style.opacity = 0; return; }
  if (!animate) ind.style.transition = "none";
  ind.style.opacity = 1;
  ind.style.width = on.offsetWidth + "px";
  ind.style.transform = `translateX(${on.offsetLeft - 6}px)`;
  if (!animate) requestAnimationFrame(() => (ind.style.transition = ""));
}

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const FLIP_EASE = "cubic-bezier(.25, .8, .25, 1)";
const pageTilt = dx => (-dx / innerWidth) * 16;
const pageTf = (dx, deg = pageTilt(dx)) => `perspective(1400px) translateX(${dx}px) rotateY(${deg}deg)`;
let flipGuard = null;
function pageOut(dir, dx = 0) {
  if (REDUCED || !$app.firstChild) return;
  document.querySelectorAll(".page-ghost").forEach(g => g.remove());
  const r = $app.getBoundingClientRect(), cs = getComputedStyle($app);
  const g = $app.cloneNode(true);
  g.removeAttribute("id"); g.className = "page-ghost";
  Object.assign(g.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", padding: cs.padding, transform: "", opacity: "" });
  document.body.append(g);
  $app.getAnimations().forEach(a => a.cancel());
  $app.classList.remove("view-slide-l", "view-slide-r", "fade");
  $app.style.transition = ""; $app.style.transform = ""; $app.style.opacity = "";
  $app.style.visibility = "hidden";
  const W = innerWidth;
  g.animate([{ transform: pageTf(dx), opacity: 1 }, { transform: pageTf(-dir * W, dir * 28), opacity: .15 }],
    { duration: 380, easing: FLIP_EASE, fill: "forwards" }).onfinish = () => g.remove();
  setTimeout(() => g.remove(), 900);
  S.flip = { dir };
  clearTimeout(flipGuard);
  flipGuard = setTimeout(() => { if (S.flip) { S.flip = null; $app.style.visibility = ""; } }, 4000);
}
function pageIn() {
  const { dir } = S.flip; S.flip = null; clearTimeout(flipGuard);
  $app.classList.remove("view-slide-l", "view-slide-r", "fade");
  $app.style.visibility = "";
  scrollTo(0, 0);
  const W = innerWidth;
  $app.animate([{ transform: pageTf(dir * W * .8, -dir * 28), opacity: .15 }, { transform: pageTf(0, 0), opacity: 1 }],
    { duration: 400, easing: FLIP_EASE });
}
const ORDER = ["home", "journal", "schedule", "grades", "students", "stats", "files", "more"];
function go(tab, sub = null, opts = {}) {
  const prev = S.tab, prevSub = S.sub;
  S.tab = tab; S.sub = sub;
  closeAllSheets();
  const nav = document.getElementById("tabs");
  nav.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  moveInd();
  const dir = ORDER.indexOf(tab) >= ORDER.indexOf(prev) ? "view-slide-l" : "view-slide-r";
  S.anim = sub ? "view-slide-l" : (prev === tab ? (prevSub ? "view-slide-r" : "fade") : dir);

  const ids = tabsFor().map(t => t[0]);
  let fdir = 0;
  if (sub && sub !== prevSub) fdir = 1;
  else if (!sub && prevSub && prev === tab) fdir = -1;
  else if (!sub && prev !== tab && ids.includes(prev) && ids.includes(tab)) fdir = ids.indexOf(tab) > ids.indexOf(prev) ? 1 : -1;
  if (fdir) pageOut(fdir, opts.dx || 0);
  try { sub ? tg?.BackButton?.show() : tg?.BackButton?.hide(); } catch (_) {}
  render();
}

(function swipeTabs() {
  let x0, y0, t0, axis = null, dx = 0, active = false;

  const blocked = el => {
    for (; el && el !== document.body; el = el.parentElement) {
      if (el.matches?.("input, textarea, select, [contenteditable], [data-noswipe], .sheet")) return true;
      if (el.scrollWidth > el.clientWidth + 2 && /(auto|scroll)/.test(getComputedStyle(el).overflowX)) return true;
    }
    return false;
  };
  const neighbor = d => {
    const ids = tabsFor().map(t => t[0]), i = ids.indexOf(S.tab);
    return i < 0 ? null : ids[i + d] || null;
  };
  const reset = (anim = true) => {
    $app.style.transition = anim ? "transform .25s var(--ease), opacity .25s" : "";
    $app.style.transform = ""; $app.style.opacity = "";
    if (anim) setTimeout(() => ($app.style.transition = ""), 260);
  };
  document.addEventListener("touchstart", e => {
    active = false;
    if (e.touches.length !== 1 || sheetStack.length || document.getElementById("tabs").classList.contains("hidden")) return;
    const t = e.touches[0];
    if (t.clientX < 18 || t.clientX > innerWidth - 18) return;
    if (blocked(e.target)) return;
    x0 = t.clientX; y0 = t.clientY; t0 = Date.now(); axis = null; dx = 0; active = true;
  }, { passive: true });
  document.addEventListener("touchmove", e => {
    if (!active) return;
    const t = e.touches[0], mx = t.clientX - x0, my = t.clientY - y0;
    if (!axis) {
      if (Math.abs(mx) < 10 && Math.abs(my) < 10) return;
      axis = Math.abs(mx) > Math.abs(my) * 1.4 ? "x" : "y";
      if (axis === "y") { active = false; return; }
      $app.classList.remove("view-slide-l", "view-slide-r", "fade");
    }
    dx = mx;

    const target = S.sub ? (dx > 0 ? S.tab : null) : neighbor(dx < 0 ? 1 : -1);
    const k = target ? 1 : .15;
    $app.style.transition = "none";
    $app.style.transform = REDUCED ? `translateX(${dx * k * .4}px)` : pageTf(dx * k);
    $app.style.opacity = String(1 - Math.min(Math.abs(dx) / innerWidth, .6) * (target ? .9 : 0));
  }, { passive: true });
  const end = () => {
    if (!active || axis !== "x") { active = false; return; }
    active = false;
    const fast = Math.abs(dx) > 40 && Date.now() - t0 < 250;
    if (Math.abs(dx) < Math.min(90, innerWidth * .22) && !fast) return reset();
    const target = S.sub ? (dx > 0 ? S.tab : null) : neighbor(dx < 0 ? 1 : -1);
    if (!target) return reset();
    selTick();
    go(target, null, { dx });
  };
  document.addEventListener("touchend", end, { passive: true });
  document.addEventListener("touchcancel", () => { if (active && axis === "x") reset(); active = false; }, { passive: true });
})();

function render() {
  document.querySelectorAll(".fab").forEach(f => f.remove());
  const views = {
    home: renderHome, journal: renderJournal, schedule: renderSchedule, students: renderStudents,
    stats: renderStats, files: renderFiles, more: renderMore, grades: renderGrades,
  };
  const sub = { truancy: renderTruancy, announcements: renderAnnouncements, files: renderFiles, stats: renderStats, settings: renderSettings, periods: renderPeriods, grades: renderGrades, server: renderServer, online: renderOnline,
    homework: renderHomework, audit: renderAudit, staff: renderStaffAccounts, badges: renderBadges };
  const fn = (S.sub && sub[S.sub]) || views[S.tab] || renderHome;
  Promise.resolve(fn()).catch(e => { console.error(e); mount("fade", h("div", { class: "empty" }, h("b", {}, "Не удалось загрузить"), e.message)); });
}
function fab(ic, onclick) { document.querySelectorAll(".fab").forEach(f => f.remove()); document.body.append(h("button", { class: "fab", onclick }, icon(ic, "lg"))); }
function pageTitle(title, ...right) {
  return [S.sub ? h("button", { class: "back", onclick: () => go(S.tab) }, icon("left", "sm"), "Назад") : null,
    h("div", { class: "page-title rise" }, h("h1", { class: "grow" }, title), right)];
}
const empty = (ic, title, text, ...extra) => h("div", { class: "empty rise" }, h("div", { class: "big-ic" }, icon(ic)), h("b", {}, title), text, extra);


async function boot(refresh = false) {
  if (!refresh && !introSeen()) { WELCOME.finish(null); document.getElementById("tabs").classList.add("hidden"); return renderIntro(() => boot()); }
  if (!IN_TG && !AUTH.get() && !S.demoToken) { WELCOME.finish(null); document.getElementById("tabs").classList.add("hidden"); return renderLogin(); }

  const cachedMe = !refresh && !S.demoToken ? quick.get("/me") : null;
  if (cachedMe?.member && cachedMe.consent && cachedMe.today === iso(new Date())) {
    S.me = cachedMe; S.fromCache = true;
    if (showMain(false)) {
      WELCOME.finish((S.me.user?.first_name || "").trim());
      return refreshFromServer();
    }
    S.fromCache = false;
  }
  if (!refresh) skeleton(90, 220, 140, 140);
  try { S.me = await api("/me"); }
  catch (e) { WELCOME.finish(null); if (e.status === 423 || e.status === 426) return; return mount("fade", empty("alert", "Нет связи с сервером", e.message, h("div", { class: "btns" }, h("button", { class: "btn", onclick: () => boot() }, "Повторить")))); }
  WELCOME.finish((S.me.user?.first_name || "").trim());
  if (!S.me.consent) { document.getElementById("tabs").classList.add("hidden"); return renderConsent(); }
  if (S.me.parent !== undefined) return S.me.parent ? renderParent() : mount("fade", empty("user", "Запись студента удалена", "Обратитесь к старосте или куратору группы", h("div", { class: "btns" }, h("button", { class: "btn", onclick: logoutApp }, "Выйти"))));
  if (!S.me.member) { document.getElementById("tabs").classList.add("hidden"); return renderOnboarding(); }
  if (S.me.member.role === "student" && !isStaff() && !S.me.student) { document.getElementById("tabs").classList.add("hidden"); return renderRegister(); }
  showMain(refresh);
}

function showMain(refresh) {
  if (!S.me?.member || (S.me.member.role === "student" && !isStaff() && !S.me.student)) return false;
  const hash = location.hash.replace("#", "");
  if (!refresh && hash && tabsFor().some(t => t[0] === hash)) S.tab = hash;
  if (!refresh && hash === "files") { S.tab = "home"; S.sub = "files"; }
  if (!refresh && hash === "grades" && isStaff()) { S.tab = "home"; S.sub = "grades"; }
  if (!refresh && ["homework", "announcements", "badges"].includes(hash)) { S.tab = "home"; S.sub = hash; }
  if (!tabsFor().some(t => t[0] === S.tab)) S.tab = "home";
  renderTabs();
  S.anim = "fade";
  render();
  lockBadge();
  demoBadge();
  if (!S.fromCache) {
    reportNativeCrash();
    syncNativePush();
    if (NATIVE && !S.updChecked) { S.updChecked = true; setTimeout(() => checkUpdates(true), 2500); }
  }
  return true;
}

async function refreshFromServer() {
  await new Promise(r => setTimeout(r, 30));
  let fresh;
  try { fresh = await api("/me", { fresh: true }); }
  catch (e) { S.fromCache = false; if (e.status === 401 || e.status === 423 || e.status === 426) return; return; }
  S.fromCache = false;
  const sameShape = fresh.member && fresh.consent && fresh.member.role === S.me.member.role &&
    JSON.stringify(fresh.perms) === JSON.stringify(S.me.perms) && !!fresh.student === !!S.me.student;
  S.me = fresh;
  if (!sameShape) return boot(true);
  if (sheetStack.length) { showMainExtras(); return; }
  const y = scrollY;
  $app.classList.add("srv-quiet");
  S.anim = null;
  render();
  setTimeout(() => { scrollTo(0, y); $app.classList.remove("srv-quiet"); }, 900);
  showMainExtras();
}
function showMainExtras() {
  lockBadge(); demoBadge(); reportNativeCrash(); syncNativePush();
  if (NATIVE && !S.updChecked) { S.updChecked = true; setTimeout(() => checkUpdates(true), 2500); }
}


const appVer = () => (NATIVE?.version?.() || "");
async function appInfo() { return api("/app-info"); }
function startUpdate(info, status) {
  const url = location.origin + (info.url || "/app.apk");
  if (NATIVE?.installUpdate) {
    if (status) status.textContent = "Скачиваю…";
    NATIVE.installUpdate(url);
  } else if (NATIVE?.openExternal) {
    NATIVE.openExternal(url);
    if (status) status.textContent = "Файл скачивается в браузере. Откройте его из уведомления или «Загрузок» и нажмите «Установить», затем запустите приложение снова.";
  } else openLink(url);
}


const RING_R = 86, RING_C = 2 * Math.PI * RING_R;
let UPD = null;
window.__appUpdate = (state, pct) => {
  if (!UPD) return;
  UPD.set(state, pct);
};
function updatePage(info, { forced = false, text = "" } = {}) {
  closeAllSheets();
  document.querySelectorAll(".fab, .lock-badge, .demo-badge").forEach(f => f.remove());
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 200 200"); svg.setAttribute("class", "upd-ring");
  svg.innerHTML = `<defs><linearGradient id="updg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#34d399"/><stop offset=".5" stop-color="#60a5fa"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient></defs>
    <circle cx="100" cy="100" r="${RING_R}" class="track"/><circle cx="100" cy="100" r="${RING_R}" class="bar" stroke-dasharray="${RING_C}" stroke-dashoffset="${RING_C}"/>`;
  const bar = svg.querySelector(".bar");
  const pctEl = h("div", { class: "upd-pct num" });
  const check = h("div", { class: "upd-check" }, h("span"));
  const stage = h("div", { class: "upd-stage" });
  const sub = h("div", { class: "upd-sub muted" });
  const btn = h("button", { class: "btn block upd-go", onclick: () => go() }, icon("download", "sm"), `Обновить до ${info.version_name || "новой версии"}`);
  const later = forced ? null : h("button", { class: "back", style: "margin-top:12px;color:var(--hint)", onclick: () => { UPD = null; render(); renderTabs(); } }, "Не сейчас");
  const steps = h("div", { class: "upd-steps" });
  const page = h("div", { class: "upd-page" },
    h("div", { class: "upd-blob b1" }), h("div", { class: "upd-blob b2" }), h("div", { class: "upd-blob b3" }),
    h("div", { class: "upd-wrap" },
      h("div", { class: "upd-badge" }, forced ? "Требуется обновление" : "Доступно обновление"),
      h("div", { class: "upd-hero" }, svg, h("div", { class: "upd-orbit" }, h("i"), h("i"), h("i")),
        h("img", { class: "upd-logo", src: "/static/logo.webp", alt: "" }), pctEl, check),
      h("h1", { class: "upd-title" }, forced ? "Обновите приложение" : "Новая версия «Куратор +»"),
      h("div", { class: "upd-ver" }, h("span", {}, info.installed?.name || appVer() || "старая"), h("b", {}, "→"), h("span", { class: "new" }, info.version_name || "новая"),
        info.size ? h("em", {}, fmtSize(info.size)) : null),
      stage, sub,
      info.notes?.length ? h("div", { class: "upd-notes" }, h("div", { class: "upd-notes-t" }, "Что нового"),
        info.notes.map((n, i) => h("div", { class: "upd-note", style: `--i:${i}` }, h("span", {}, "✦"), n))) : null,
      steps,
      h("div", { class: "upd-actions" }, btn, later),
      h("p", { class: "upd-foot" }, forced ? (text || "Обновление ставится поверх — вход и данные сохранятся. Пока можно пользоваться ботом в Telegram.")
        : "Обновление ставится поверх — вход и данные сохранятся.")));
  const setRing = p => bar.setAttribute("stroke-dashoffset", String(RING_C * (1 - Math.max(0, Math.min(100, p)) / 100)));
  const LABEL = {
    idle: ["Готово к обновлению", "Займёт меньше минуты"],
    downloading: ["Скачиваю обновление…", "Не закрывайте приложение"],
    ready: ["Загружено", "Открываю установку"],
    permission: ["Нужно разрешение", "Разрешите установку из «Куратор +» и вернитесь назад — установка продолжится сама"],
    installing: ["Почти готово", "Нажмите «Обновить» в окне Android"],
    browser: ["Скачивается в браузере", "Дальше — три простых шага ниже"],
    error: ["Не удалось скачать", "Проверьте интернет и попробуйте ещё раз"],
  };
  const set = (state, pct = 0) => {
    page.dataset.state = state;
    const [t, d] = LABEL[state] || LABEL.idle;
    stage.textContent = t; sub.textContent = d;
    pctEl.textContent = state === "downloading" ? Math.round(pct) + "%" : "";
    setRing(state === "downloading" ? pct : ["ready", "installing", "permission", "browser"].includes(state) ? 100 : 0);
    btn.disabled = state === "downloading" || state === "ready";
    btn.lastChild.textContent = state === "error" ? "Попробовать ещё раз" : state === "installing" || state === "permission" ? "Открыть установку снова"
      : state === "browser" ? "Скачать ещё раз" : `Обновить до ${info.version_name || "новой версии"}`;
    if (state === "ready") haptic("medium");
  };
  const go = () => {
    const url = location.origin + (info.url || "/app.apk");
    if (NATIVE?.installUpdate) {
      if (page.dataset.state === "installing" || page.dataset.state === "permission") return NATIVE.installUpdate("");
      set("downloading", 0); NATIVE.installUpdate(url);
    } else {
      if (NATIVE?.openExternal) NATIVE.openExternal(url); else openLink(url);
      set("browser");
      steps.replaceChildren(...[["⬇️", "Дождитесь загрузки файла", "kurator.apk появится в уведомлениях"], ["📂", "Откройте файл", "из уведомления или «Загрузок»"],
        ["✅", "Нажмите «Установить»", "затем запустите приложение снова"]].map(([ic, t, d], i) =>
        h("div", { class: "upd-step", style: `--i:${i}` }, h("span", { class: "ic" }, ic), h("div", {}, h("b", {}, t), h("small", {}, d)))));
    }
    haptic("soft");
  };
  UPD = { set };
  document.getElementById("tabs").classList.add("hidden");
  mount("fade", page);
  set("idle");
}
const fmtSize = n => n > 1e6 ? (n / 1e6).toFixed(1).replace(".", ",") + " МБ" : Math.max(1, Math.round(n / 1e3)) + " КБ";
async function checkUpdates(silent = false) {
  let info;
  try { info = await appInfo(); } catch (e) { if (!silent) toast(e.message, "alert"); return; }
  const cur = info.installed?.name || appVer();
  if (!info.update_available) {
    if (!silent) openSheet(h("div", { class: "center", style: "padding:10px 0" }, h("img", { class: "brand-logo", src: "/static/logo.webp", width: 72, height: 72, alt: "" }),
      h("h3", { style: "margin:14px 0 4px" }, "У вас последняя версия"), h("div", { class: "muted" }, "«Куратор +» " + cur)));
    return;
  }
  if (silent) return toast(`Доступна версия ${info.version_name} — «Ещё → Проверить обновления»`, "download");
  updatePage(info);
}

async function renderUpdate(text) {
  WELCOME.finish(null);
  let info = {};
  try { info = await appInfo(); } catch (_) {}
  updatePage(info, { forced: true, text });
}


setInterval(() => { if (!document.hidden && S.me?.member) api("/ping").catch(() => {}); }, 60000);
document.addEventListener("visibilitychange", () => { if (!document.hidden && S.me?.member) api("/ping").catch(() => {}); });


function renderLocked(text) {
  WELCOME.finish(null);
  closeAllSheets();
  document.querySelectorAll(".fab, .lock-badge").forEach(f => f.remove());
  document.getElementById("tabs").classList.add("hidden");
  mount("fade", h("div", { class: "login" },
    h("div", { class: "login-art pop" }, h("div", { class: "avatar", style: "width:84px;height:84px;border-radius:26px;background:linear-gradient(135deg,#64748b,#334155)" }, icon("key", "lg"))),
    h("h1", { class: "rise" }, "Доступ временно закрыт"),
    h("p", { class: "muted rise" }, text || "Сервис временно закрыт. Попробуйте позже."),
    h("div", { class: "rise", style: "width:100%" }, h("button", { class: "btn block", onclick: act(async () => { await boot(); }) }, icon("refresh", "sm"), "Проверить снова"))));
}

function lockBadge() {
  document.querySelectorAll(".lock-badge").forEach(f => f.remove());
  if (!S.me?.super || !S.me.lock) return;
  document.body.append(h("button", { class: "lock-badge", onclick: () => openLockSheet() }, icon("key", "sm"), "Доступ закрыт для всех"));
}
async function openLockSheet() {
  const st = await safe(() => api("/lock"));
  const on = !!st.lock?.on;
  const text = h("textarea", { maxlength: 300, style: "min-height:80px", placeholder: "Например: Идёт обновление, бот заработает к 18:00" });
  text.value = st.lock?.text || "";
  const notifyBox = h("input", { type: "checkbox" });
  const apply = want => act(async () => {
    await api("/lock", { body: { on: want, text: text.value, notify: notifyBox.checked } });
    notify(want ? "warning" : "success"); closeSheet();
    toast(want ? "Доступ закрыт для всех, кроме вас" : "Доступ открыт", want ? "key" : "check");
    S.me.lock = want ? { text: text.value } : null; lockBadge(); if (S.sub === "server" || S.tab === "more") render();
  });
  openSheet(
    h("h3", {}, on ? "🔒 Доступ закрыт" : "Закрыть доступ всем"),
    h("p", { class: "muted small", style: "margin:6px 0 14px" }, on
      ? "Бот и приложение сейчас работают только для вас. Опросы и сводки на паузе."
      : `Бот и приложение перестанут работать для всех ${st.users ? "(" + st.users + " чел.)" : ""}, кроме главного куратора. Опросы и сводки встанут на паузу, данные сохранятся.`),
    h("label", { class: "f" }, "Что увидят пользователи"), text,
    h("label", { class: "item", style: "padding:14px 2px 0;cursor:pointer" }, h("div", { class: "grow" }, on ? "Сообщить всем в Telegram, что бот снова работает" : "Сообщить всем в Telegram"), h("span", { class: "switch" }, notifyBox, h("i"))),
    h("div", { class: "btns", style: "margin-top:10px" }, on
      ? h("button", { class: "btn block", onclick: apply(false) }, icon("check", "sm"), "Открыть доступ")
      : h("button", { class: "btn danger block", onclick: e => confirmDo("Закрыть доступ всем пользователям?", () => apply(true)(e)) }, icon("key", "sm"), "Закрыть доступ")),
    on ? h("div", { class: "btns" }, h("button", { class: "btn plain sm", onclick: apply(true) }, "Сохранить текст")) : null);
}


const INTRO_KEY = "kp_intro_v1";
function introSeen() { try { return localStorage.getItem(INTRO_KEY) === "1"; } catch (_) { return true; } }
function renderIntro(next) {
  const slides = [
    { ic: "bell", g: "linear-gradient(135deg,#8b5cf6,#6366f1)", c: "#6366f1", title: "Опрос перед каждой парой",
      text: "Бот сам спрашивает студентов «Будешь на паре?», а старосте присылает готовую сводку: кто пришёл, кто опаздывает, кто не придёт.",
      chips: ["✅ Буду", "⏰ Опоздаю", "❌ Не смогу"] },
    { ic: "table", g: "linear-gradient(135deg,#10b981,#0ea5e9)", c: "#10b981", title: "Журнал, расписание и оценки",
      text: "Чётные и нечётные недели, отметки в одно касание, оценки за месяц для каждого студента и отчёт в Excel для деканата.",
      chips: ["📅 Неделя", "📒 Оценки", "📥 Excel"] },
    { ic: "mobile", g: "linear-gradient(135deg,#1665f0,#4b3efa)", c: "#3b48f6", title: "Всегда под рукой",
      text: "Telegram, приложение для Android или браузер — один аккаунт и одни данные. Вход через Telegram, без паролей.",
      chips: ["Telegram", "Android", "Браузер"] },
  ];
  const last = slides.length - 1;
  let i = 0;
  const track = h("div", { class: "intro-track" }, slides.map(sl => h("div", { class: "intro-slide", style: `--g:${sl.g};--c:${sl.c}` },
    h("div", { class: "intro-art" }, h("div", { class: "intro-tile" }, icon(sl.ic, "lg")),
      sl.chips.map((t, k) => h("span", { class: "intro-chip", style: `--k:${k}` }, t))),
    h("h1", {}, sl.title), h("p", { class: "muted" }, sl.text))));
  const dots = h("div", { class: "intro-dots" }, slides.map((_, k) => h("i", { onclick: () => show(k) })));
  const btn = h("button", { class: "btn block", onclick: () => (i < last ? show(i + 1) : finish()) }, "Далее");
  const skip = h("button", { class: "intro-skip", onclick: () => finish() }, "Пропустить");
  const view = h("div", { class: "intro-view" }, track);
  function show(n, tick = true) {
    i = Math.max(0, Math.min(last, n));
    track.style.transition = ""; track.style.transform = `translateX(${-i * 100}%)`;
    [...track.children].forEach((x, k) => x.classList.toggle("on", k === i));
    [...dots.children].forEach((x, k) => x.classList.toggle("on", k === i));
    btn.textContent = i === last ? "Начать" : "Далее";
    skip.style.visibility = i === last ? "hidden" : "";
    if (tick) selTick();
  }
  function finish() { try { localStorage.setItem(INTRO_KEY, "1"); } catch (_) {} haptic("soft"); next(); }

  let x0 = null, dx = 0;
  view.addEventListener("touchstart", e => { x0 = e.touches[0].clientX; dx = 0; track.style.transition = "none"; }, { passive: true });
  view.addEventListener("touchmove", e => {
    if (x0 == null) return;
    dx = e.touches[0].clientX - x0;
    const edge = (i === 0 && dx > 0) || (i === last && dx < 0) ? .3 : 1;
    track.style.transform = `translateX(calc(${-i * 100}% + ${dx * edge}px))`;
  }, { passive: true });
  view.addEventListener("touchend", () => { if (x0 == null) return; x0 = null; show(Math.abs(dx) > 50 ? i + (dx < 0 ? 1 : -1) : i, Math.abs(dx) > 50); });
  mount("fade", h("div", { class: "intro" }, skip, view, dots, h("div", { class: "intro-btns" }, btn)));
  show(0, false);
}


function renderConsent() {
  const doc = name => h("a", { href: "/legal/" + name, onclick: e => { e.preventDefault(); e.stopPropagation(); openLink(location.origin + "/legal/" + name); } });
  const a = (name, text) => { const el = doc(name); el.textContent = text; return el; };
  const pd = h("input", { type: "checkbox" }), terms = h("input", { type: "checkbox" });
  const go = h("button", { class: "btn block", disabled: true, onclick: act(async () => {
    await api("/consent", { body: { pd: pd.checked, terms: terms.checked } }); notify(); boot(); }) }, "Продолжить");
  const upd = () => { go.disabled = !(pd.checked && terms.checked); selTick(); };
  pd.onchange = upd; terms.onchange = upd;
  mount("fade",
    h("div", { class: "login" },
      h("div", { class: "login-art pop" }, h("div", { class: "avatar", style: "width:84px;height:84px;border-radius:26px;font-size:30px" }, icon("shield", "lg"))),
      h("h1", { class: "rise" }, "Почти готово"),
      h("p", { class: "muted rise" }, "Бот хранит ФИО, отметки о посещаемости и оценки группы. Пожалуйста, ознакомьтесь с документами."),
      h("div", { class: "card rise consent" },
        h("label", { class: "consent-row" }, pd, h("span", {}, "Даю ", a("consent", "согласие на обработку персональных данных"),
          " (", a("privacy", "политика"), "). Мне есть 14 лет; если мне нет 18 — родитель не возражает")),
        h("label", { class: "consent-row" }, terms, h("span", {}, "Принимаю ", a("terms", "пользовательское соглашение")))),
      h("div", { class: "rise", style: "width:100%;margin-top:16px" }, go)));
}


let loginTimer = null;
function renderLogin(state = {}) {
  clearInterval(loginTimer);
  const waiting = !!state.code;
  if (!waiting) return renderLanding();
  const start = act(async () => {
    const r = await api("/applogin/start", { body: {} });
    renderLogin({ code: r.code, link: r.link, tg_link: r.tg_link });
    openLink(NATIVE ? r.tg_link : r.link);
  });
  mount("fade",
    h("div", { class: "login" },
      h("div", { class: "login-art pop" }, h("img", { class: "brand-logo", src: "/static/logo.webp", alt: "Куратор +", width: 96, height: 96 })),
      h("h1", { class: "rise" }, "Куратор +"),
      h("p", { class: "muted rise" }, "Опрос перед парой, журнал, оценки и расписание группы — в одном приложении"),
      waiting
        ? h("div", { class: "card rise center", style: "padding:22px 18px" },
            h("div", { class: "spin-lg" }),
            h("b", { style: "display:block;font-size:17px;margin-top:14px" }, "Подтвердите вход в Telegram"),
            h("p", { class: "muted small", style: "margin:6px 0 14px" }, "Бот прислал сообщение «Вход в приложение». Нажмите «Да, это я» и вернитесь сюда — всё откроется само."),
            h("div", { class: "btns" }, h("button", { class: "btn", onclick: () => openLink(NATIVE ? state.tg_link : state.link) }, icon("share", "sm"), "Открыть Telegram")),
            h("div", { class: "btns" }, h("button", { class: "btn plain sm", onclick: () => renderLogin() }, "Отмена")))
        : h("div", { class: "rise", style: "width:100%" },
            h("button", { class: "btn block tg-btn", onclick: start }, h("span", { class: "tg-logo" }), "Войти через Telegram"),
            h("button", { class: "btn ghost block", style: "margin-top:10px", onclick: () => renderPwLogin() }, icon("key", "sm"), "Войти по паролю"),
            h("p", { class: "muted tiny center", style: "margin-top:12px" }, "Пароль не нужен: бот спросит в Telegram, вы ли это. Аккаунт тот же, что и в боте — группа, роль и оценки сохранятся."),
            demoButton()),
      NATIVE?.resetServer ? h("button", { class: "back", style: "margin-top:26px;color:var(--hint)", onclick: () => NATIVE.resetServer() }, "Сменить адрес сервера") : null));
  if (waiting) {
    const t0 = Date.now();
    loginTimer = setInterval(async () => {
      if (Date.now() - t0 > 14 * 60 * 1000) { clearInterval(loginTimer); return renderLogin(); }
      try {
        const r = await api("/applogin/status?code=" + encodeURIComponent(state.code));
        if (r.status === "ok" && r.token) { clearInterval(loginTimer); AUTH.set(r.token); notify(); confetti(); boot(); }
        else if (r.status === "expired") { clearInterval(loginTimer); toast("Время входа истекло — попробуйте ещё раз", "alert"); renderLogin(); }
      } catch (_) {}
    }, 2000);
  }
}

function demoButton() {
  return h("div", { class: "demo-entry rise" },
    h("div", { class: "muted small" }, "Хотите сначала посмотреть, как всё устроено?"),
    h("button", { class: "btn ghost block", onclick: openDemoPicker }, icon("sparkles", "sm"), "Посмотреть демо"));
}
function openDemoPicker() {
  const go = role => act(async () => {
    const r = await api("/demo/start", { body: { role } });
    closeAllSheets(); S.demoToken = r.token; S.me = null; S.tab = "home"; S.sub = null; S.homeLoaded = false;
    notify(); toast("Демо-режим: можно всё смотреть, изменения не сохраняются", "sparkles"); boot();
  });
  openSheet(h("h3", {}, "Демо-режим"),
    h("p", { class: "muted small", style: "margin:4px 0 14px" }, "Выдуманная группа с расписанием, журналом, оценками и объявлениями. Смотреть можно всё, изменить ничего нельзя — реальные данные не затрагиваются."),
    h("div", { class: "list" },
      h("div", { class: "item tap", onclick: go("head") }, h("div", { class: "tile c1", style: "width:38px;height:38px;border-radius:12px;display:grid;place-items:center" }, icon("shield", "sm")),
        h("div", { class: "grow" }, h("b", {}, "Как староста"), h("div", { class: "muted tiny" }, "Журнал, отметки, статистика, переносы пар, кто в сети")), icon("right", "sm chev")),
      h("div", { class: "item tap", onclick: go("student") }, h("div", { class: "tile c5", style: "width:38px;height:38px;border-radius:12px;display:grid;place-items:center" }, icon("user", "sm")),
        h("div", { class: "grow" }, h("b", {}, "Как студент"), h("div", { class: "muted tiny" }, "Расписание, мои пропуски и оценки, объявления")), icon("right", "sm chev"))));
}
function demoBadge() {
  document.querySelectorAll(".demo-badge").forEach(f => f.remove());
  if (!S.demoToken) return;
  document.body.append(h("button", { class: "demo-badge", onclick: () => confirmDo("Выйти из демо-режима?", exitDemo) }, icon("sparkles", "sm"), "Демо · выйти"));
}
function exitDemo() {
  S.demoToken = null; S.me = null; S.tab = "home"; S.sub = null; S.homeLoaded = false;
  document.querySelectorAll(".demo-badge").forEach(f => f.remove());
  closeAllSheets(); boot();
}


function renderPwLogin(mode = "login", recordNo = "") {
  clearInterval(loginTimer);
  const first = mode === "set";
  const rec = h("input", { class: "rec-input", placeholder: "А-309 или ваш логин", autocomplete: "username", value: recordNo, autocapitalize: "none", spellcheck: false });
  const code = h("input", { placeholder: "6 цифр — от старосты, куратора или главного куратора", inputmode: "numeric", maxlength: 6, autocomplete: "one-time-code", style: "letter-spacing:4px;font-weight:700" });
  const pw = h("input", { type: "password", placeholder: first ? "Не короче 8 символов" : "Пароль", autocomplete: first ? "new-password" : "current-password" });
  const pw2 = h("input", { type: "password", placeholder: "Ещё раз", autocomplete: "new-password" });
  const eye = h("button", { class: "btn plain sm", style: "flex:0 0 auto", onclick: () => { const t = pw.type === "password" ? "text" : "password"; pw.type = t; pw2.type = t; } }, "👁");
  const submit = act(async () => {
    if (first && pw.value !== pw2.value) throw new Error("Пароли не совпадают");
    const r = first
      ? await api("/auth/set-password", { body: { login: rec.value, code: code.value, password: pw.value } })
      : await api("/auth/password", { body: { login: rec.value, password: pw.value } });
    AUTH.set(r.token); notify(); if (first) confetti(); S.me = null; boot();
  });
  const onEnter = e => { if (e.key === "Enter") submit({ currentTarget: e.target }); };
  [rec, code, pw, pw2].forEach(i => i.addEventListener("keydown", onEnter));
  mount("fade", h("div", { class: "login" },
    h("div", { class: "login-art pop" }, h("img", { class: "brand-logo", src: "/static/logo.webp", width: 84, height: 84, alt: "" })),
    h("h1", { class: "rise" }, first ? "Первый вход" : "Вход по паролю"),
    h("p", { class: "muted rise" }, first ? "Получите одноразовый код и придумайте пароль: студентам код выдаёт староста или куратор, старостам и кураторам — главный куратор. Этот же способ — если забыли пароль."
      : "Студенты — номер студенческого, старосты и кураторы — логин. Telegram не нужен."),
    h("div", { class: "card rise", style: "text-align:left" },
      h("label", { class: "f", style: "margin-top:0" }, "Номер студенческого или логин"), rec,
      first ? [h("label", { class: "f" }, "Одноразовый код"), code] : null,
      h("label", { class: "f" }, first ? "Новый пароль" : "Пароль"), h("div", { class: "row", style: "gap:6px" }, pw, eye),
      first ? [h("label", { class: "f" }, "Повторите пароль"), pw2] : null,
      h("div", { class: "btns" }, h("button", { class: "btn block", onclick: submit }, first ? "Сохранить пароль и войти" : "Войти"))),
    h("button", { class: "back", style: "margin-top:16px", onclick: () => renderPwLogin(first ? "login" : "set", rec.value) },
      first ? "У меня уже есть пароль — войти" : "Первый вход или забыли пароль?"),
    h("button", { class: "back", style: "margin-top:6px;color:var(--hint)", onclick: () => renderLogin() }, icon("left", "sm"), "Другие способы входа")));
  setTimeout(() => (recordNo ? (first ? code : pw) : rec).focus(), 300);
}

async function logoutApp() {
  if (S.demoToken) return exitDemo();
  try { await api("/applogin/logout", { body: {} }); } catch (_) {}
  AUTH.clear(); S.me = null; S.tab = "home"; S.sub = null; closeAllSheets(); boot();
}
