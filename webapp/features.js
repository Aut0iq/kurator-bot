"use strict";
/* ================= Задания, журнал действий, сотрудники, копии, итоги семестра, значки, оформление, уведомления ================= */

const tileIc = (ic, c, size = 34) => h("div", { class: "tile " + c, style: `width:${size}px;height:${size}px;border-radius:${Math.round(size / 3)}px;display:grid;place-items:center;flex:none` }, icon(ic, "sm"));
const WD_G = ["понедельника", "вторника", "среды", "четверга", "пятницы", "субботы", "воскресенья"];
const daysLeft = ds => Math.round((parseIso(ds) - parseIso(S.me.today)) / 864e5);
function dueText(ds) {
  const n = daysLeft(ds);
  if (n < 0) return n === -1 ? "срок был вчера" : `срок прошёл ${fmtDate(ds)}`;
  if (n === 0) return "сдать сегодня";
  if (n === 1) return "сдать завтра";
  if (n < 7) return `до ${WD_G[wdOf(ds)]}, ${fmtDate(ds)}`;
  return "до " + fmtDate(ds);
}
const dueCls = ds => { const n = daysLeft(ds); return n < 0 ? "A" : n <= 1 ? "L" : "kind"; };

/* ===================================================== домашние задания */
async function renderHomework() {
  const past = !!S.hwPast;
  const r = await api("/homework" + (past ? "?past=1" : ""));
  S.hwCache = r;
  const items = r.items;
  const head = pageTitle("Задания", r.can_add ? h("button", { class: "btn sm", onclick: () => openHomeworkEditor() }, icon("plus", "sm"), "Задать") : null);
  const chips = h("div", { class: "chips rise" },
    [[false, "Актуальные"], [true, "Архив"]].map(([v, t]) => h("button", { class: "chip " + (past === v ? "on" : ""), onclick: () => { S.hwPast = v; S.anim = "fade"; selTick(); render(); } }, t)));
  if (!items.length) return mount(S.anim, head, chips, empty("book", past ? "Архив пуст" : "Заданий нет", past ? "Здесь появятся задания за последние два месяца"
    : r.can_add ? "Нажмите «Задать», чтобы выдать задание к паре — студенты получат уведомление и напоминание накануне срока" : "Когда староста или куратор выдаст задание, оно появится здесь"));
  const groups = past
    ? [["Все задания", items.slice().reverse()]]
    : [["Срок прошёл", items.filter(x => x.bucket === "past" && !x.done)], ["Сегодня", items.filter(x => x.bucket === "today" && !x.done)],
       ["На этой неделе", items.filter(x => x.bucket === "week" && !x.done)], ["Позже", items.filter(x => x.bucket === "later" && !x.done)],
       ["Сделано ✓", items.filter(x => x.done)]];
  const parts = [head, chips];
  if (!past && r.is_student) {
    const todo = items.filter(x => !x.done && x.bucket !== "later").length, done = items.filter(x => x.done).length;
    parts.push(h("div", { class: "card rise hw-sum row" },
      h("div", { class: "hw-sum-num num" }, todo),
      h("div", { class: "grow" }, h("b", {}, todo ? `${plural(todo, "задание", "задания", "заданий")} сдать на этой неделе` : "На этой неделе всё сдано 🎉"),
        h("div", { class: "muted small" }, done ? `Уже сделано: ${done}` : "Отмечайте выполненные — кружок справа"))));
  }
  for (const [title, list] of groups) {
    if (!list.length) continue;
    parts.push(h("div", { class: "section rise" }, title, h("span", {}, list.length)));
    parts.push(h("div", { class: "hw-list" }, list.map(x => hwCard(x, r))));
  }
  mount(S.anim, parts);
}
function hwCard(x, r) {
  const check = r.is_student ? h("button", { class: "hw-check" + (x.done ? " on" : ""), title: x.done ? "Сделано" : "Отметить выполненным", onclick: e => {
    e.stopPropagation();
    const on = !x.done; x.done = on; card.classList.toggle("done", on); check.classList.toggle("on", on); haptic(on ? "medium" : "light");
    api(`/homework/${x.id}/done`, { body: { done: on } }).then(res => {
      if (on) { toast("Отлично! Задание выполнено", "check"); if (res.new_badge) checkNewBadges(true); }
      setTimeout(() => S.sub === "homework" && render(), 650);
    }).catch(err => { x.done = !on; card.classList.toggle("done", !on); check.classList.toggle("on", !on); toast(err.message, "alert"); });
  } }, icon("check", "sm")) : null;
  const card = h("div", { class: "card tap rise hw-card" + (x.done ? " done" : ""), onclick: () => openHomework(x, r) },
    h("div", { class: "row", style: "align-items:flex-start" },
      h("div", { class: "grow" },
        h("div", { class: "row", style: "gap:6px;flex-wrap:wrap" }, h("span", { class: "badge" }, x.subject), h("span", { class: "badge " + (x.done ? "P" : dueCls(x.due_date)) }, x.done ? "сделано" : dueText(x.due_date))),
        h("div", { class: "hw-title" }, x.title),
        x.text ? h("div", { class: "muted small hw-text" }, x.text) : null,
        x.total != null ? h("div", { class: "hw-prog" }, h("div", { class: "progress" }, h("i", { style: `width:${x.total ? Math.round(100 * x.done_count / x.total) : 0}%;background:var(--P)` })),
          h("span", { class: "muted tiny" }, `сделали ${x.done_count} из ${x.total}`)) : null),
      check));
  return card;
}
function openHomework(x, r) {
  openSheet(h("div", { class: "row", style: "gap:6px;flex-wrap:wrap" }, h("span", { class: "badge" }, x.subject), h("span", { class: "badge " + dueCls(x.due_date) }, dueText(x.due_date))),
    h("h3", { style: "margin:10px 0 4px" }, x.title),
    x.text ? h("div", { style: "white-space:pre-wrap;margin:6px 0 10px" }, x.text) : null,
    h("div", { class: "list", style: "margin-top:10px" },
      h("div", { class: "item" }, icon("calendar", "sm"), "Сдать до", h("div", { class: "grow" }), h("b", {}, fmtDateLong(x.due_date))),
      x.lesson_date ? h("div", { class: "item" }, icon("clock", "sm"), "Задано на паре", h("div", { class: "grow" }), h("b", {}, fmtDate(x.lesson_date))) : null,
      x.author_name ? h("div", { class: "item" }, icon("user", "sm"), "Задал(а)", h("div", { class: "grow" }), h("b", {}, x.author_name)) : null,
      x.total != null ? h("div", { class: "item" }, icon("check", "sm"), "Отметили «сделал»", h("div", { class: "grow" }), h("b", {}, `${x.done_count} из ${x.total}`)) : null),
    x.can_edit ? h("div", { class: "btns" },
      h("button", { class: "btn ghost", onclick: () => { closeSheet(); openHomeworkEditor(x); } }, icon("edit", "sm"), "Изменить"),
      h("button", { class: "btn danger", onclick: () => confirmDo("Удалить задание «" + x.title + "»?", () => safe(async () => {
        await api("/homework/" + x.id, { method: "DELETE" }); closeSheet(); toast("Задание удалено", "trash"); render(); })) }, icon("trash", "sm"), "Удалить")) : null);
}
async function openHomeworkEditor(x = {}) {
  let info = S.hwCache;
  if (!info?.next) { try { info = S.hwCache = await api("/homework"); } catch (_) { info = { subjects: S.me.subjects || [], next: {} }; } }
  const subjects = [...new Set([...(info.subjects || []), ...(x.subject ? [x.subject] : [])])];
  const subj = h("select", {}, h("option", { value: "" }, "— выберите предмет —"), subjects.map(s => h("option", { value: s, selected: s === x.subject }, s)));
  const title = h("input", { placeholder: "Например: задачи 1–10, стр. 42", maxlength: 200, value: x.title || "" });
  const text = h("textarea", { placeholder: "Подробности (необязательно)", maxlength: 2000, style: "min-height:80px" }); text.value = x.text || "";
  const due = h("input", { type: "date", value: x.due_date || "" });
  const notifyBox = h("input", { type: "checkbox", checked: !x.id });
  const quick = h("div", { class: "chips", style: "margin-top:8px;padding-bottom:2px" });
  const paintQuick = () => {
    const n = info.next?.[subj.value];
    const opts = [n ? [n.date, `К следующей паре · ${fmtDate(n.date)}`] : null, [addDays(S.me.today, 1), "Завтра"], [addDays(S.me.today, 7), "Через неделю"]].filter(Boolean);
    quick.replaceChildren(...opts.map(([d, t]) => h("button", { class: "chip " + (due.value === d ? "on" : ""), onclick: () => { due.value = d; selTick(); paintQuick(); } }, t)));
  };
  subj.onchange = () => { const n = info.next?.[subj.value]; if (n && !x.id && !due.dataset.touched) due.value = n.date; paintQuick(); };
  due.oninput = () => { due.dataset.touched = "1"; paintQuick(); };
  if (!x.id && x.subject && !x.due_date) { const n = info.next?.[x.subject]; if (n) due.value = n.date; }
  paintQuick();
  openSheet(h("h3", {}, x.id ? "Изменить задание" : "Новое задание"),
    h("label", { class: "f" }, "Предмет"), subj,
    h("label", { class: "f" }, "Что задано"), title,
    h("label", { class: "f" }, "Подробности"), text,
    h("label", { class: "f" }, "Срок сдачи"), due, quick,
    !x.id ? h("label", { class: "item", style: "padding:14px 2px 0;cursor:pointer" }, h("div", { class: "grow" }, "Сообщить группе в Telegram", h("div", { class: "muted tiny" }, "В приложении уведомление придёт в любом случае")), h("span", { class: "switch" }, notifyBox, h("i"))) : null,
    h("div", { class: "btns" }, h("button", { class: "btn block", onclick: act(async () => {
      const body = { subject: subj.value, title: title.value, text: text.value, due_date: due.value, lesson_id: x.lesson_id || null, lesson_date: x.lesson_date || null, notify: notifyBox.checked };
      if (x.id) await api("/homework/" + x.id, { method: "PUT", body });
      else { const res = await api("/homework", { body }); if (res.sent) toast(`Задание выдано · уведомлено ${res.sent}`, "check"); }
      notify(); closeAllSheets(); if (x.id) toast("Сохранено", "check");
      if (S.sub === "homework") render(); else go(S.tab, "homework");
    }) }, x.id ? "Сохранить" : "Выдать задание")),
    h("p", { class: "muted tiny center" }, "Накануне срока вечером студенты, которые ещё не отметили задание, получат напоминание."));
  setTimeout(() => (x.subject ? title : subj).focus(), 300);
}
/* карточка на главной: что сдать на неделе */
function homeworkHomeCard(r) {
  if (!r) return null;
  const todo = r.items.filter(x => !x.done && x.bucket !== "later");
  if (!todo.length && !r.can_add) return null;
  return h("div", { class: "card tap rise hw-home", onclick: () => go(S.tab, "homework") },
    h("div", { class: "row" }, tileIc("book", "c5", 40),
      h("div", { class: "grow" }, h("b", {}, "Задания"),
        h("div", { class: "muted small" }, todo.length ? `${todo.length} ${plural(todo.length, "задание", "задания", "заданий")} на этой неделе` : r.can_add ? "Выдайте задание к паре" : "На этой неделе всё сдано 🎉")),
      icon("right", "sm chev")),
    todo.length ? h("div", { class: "hw-mini" }, todo.slice(0, 3).map(x => h("div", { class: "row", style: "gap:8px" },
      h("span", { class: "dot", style: `background:var(--${dueCls(x.due_date) === "kind" ? "N" : dueCls(x.due_date)})` }),
      h("div", { class: "grow ellipsis small" }, h("b", {}, x.subject), " · ", x.title), h("span", { class: "muted tiny" }, dueText(x.due_date).replace("сдать ", ""))))) : null);
}

/* ===================================================== серии и значки */
const BADGE_SEEN = "badges_seen";
function streakCard(a) {
  if (!a?.student) return null;
  const got = a.badges.filter(b => b.earned);
  const nextTo = a.next_streak ? a.next_streak - a.streak : null;
  return h("div", { class: "card tap rise streak-card", onclick: () => go(S.tab, "badges") },
    h("div", { class: "row" },
      h("div", { class: "flame" + (a.streak ? " on" : "") }, "🔥", h("b", { class: "num" }, a.streak)),
      h("div", { class: "grow" },
        h("b", {}, a.streak ? `${a.streak} ${plural(a.streak, "пара", "пары", "пар")} подряд без пропусков` : "Начни новую серию!"),
        h("div", { class: "muted small" }, a.streak && nextTo > 0 ? `Ещё ${nextTo} — и новый значок` : a.best ? `Лучшая серия: ${a.best}` : "Приходи на пары — серия будет расти")),
      got.length ? h("div", { class: "streak-badges" }, got.slice(-3).map(b => h("span", {}, b.emoji))) : null));
}
async function renderBadges() {
  const a = await api("/achievements");
  if (!a.student) return mount(S.anim, pageTitle("Значки"), empty("award", "Только для студентов", "Значки получают студенты за посещаемость, ответы на опросы и задания"));
  store.set(BADGE_SEEN, a.badges.filter(b => b.earned).map(b => b.key));
  const got = a.badges.filter(b => b.earned), rest = a.badges.filter(b => !b.earned);
  const card = b => h("div", { class: "badge-tile rise" + (b.earned ? " on" : ""), onclick: () => openSheet(h("div", { class: "center", style: "padding:8px 0" },
      h("div", { class: "badge-big pop" + (b.earned ? " on" : "") }, b.emoji), h("h3", { style: "margin:12px 0 4px" }, b.title), h("div", { class: "muted" }, b.desc),
      b.earned ? h("div", { class: "badge P", style: "margin-top:12px" }, "Получен" + (b.at ? " " + fmtDate(b.at) : ""))
        : h("div", { style: "margin:14px auto 0;max-width:240px" }, h("div", { class: "progress" }, h("i", { style: `width:${Math.round(100 * b.progress / b.need)}%` })),
            h("div", { class: "muted small", style: "margin-top:6px" }, b.need > 1 ? `${b.progress} из ${b.need}` : "Ещё впереди")))) },
    h("div", { class: "be" }, b.emoji), h("b", {}, b.title),
    b.earned ? h("span", { class: "muted tiny" }, b.at ? fmtDate(b.at) : "получен")
      : h("div", { class: "progress sm" }, h("i", { style: `width:${Math.round(100 * b.progress / b.need)}%` })));
  mount(S.anim, pageTitle("Значки"),
    h("div", { class: "card rise streak-hero" },
      h("div", { class: "flame big" + (a.streak ? " on" : "") }, "🔥"),
      h("div", { class: "num streak-num" }, countUp(h("b"), a.streak)),
      h("div", { class: "muted" }, plural(a.streak, "пара", "пары", "пар") + " подряд без пропусков"),
      h("div", { class: "streak-meta" }, h("div", {}, h("b", {}, a.best), h("span", {}, "лучшая серия")), h("div", {}, h("b", {}, got.length), h("span", {}, "значков")),
        h("div", {}, h("b", {}, a.late_month), h("span", {}, plural(a.late_month, "день", "дня", "дней") + " без опозданий")))),
    got.length ? [h("div", { class: "section rise" }, "Получены", h("span", {}, got.length)), h("div", { class: "badge-grid" }, got.map(card))] : null,
    rest.length ? [h("div", { class: "section rise" }, "Впереди"), h("div", { class: "badge-grid" }, rest.map(card))] : null,
    h("p", { class: "muted tiny center rise", style: "margin-top:14px" }, "Значки видите только вы. Уважительная причина (справка) серию не прерывает."));
}
/* новый значок — поздравляем один раз */
async function checkNewBadges(force = false, data = null) {
  if (!S.me?.student || S.demoToken) return;
  let a = data;
  try { if (!a) a = await api("/achievements"); } catch (_) { return; }
  if (!a?.student) return;
  const seen = store.get(BADGE_SEEN, null), earned = a.badges.filter(b => b.earned);
  store.set(BADGE_SEEN, earned.map(b => b.key));
  if (seen == null && !force) return;                    // первый запуск на устройстве — не засыпаем поздравлениями
  const fresh = earned.filter(b => !(seen || []).includes(b.key));
  if (!fresh.length) return;
  const b = fresh[fresh.length - 1];
  confetti(); notify();
  openSheet(h("div", { class: "center", style: "padding:10px 0 4px" },
    h("div", { class: "muted small", style: "font-weight:700;letter-spacing:.06em;text-transform:uppercase" }, "Новый значок!"),
    h("div", { class: "badge-big on pop", style: "margin-top:14px" }, b.emoji),
    h("h3", { style: "margin:14px 0 4px" }, b.title), h("div", { class: "muted" }, b.desc),
    fresh.length > 1 ? h("div", { class: "muted small", style: "margin-top:8px" }, `и ещё ${fresh.length - 1}: ` + fresh.slice(0, -1).map(x => x.emoji).join(" ")) : null),
    h("div", { class: "btns" }, h("button", { class: "btn", onclick: () => { closeSheet(); go(S.tab, "badges"); } }, "Все значки"), h("button", { class: "btn plain", onclick: () => closeSheet() }, "Ура!")));
}

/* ===================================================== итоги семестра («Wrapped») */
const TONES = { violet: ["#7c3aed", "#4f46e5", "#2563eb"], green: ["#059669", "#10b981", "#0ea5e9"], blue: ["#2563eb", "#0ea5e9", "#22d3ee"],
  orange: ["#ea580c", "#f59e0b", "#ef4444"], pink: ["#db2777", "#a855f7", "#6366f1"] };
async function openWrapped() {
  let w;
  try { w = await safe(() => api("/wrapped")); } catch (_) { return; }
  const slides = w.slides;
  let i = 0, timer = null, paused = false;
  const bars = h("div", { class: "wr-bars" }, slides.map(() => h("i", {}, h("b"))));
  const stage = h("div", { class: "wr-stage" });
  const close = h("button", { class: "wr-close", onclick: () => done() }, icon("x"));
  const wrap = h("div", { class: "wrapped" }, bars, close, stage);
  document.body.append(wrap);
  document.body.classList.add("no-scroll");
  const DUR = 5200;
  function show(n) {
    i = Math.max(0, Math.min(slides.length - 1, n));
    const s = slides[i], t = TONES[s.tone] || TONES.violet;
    wrap.style.setProperty("--w1", t[0]); wrap.style.setProperty("--w2", t[1]); wrap.style.setProperty("--w3", t[2]);
    [...bars.children].forEach((b, k) => { b.className = k < i ? "done" : k === i ? "on" : ""; b.firstChild.style.animationDuration = DUR + "ms"; });
    const el = h("div", { class: "wr-slide" + (s.final ? " final" : "") },
      h("div", { class: "wr-emoji" }, s.emoji),
      h("div", { class: "wr-big" + ((s.big || "").length > 12 ? " long" : "") }, s.big),
      h("div", { class: "wr-text" }, s.text),
      s.sub ? h("div", { class: "wr-sub" }, s.sub) : null,
      s.final ? h("div", { class: "wr-share" },
        h("div", { class: "wr-card" }, h("div", { class: "wr-card-t" }, "Мой семестр · " + (w.kind === "group" ? w.group : (w.first || w.name))),
          (w.share.length ? w.share : ["✨ Ещё один семестр позади"]).map(x => h("div", {}, x)), h("div", { class: "wr-card-f" }, "Куратор +")),
        h("div", { class: "btns" }, h("button", { class: "btn wr-btn", onclick: e => { e.stopPropagation(); shareWrapped(w, "image"); } }, icon("share", "sm"), "Поделиться"),
          h("button", { class: "btn wr-btn ghost", onclick: e => { e.stopPropagation(); shareWrapped(w, "text"); } }, icon("copy", "sm"), "Текстом"))) : null);
    stage.replaceChildren(el);
    haptic("light");
    clearTimeout(timer);
    if (!s.final) timer = setTimeout(() => !paused && show(i + 1), DUR);
  }
  function done() { clearTimeout(timer); wrap.classList.add("out"); document.body.classList.remove("no-scroll"); setTimeout(() => wrap.remove(), 300); }
  stage.addEventListener("click", e => { if (e.target.closest(".wr-share")) return; e.clientX < innerWidth * .33 ? show(i - 1) : (i < slides.length - 1 ? show(i + 1) : null); });
  stage.addEventListener("pointerdown", () => { paused = true; wrap.classList.add("paused"); });
  stage.addEventListener("pointerup", () => { paused = false; wrap.classList.remove("paused"); });
  window.__wrappedClose = done;
  show(0);
}
function wrappedText(w) {
  return [`✨ Мой семестр в «Куратор +»${w.kind === "group" ? " · " + w.group : ""}`, ...w.share].join("\n");
}
function wrappedImage(w) {
  const W = 1080, H = 1350, c = document.createElement("canvas"); c.width = W; c.height = H;
  const x = c.getContext("2d");
  const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, "#7c3aed"); g.addColorStop(.55, "#4f46e5"); g.addColorStop(1, "#0ea5e9");
  x.fillStyle = g; x.fillRect(0, 0, W, H);
  for (const [cx, cy, r, a] of [[180, 220, 320, .18], [930, 1120, 380, .14], [880, 300, 200, .1]]) { x.beginPath(); x.arc(cx, cy, r, 0, 7); x.fillStyle = `rgba(255,255,255,${a})`; x.fill(); }
  x.fillStyle = "#fff"; x.textBaseline = "top";
  x.font = "700 44px -apple-system, Segoe UI, Roboto, sans-serif"; x.globalAlpha = .85;
  x.fillText("МОЙ СЕМЕСТР", 90, 110); x.globalAlpha = 1;
  x.font = "800 86px -apple-system, Segoe UI, Roboto, sans-serif";
  const name = w.kind === "group" ? w.group : (w.first || w.name);
  x.fillText(name.length > 18 ? name.slice(0, 17) + "…" : name, 90, 170);
  x.font = "600 54px -apple-system, Segoe UI, Roboto, sans-serif";
  (w.share.length ? w.share : ["✨ Ещё один семестр позади"]).slice(0, 6).forEach((t, k) => {
    const y = 360 + k * 130;
    x.fillStyle = "rgba(255,255,255,.16)"; roundRect(x, 80, y - 26, W - 160, 104, 30); x.fill();
    x.fillStyle = "#fff"; x.fillText(t.length > 30 ? t.slice(0, 29) + "…" : t, 120, y);
  });
  x.font = "800 50px -apple-system, Segoe UI, Roboto, sans-serif"; x.fillText("Куратор +", 90, H - 140);
  x.font = "500 34px -apple-system, Segoe UI, Roboto, sans-serif"; x.globalAlpha = .8; x.fillText(w.group, 90, H - 80);
  return c;
}
function roundRect(x, a, b, w, hh, r) { x.beginPath(); x.moveTo(a + r, b); x.arcTo(a + w, b, a + w, b + hh, r); x.arcTo(a + w, b + hh, a, b + hh, r); x.arcTo(a, b + hh, a, b, r); x.arcTo(a, b, a + w, b, r); x.closePath(); }
async function shareWrapped(w, how) {
  const text = wrappedText(w);
  if (how === "image") {
    const c = wrappedImage(w), data = c.toDataURL("image/png");
    if (NATIVE?.shareImage) { try { NATIVE.shareImage(data.split(",")[1], text); return; } catch (_) {} }
    try {
      const blob = await new Promise(r => c.toBlob(r, "image/png"));
      const file = new File([blob], "semestr.png", { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) { await navigator.share({ files: [file], text }); return; }
    } catch (e) { if (e?.name === "AbortError") return; }
    if (!IN_TG) { const a = h("a", { href: data, download: "semestr.png" }); document.body.append(a); a.click(); a.remove(); toast("Картинка сохранена", "download"); return; }
    return openSheet(h("h3", {}, "Картинка с итогами"), h("img", { src: data, style: "width:100%;border-radius:16px;margin-top:10px" }),
      h("p", { class: "muted small center" }, "Нажмите на картинку и удерживайте, чтобы сохранить или переслать."));
  }
  if (IN_TG) { try { return tg.openTelegramLink("https://t.me/share/url?url=" + encodeURIComponent("https://t.me/" + S.me.bot) + "&text=" + encodeURIComponent(text)); } catch (_) {} }
  if (navigator.share) { try { await navigator.share({ text }); return; } catch (e) { if (e?.name === "AbortError") return; } }
  navigator.clipboard?.writeText(text).then(() => toast("Скопировано — вставьте в чат или сторис", "copy"));
}
function wrappedCard() {
  const m = +S.me.today.slice(5, 7);
  const season = [12, 1, 5, 6, 7].includes(m);
  return h("div", { class: "card tap rise wr-promo" + (season ? " hot" : ""), onclick: openWrapped },
    h("div", { class: "row" }, h("div", { class: "wr-promo-ic" }, "✨"),
      h("div", { class: "grow" }, h("b", {}, season ? "Итоги семестра готовы!" : "Итоги семестра"),
        h("div", { class: "small", style: "opacity:.85" }, isStaff() && !S.me.student ? "Как прошёл семестр у группы" : "Твоя посещаемость, серии и значки — в формате историй")),
      icon("right", "sm")));
}

/* ===================================================== журнал действий */
const AUDIT_KINDS = { "": "Все", marks: "Отметки", grades: "Оценки", student: "Студенты", delete: "Удаления", schedule: "Расписание", change: "Переносы",
  homework: "Задания", role: "Роли", perms: "Права", announce: "Объявления", code: "Коды входа", settings: "Настройки", lock: "Доступ", backup: "Копии" };
const AUDIT_IC = { marks: ["journal", "c2"], grades: ["award", "c2"], student: ["user", "c5"], delete: ["trash", "c4"], schedule: ["calendar", "c5"], change: ["refresh", "c3"],
  homework: ["book", "c5"], role: ["shield", "c1"], perms: ["key", "c1"], announce: ["mega", "c6"], code: ["key", "c3"], settings: ["settings", "c5"], lock: ["key", "c4"], backup: ["server", "c3"] };
async function renderAudit(more = false) {
  const f = S.auditF || (S.auditF = { action: "", q: "", student: "" });
  const qs = new URLSearchParams(Object.entries({ action: f.action, q: f.q, student: f.student, before: more ? S.auditLast : "" }).filter(([, v]) => v)).toString();
  const r = await api("/audit" + (qs ? "?" + qs : ""));
  if (S.sub !== "audit") return;
  S.auditItems = more ? [...(S.auditItems || []), ...r.items] : r.items;
  S.auditLast = S.auditItems.at(-1)?.id;
  if (!S.auditStudents) { try { S.auditStudents = (await api("/students?archived=1")).students; } catch (_) { S.auditStudents = []; } }
  const search = h("input", { placeholder: "Поиск: фамилия, предмет, действие…", value: f.q, style: "margin-bottom:10px;background-color:var(--card);box-shadow:var(--shadow)" });
  let t = null;
  search.oninput = () => { clearTimeout(t); t = setTimeout(() => { f.q = search.value.trim(); S.anim = null; renderAudit().then(() => { const s = $app.querySelector("input"); s?.focus(); s?.setSelectionRange(99, 99); }); }, 400); };
  const who = h("select", { style: "margin-bottom:10px;background-color:var(--card);box-shadow:var(--shadow)", onchange: e => { f.student = e.target.value; S.anim = "fade"; renderAudit(); } },
    h("option", { value: "" }, "Все студенты"), S.auditStudents.map(s => h("option", { value: s.id, selected: String(s.id) === String(f.student) }, s.full_name)));
  const chips = h("div", { class: "chips" }, Object.entries(AUDIT_KINDS).filter(([k]) => S.me.super || !["lock", "backup"].includes(k)).map(([k, v]) =>
    h("button", { class: "chip " + (f.action === k ? "on" : ""), onclick: () => { f.action = k; S.anim = "fade"; selTick(); renderAudit(); } }, v)));
  const byDay = {};
  for (const x of S.auditItems) { const d = iso(new Date(x.at * 1000)); (byDay[d] = byDay[d] || []).push(x); }
  const dayName = d => d === S.me.today ? "Сегодня" : d === addDays(S.me.today, -1) ? "Вчера" : fmtDateLong(d);
  const list = Object.entries(byDay).map(([d, xs]) => [h("div", { class: "section" }, dayName(d), h("span", {}, xs.length)),
    h("div", { class: "list" }, xs.map(x => { const [ic, c] = AUDIT_IC[x.action] || ["edit", "c1"]; return h("div", { class: "item", style: "align-items:flex-start" }, tileIc(ic, c, 32),
      h("div", { class: "grow", style: "min-width:0" }, h("div", { class: "small audit-text" }, x.text),
        h("div", { class: "muted tiny", style: "margin-top:3px" }, (x.actor_name || "система") + " · " + hm(x.at) + (x.group_id == null ? " · весь сервис" : "")))); }))]);
  const parts = [pageTitle("Журнал действий"), h("div", { class: "rise" }, search, S.auditStudents.length ? who : null, chips),
    S.auditItems.length ? list : empty("journal", "Ничего не найдено", f.q || f.student || f.action ? "Попробуйте изменить фильтр" : "Здесь появятся изменения отметок, оценок, данных студентов и удаления"),
    r.more ? h("div", { class: "btns" }, h("button", { class: "btn plain", onclick: act(() => renderAudit(true)) }, "Показать ещё")) : null,
    h("p", { class: "muted tiny center", style: "margin-top:14px" }, "Записи хранятся год. Видят староста, заместитель и куратор группы.")];
  if (more) { const y = scrollY; mount(null, parts); scrollTo(0, y); } else mount(S.anim, parts);
}

/* ===================================================== вход по логину: сотрудник сам + главный куратор */
function staffLoginSheet() {
  const sl = S.me.staff_login || {};
  const login = h("input", { placeholder: "Например, ivanova или ivanova@mail.ru", autocomplete: "username", value: sl.login || "", autocapitalize: "none", spellcheck: false });
  const old = h("input", { type: "password", placeholder: "Текущий пароль", autocomplete: "current-password" });
  const pw = h("input", { type: "password", placeholder: sl.has_password ? "Оставьте пустым, чтобы не менять" : "Не короче 8 символов", autocomplete: "new-password" });
  const pw2 = h("input", { type: "password", placeholder: "Ещё раз", autocomplete: "new-password" });
  openSheet(h("h3", {}, sl.has_password ? "Вход по логину" : "Логин и пароль"),
    h("p", { class: "muted small", style: "margin:4px 0 6px" }, "Вход через Telegram продолжит работать. С логином и паролем можно войти в приложение или в браузере и без Telegram."),
    h("label", { class: "f" }, "Логин"), login,
    sl.has_password ? [h("label", { class: "f" }, "Текущий пароль"), old] : null,
    h("label", { class: "f" }, sl.has_password ? "Новый пароль" : "Пароль"), pw, h("label", { class: "f" }, "Повторите"), pw2,
    h("div", { class: "btns" }, h("button", { class: "btn block", onclick: act(async () => {
      if (pw.value !== pw2.value) throw new Error("Пароли не совпадают");
      const r = await api("/me/login", { body: { login: login.value, password: pw.value, old: old.value } });
      S.me.staff_login = { login: r.login, has_password: sl.has_password || !!pw.value };
      notify(); closeSheet(); toast("Сохранено — логин " + r.login, "check"); if (S.tab === "more") render();
    }) }, "Сохранить")),
    h("p", { class: "muted tiny center" }, "Забыли пароль? Главный куратор выдаст одноразовый код для сброса."));
}
async function renderStaffAccounts() {
  if (!S.me.super) return mount(S.anim, pageTitle("Сотрудники"), empty("key", "Недоступно", "Раздел главного куратора"));
  const r = await api("/admin/staff");
  const now = Date.now() / 1000;
  mount(S.anim, pageTitle("Входы сотрудников"),
    h("p", { class: "muted small rise", style: "margin:0 6px 12px" }, "Старосты, заместители и кураторы могут входить по логину и паролю. Забыл пароль — выдайте одноразовый код: по нему он задаст новый."),
    r.staff.length ? h("div", { class: "list rise" }, r.staff.map(x => h("div", { class: "item tap", onclick: () => staffCodeSheet(x) }, ava(x.name || "?"),
      h("div", { class: "grow", style: "min-width:0" }, h("div", { class: "ellipsis", style: "font-weight:600" }, x.name),
        h("div", { class: "muted tiny ellipsis" }, [x.role_name, x.group, x.login ? "логин " + x.login : null].filter(Boolean).join(" · "))),
      x.code_until && x.code_until > now ? h("span", { class: "badge L" }, "код выдан") : x.has_password ? h("span", { class: "badge P" }, "пароль") : h("span", { class: "badge kind" }, "нет пароля"))))
      : empty("users", "Сотрудников пока нет", "Здесь появятся старосты и кураторы групп"));
}
function staffCodeSheet(x) {
  const login = h("input", { placeholder: "латиницей, например ivanova", value: x.login || "", autocapitalize: "none", spellcheck: false });
  openSheet(h("div", { class: "row", style: "gap:12px" }, ava(x.name || "?"), h("div", {}, h("h3", { style: "margin:0" }, x.name), h("div", { class: "muted small" }, x.role_name + (x.group ? " · " + x.group : "")))),
    h("div", { class: "list", style: "margin-top:14px" },
      h("div", { class: "item" }, "Логин", h("div", { class: "grow" }), h("b", {}, x.login || "не задан")),
      h("div", { class: "item" }, "Пароль", h("div", { class: "grow" }), h("b", {}, x.has_password ? "задан" : "не задан")),
      x.last_seen ? h("div", { class: "item" }, "Заходил(а)", h("div", { class: "grow" }), h("b", {}, fmtAgo(x.last_seen))) : null),
    h("label", { class: "f" }, x.login ? "Логин (можно изменить)" : "Логин — придумайте или оставьте пустым"), login,
    h("div", { class: "btns" }, h("button", { class: "btn block", onclick: act(async () => {
      const r = await api(`/admin/staff/${x.tg_id}/code`, { body: { login: login.value.trim() || undefined } });
      notify(); closeSheet();
      const until = new Date(r.expires * 1000).toLocaleString("ru", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
      const msg = `Вход в «Куратор +» по логину:\n1) Откройте приложение или ${location.origin}\n2) «Войти по паролю» → «Первый вход или забыли пароль?»\n3) Логин: ${r.login}, код: ${r.code}\nКод одноразовый, действует до ${until}.`;
      openSheet(h("div", { class: "center", style: "padding:6px 0" }, h("div", { class: "muted small" }, r.name + " · логин " + r.login),
          h("div", { class: "code pop", style: "font-size:46px;letter-spacing:10px;margin:10px 0" }, r.code), h("div", { class: "muted small" }, "Одноразовый · действует до " + until)),
        h("div", { class: "note", style: "font-size:14px;margin-top:12px" }, "Передайте код лично. Вход: «Войти по паролю» → «Первый вход или забыли пароль?» → логин, код и новый пароль."),
        h("div", { class: "btns" }, h("button", { class: "btn ghost", onclick: () => navigator.clipboard?.writeText(msg).then(() => toast("Скопировано", "check")) }, icon("copy", "sm"), "Копировать с инструкцией")));
      if (S.sub === "staff") renderStaffAccounts();
    }) }, icon("key", "sm"), x.has_password ? "Сбросить пароль — выдать код" : "Выдать код для первого входа")));
}

/* ===================================================== мониторинг: статистика использования и резервные копии */
function usageBlock(u) {
  if (!u) return null;
  const max = Math.max(1, ...u.days.map(d => d.n));
  return [h("div", { class: "section rise" }, "Использование"),
    h("div", { class: "kpis rise", style: "grid-template-columns:1fr 1fr" },
      h("div", { class: "kpi" }, h("b", { class: "num" }, u.active_day), h("span", {}, "активны за сутки")),
      h("div", { class: "kpi" }, h("b", { class: "num" }, u.active_week), h("span", {}, `за неделю · из ${u.users}`)),
      h("div", { class: "kpi" }, h("b", { class: "num" }, u.answers_week), h("span", {}, "ответов на опросы за 7 дней")),
      h("div", { class: "kpi" }, h("b", { class: "num" }, u.marks_week), h("span", {}, "отметок за 7 дней"))),
    h("div", { class: "card rise" }, h("div", { class: "row" }, h("b", { class: "grow" }, "Заходили по дням"), h("span", { class: "muted tiny" }, `приложение: ${u.app_week} · без Telegram: ${u.no_telegram}`)),
      h("div", { class: "ubars" }, u.days.map(d => h("div", { class: "ubar" + (d.day === u.days.at(-1).day ? " on" : "") }, h("span", { class: "num" }, d.n || ""),
        h("i", { style: `height:${Math.max(4, Math.round(70 * d.n / max))}px` }), h("em", {}, WDS[wdOf(d.day)]))))),
    u.groups.length ? h("div", { class: "list rise" }, u.groups.map(gr => h("div", { class: "item" }, h("div", { class: "avatar", style: "width:34px;height:34px;border-radius:11px;font-size:13px" }, groupMark(gr.name)),
      h("div", { class: "grow", style: "min-width:0" }, h("div", { class: "ellipsis", style: "font-weight:600" }, gr.name),
        h("div", { class: "muted tiny" }, `${gr.students} студ. · подключились ${gr.linked} · ответов за неделю ${gr.answers_week}`)),
      h("div", { class: "center" }, h("b", { class: "num" }, gr.active_week), h("div", { class: "muted tiny" }, "активны"))))) : null];
}
function backupBlock(bk) {
  if (!bk) return null;
  const items = bk.items || [];
  return [h("div", { class: "section rise" }, "Резервные копии", h("span", {}, items.length)),
    h("div", { class: "card rise" },
      h("div", { class: "muted small" }, items.length ? `Последняя: ${fmtAgo(items[0].at)} · ${fmtB(items[0].size)}. Автоматически — каждую ночь, хранятся ${bk.keep} последних.` : "Копий ещё нет. Автоматическая копия делается каждую ночь."),
      h("div", { class: "btns" },
        h("button", { class: "btn sm", onclick: act(async () => { const r = await api("/admin/backup", { body: {} }); S.bk = { ...S.bk, items: r.items }; notify(); toast("Копия создана · " + fmtB(r.size), "check"); renderServer(true); }) }, icon("download", "sm"), "Сделать копию"),
        h("button", { class: "btn ghost sm", onclick: act(async () => { const r = await api("/admin/backup", { body: { send: true } }); S.bk = { ...S.bk, items: r.items }; notify(); toast("Копия отправлена вам в Telegram", "check"); renderServer(true); }) }, icon("share", "sm"), "В Telegram"))),
    items.length ? h("div", { class: "list rise" }, items.slice(0, 8).map(b => h("div", { class: "item tap", onclick: () => backupSheet(b) },
      tileIc(b.safety ? "shield" : "server", b.safety ? "c3" : "c5", 32),
      h("div", { class: "grow", style: "min-width:0" }, h("div", { class: "small", style: "font-weight:600" }, new Date(b.at * 1000).toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })),
        h("div", { class: "muted tiny ellipsis" }, (b.safety ? "страховочная (перед восстановлением) · " : "") + fmtB(b.size))),
      icon("right", "sm chev")))) : null];
}
function backupSheet(b) {
  openSheet(h("h3", {}, "Копия от " + new Date(b.at * 1000).toLocaleString("ru", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })),
    h("div", { class: "muted small", style: "margin:4px 0 12px" }, b.name + " · " + fmtB(b.size)),
    h("div", { class: "list" },
      h("div", { class: "item tap", onclick: act(async () => { await api(`/admin/backups/${encodeURIComponent(b.name)}/send`, { body: {} }); closeSheet(); toast("Отправлено вам в Telegram", "check"); }) },
        tileIc("share", "c5"), h("div", { class: "grow" }, h("b", {}, "Прислать в Telegram"), h("div", { class: "muted tiny" }, "Файл базы придёт в чат с ботом")), icon("right", "sm chev")),
      h("div", { class: "item tap", onclick: () => restoreSheet(b) }, tileIc("refresh", "c4"),
        h("div", { class: "grow" }, h("b", { style: "color:var(--A)" }, "Восстановить из этой копии"), h("div", { class: "muted tiny" }, "Всё, что изменилось после неё, пропадёт")), icon("right", "sm chev"))));
}
function restoreSheet(b) {
  const word = h("input", { placeholder: "ВОССТАНОВИТЬ", autocapitalize: "characters", style: "text-align:center;font-weight:700;letter-spacing:2px" });
  const go = h("button", { class: "btn danger block", disabled: true, onclick: act(async () => {
    const r = await api("/admin/restore", { body: { name: b.name, confirm: word.value } });
    closeAllSheets(); notify("warning"); S.bk = null;
    openSheet(h("div", { class: "center", style: "padding:10px 0" }, h("div", { style: "font-size:44px" }, "✅"), h("h3", { style: "margin:10px 0 4px" }, "База восстановлена"),
      h("div", { class: "muted small" }, "Из копии " + r.restored), h("div", { class: "muted tiny", style: "margin-top:10px" }, "Состояние до восстановления сохранено в " + r.safety + " — если что-то пошло не так, восстановите её.")),
      h("div", { class: "btns" }, h("button", { class: "btn", onclick: () => { closeSheet(); S.me = null; boot(); } }, "Перезагрузить приложение")));
  }) }, icon("refresh", "sm"), "Восстановить");
  word.oninput = () => { go.disabled = word.value.trim().toUpperCase() !== "ВОССТАНОВИТЬ"; };
  openSheet(h("h3", {}, "Восстановить базу?"),
    h("div", { class: "note", style: "font-size:14px;margin-top:8px" }, "Все данные (группы, отметки, оценки, студенты, задания) вернутся к состоянию на " +
      new Date(b.at * 1000).toLocaleString("ru", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }) + ". Перед этим текущая база автоматически сохранится в страховочную копию."),
    h("label", { class: "f" }, "Чтобы подтвердить, введите слово ВОССТАНОВИТЬ"), word, h("div", { class: "btns" }, go));
}

/* ===================================================== оформление */
function openAppearance() {
  const body = h("div");
  const paint = () => {
    const p = themePrefs();
    const modes = [["system", "Как в системе", IN_TG ? "Как в Telegram" : "Как в телефоне"], ["light", "Светлая", "Всегда светлая"], ["dark", "Тёмная", "Всегда тёмная"]];
    body.replaceChildren(
      h("div", { class: "theme-modes" }, modes.map(([k, t, d]) => h("button", { class: "theme-mode " + k + (p.mode === k ? " on" : ""), onclick: () => { setThemePrefs({ mode: k }); selTick(); paint(); } },
        h("div", { class: "tm-prev" }, h("i"), h("i"), h("i")), h("b", {}, t), h("span", {}, d)))),
      h("label", { class: "f" }, "Цвет акцента"),
      h("div", { class: "accents" }, Object.entries(ACCENTS).map(([k, a]) => h("button", { class: "accent-sw" + (p.accent === k ? " on" : ""), title: a.name, style: `--sw:linear-gradient(135deg,${a.a.join(",")})`,
        onclick: () => { setThemePrefs({ accent: k }); haptic("light"); paint(); } }, h("i"), h("span", {}, a.name)))),
      h("div", { class: "card", style: "margin-top:16px;background:var(--bg2);box-shadow:none" },
        h("div", { class: "row" }, h("div", { class: "avatar", style: "width:40px;height:40px;font-size:15px" }, "К+"), h("div", { class: "grow" }, h("b", {}, "Так будет выглядеть"), h("div", { class: "muted small" }, "кнопки, вкладки и графики"))),
        h("div", { class: "progress", style: "margin:12px 0" }, h("i", { style: "width:68%" })),
        h("div", { class: "btns", style: "margin-top:0" }, h("button", { class: "btn sm" }, "Кнопка"), h("button", { class: "btn ghost sm" }, "Вторая"))));
  };
  paint();
  openSheet(h("h3", {}, "Оформление"), h("p", { class: "muted small", style: "margin:4px 0 12px" }, "Сохраняется на этом устройстве."), body);
}

/* ===================================================== уведомления в Android-приложении */
const pushSupported = () => { try { return !!NATIVE?.pushSupported?.(); } catch (_) { return false; } };
/* приложение закрылось с ошибкой — отправляем её в «Мониторинг» главному куратору */
function reportNativeCrash() {
  let t = "";
  try { t = NATIVE?.lastCrash?.() || ""; } catch (_) {}
  if (t) api("/client-error", { body: { text: t } }).catch(() => {});
}
function syncNativePush() {
  if (!pushSupported() || !S.me?.member || S.demoToken) return;
  try { NATIVE.setPush(!!S.me.push); if (S.me.push) store.set("notif_asked", 1); } catch (_) {}
}
function pushRow() {
  if (!pushSupported() || S.me.demo) return null;
  const sw = h("input", { type: "checkbox", checked: !!S.me.push, onchange: e => safe(() => api("/me/push", { body: { on: e.target.checked } }))
    .then(() => {
      S.me.push = e.target.checked; selTick();
      // Android уже спрашивал разрешение и его не дали — открываем настройки уведомлений приложения
      if (S.me.push && store.get("notif_asked") && NATIVE.pushPermission && !NATIVE.pushPermission()) { NATIVE.openNotificationSettings?.(); toast("Разрешите уведомления для «Куратор +»", "bell"); }
      else toast(S.me.push ? "Уведомления в телефоне включены" : "Уведомления в телефоне выключены", "bell");
      syncNativePush();
    })
    .catch(() => { e.target.checked = !e.target.checked; }) });
  return h("label", { class: "item", style: "cursor:pointer" }, tileIc("mobile", "c1"),
    h("div", { class: "grow" }, h("div", { style: "font-weight:600" }, "Уведомления в телефоне"),
      h("div", { class: "muted tiny" }, S.me.no_telegram ? "Опрос «Будешь на паре?» с кнопками, объявления, переносы, задания"
        : "Опросы с кнопками, объявления, переносы, задания — прямо в шторке. В Telegram тоже продолжат приходить")),
    h("span", { class: "switch" }, sw, h("i")));
}

/* ===================================================== стартовая страница (вне Telegram) */
const SOCIAL_NAMES = { telegram: ["Telegram", "#229ED9"], vk: ["ВКонтакте", "#0077FF"], youtube: ["YouTube", "#FF0033"], rutube: ["RuTube", "#100943"],
  tiktok: ["TikTok", "#111111"], dzen: ["Дзен", "#000000"], site: ["Сайт", "var(--accent)"] };
function startTelegramLogin(btn) {
  return safe(async () => {
    const r = await api("/applogin/start", { body: {} });
    renderLogin({ code: r.code, link: r.link, tg_link: r.tg_link });
    openLink(NATIVE ? r.tg_link : r.link);
  }, btn);
}
function copyrightFooter() {
  const y = new Date().getFullYear();
  const doc = (n, t) => h("a", { onclick: () => openDoc(n) }, t);
  return h("footer", { class: "copyright rise" },
    h("div", { class: "cr-links" }, doc("terms", "Соглашение"), doc("privacy", "Конфиденциальность"), doc("consent", "Согласие на обработку данных")),
    h("p", {}, `© ${y > 2026 ? "2026–" + y : 2026} «Куратор +». Все права защищены.`),
    h("p", {}, "Дизайн, интерфейс, логотип, тексты и программный код «Куратор +» охраняются законом как объекты авторского права (ст. 1259, 1270 ГК РФ). " +
      "Копирование, в том числе частичное, переработка и использование в других проектах — только с письменного разрешения правообладателя."),
    h("p", {}, "Не является официальным приложением КГА ПОУ «ВСК»."));
}
function appDownloadCard(info) {
  if (NATIVE || !info?.apk) return null;
  return h("div", { class: "card rise land-app row" },
    h("div", { class: "land-app-ic" }, icon("mobile", "lg")),
    h("div", { class: "grow" }, h("b", {}, "Приложение для Android"),
      h("div", { class: "muted small" }, [info.version_name ? "версия " + info.version_name : null, info.size ? fmtSize(info.size) : null, "бесплатно"].filter(Boolean).join(" · "))),
    h("button", { class: "btn sm", onclick: () => { openLink(location.origin + (info.url || "/app.apk")); toast("Файл скачивается — откройте его из «Загрузок» и нажмите «Установить»", "download"); } }, icon("download", "sm"), "Скачать"));
}
function socialBlock(info) {
  const list = (info?.social || []).filter(x => SOCIAL_NAMES[x.key]);
  return [h("div", { class: "section rise" }, "Мы в соцсетях"),
    list.length
      ? h("div", { class: "social rise" }, list.map(x => h("button", { class: "social-btn", style: `--sc:${SOCIAL_NAMES[x.key][1]}`, onclick: () => openLink(x.url) },
          h("span", { class: "social-dot" }, SOCIAL_NAMES[x.key][0][0]), SOCIAL_NAMES[x.key][0])))
      : h("div", { class: "card rise muted small center" }, "Скоро здесь появятся наши соцсети — новости, советы старостам и обновления")];
}
function loginSheet(kind) {
  const staff = kind === "staff";
  openSheet(h("div", { class: "row", style: "gap:12px" }, tileIc(staff ? "shield" : "user", staff ? "c1" : "c5", 44),
      h("div", {}, h("h3", { style: "margin:0" }, staff ? "Староста или куратор" : "Студент"),
        h("div", { class: "muted small" }, staff ? "Ведите журнал, опросы и отчёты" : "Опросы, расписание, пропуски и оценки"))),
    h("div", { class: "list", style: "margin-top:16px" },
      h("div", { class: "item tap", onclick: e => { closeSheet(); startTelegramLogin(); } }, h("span", { class: "tg-logo sm" }),
        h("div", { class: "grow" }, h("b", {}, "Через Telegram"), h("div", { class: "muted tiny" }, "Без пароля: бот спросит, вы ли это")), icon("right", "sm chev")),
      h("div", { class: "item tap", onclick: () => { closeSheet(); renderPwLogin(); } }, tileIc("key", "c3", 34),
        h("div", { class: "grow" }, h("b", {}, staff ? "По логину и паролю" : "По номеру студенческого"),
          h("div", { class: "muted tiny" }, staff ? "Логин задаётся в «Ещё → Аккаунт»; сброс — у главного куратора" : "Первый пароль — по коду от старосты или куратора")), icon("right", "sm chev"))));
}
function createGroupSheet() {
  store.set("intent", "create");
  openSheet(h("div", { class: "center", style: "padding:6px 0 2px" }, h("div", { class: "land-create-ic pop" }, icon("plus", "lg")),
      h("h3", { style: "margin:12px 0 4px" }, "Своя группа за минуту"),
      h("p", { class: "muted small", style: "margin:0" }, "Войдите — и сразу откроется создание группы. Потом добавите расписание и пригласите студентов ссылкой.")),
    h("div", { class: "btns" }, h("button", { class: "btn block tg-btn", onclick: () => { closeSheet(); startTelegramLogin(); } }, h("span", { class: "tg-logo" }), "Войти через Telegram")),
    h("div", { class: "btns", style: "margin-top:8px" }, h("button", { class: "btn ghost block", onclick: () => { closeSheet(); renderPwLogin(); } }, icon("key", "sm"), "У меня есть логин и пароль")),
    h("p", { class: "muted tiny center" }, "Бесплатно и без рекламы."));
}
async function renderLanding() {
  let info = {};
  const page = () => mount("fade",
    h("div", { class: "land-hero" },
      h("div", { class: "login-art pop" }, h("img", { class: "brand-logo", src: "/static/logo.webp", alt: "Куратор +", width: 92, height: 92 })),
      h("h1", { class: "rise" }, "Куратор ", h("b", { class: "plus" }, "+")),
      h("p", { class: "muted rise" }, "Опрос «Будешь на паре?», журнал, оценки, задания и расписание группы — в одном приложении")),
    h("div", { class: "card tap rise land-create", onclick: createGroupSheet },
      h("div", { class: "row" }, h("div", { class: "land-create-ic" }, icon("plus", "lg")),
        h("div", { class: "grow" }, h("b", {}, "Создать свою группу"), h("div", { class: "small", style: "opacity:.9" }, "Для старост и кураторов · бесплатно")),
        icon("right", "sm"))),
    h("div", { class: "section rise" }, "Войти"),
    h("div", { class: "land-roles rise" },
      h("button", { class: "land-role", onclick: () => loginSheet("staff") }, tileIc("shield", "c1", 44), h("b", {}, "Староста или куратор"), h("span", {}, "Telegram или логин")),
      h("button", { class: "land-role", onclick: () => loginSheet("student") }, tileIc("user", "c5", 44), h("b", {}, "Студент"), h("span", {}, "Telegram или № студенческого")),
      h("button", { class: "land-role", onclick: () => renderParentLogin() }, tileIc("users", "c2", 44), h("b", {}, "Родитель"), h("span", {}, "Посещаемость и оценки ребёнка"))),
    appDownloadCard(info),
    h("div", { class: "section rise" }, "Посмотреть без входа"),
    demoButton(),
    socialBlock(info),
    NATIVE?.resetServer ? h("div", { class: "center" }, h("button", { class: "back", style: "color:var(--hint)", onclick: () => NATIVE.resetServer() }, "Сменить адрес сервера")) : null,
    copyrightFooter());
  page();
  try { info = await api("/app-info"); if (!S.me && document.querySelector(".land-roles")) { S.anim = null; $app.classList.add("srv-quiet"); page(); setTimeout(() => $app.classList.remove("srv-quiet"), 600); } } catch (_) {}
}

/* ===================================================== родитель */
function renderParentLogin(mode = "login", recordNo = "") {
  const first = mode === "set";
  const rec = h("input", { class: "rec-input", placeholder: "Например, А-309", value: recordNo, autocapitalize: "characters", spellcheck: false });
  const code = h("input", { placeholder: "6 цифр от старосты или куратора", inputmode: "numeric", maxlength: 6, autocomplete: "one-time-code", style: "letter-spacing:4px;font-weight:700" });
  const pw = h("input", { type: "password", placeholder: first ? "Не короче 8 символов" : "Пароль родителя", autocomplete: first ? "new-password" : "current-password" });
  const pw2 = h("input", { type: "password", placeholder: "Ещё раз", autocomplete: "new-password" });
  const submit = act(async () => {
    if (first && pw.value !== pw2.value) throw new Error("Пароли не совпадают");
    const r = first ? await api("/parent/set-password", { body: { record_no: rec.value, code: code.value, password: pw.value } })
      : await api("/parent/login", { body: { record_no: rec.value, password: pw.value } });
    AUTH.set(r.token); notify(); S.me = null; boot();
  });
  [rec, code, pw, pw2].forEach(i => i.addEventListener("keydown", e => { if (e.key === "Enter") submit({ currentTarget: e.target }); }));
  mount("fade", h("div", { class: "login" },
    h("div", { class: "login-art pop" }, h("div", { class: "avatar", style: "width:84px;height:84px;border-radius:26px;background:linear-gradient(135deg,#22c55e,#0ea5e9)" }, icon("users", "lg"))),
    h("h1", { class: "rise" }, first ? "Первый вход родителя" : "Вход для родителей"),
    h("p", { class: "muted rise" }, first ? "Код выдаёт староста или куратор группы (в карточке студента). Придумайте пароль — дальше входите по номеру студенческого и паролю."
      : "Посещаемость, пропуски, оценки и задания вашего ребёнка. Только просмотр."),
    h("div", { class: "card rise", style: "text-align:left" },
      h("label", { class: "f", style: "margin-top:0" }, "Номер студенческого ребёнка"), rec,
      first ? [h("label", { class: "f" }, "Код для родителя"), code] : null,
      h("label", { class: "f" }, first ? "Новый пароль" : "Пароль"), pw,
      first ? [h("label", { class: "f" }, "Повторите пароль"), pw2] : null,
      h("div", { class: "btns" }, h("button", { class: "btn block", onclick: submit }, first ? "Сохранить пароль и войти" : "Войти"))),
    h("button", { class: "back", style: "margin-top:16px", onclick: () => renderParentLogin(first ? "login" : "set", rec.value) }, first ? "У меня уже есть пароль" : "Первый вход или забыли пароль?"),
    h("button", { class: "back", style: "margin-top:6px;color:var(--hint)", onclick: () => renderLogin() }, icon("left", "sm"), "На главную")));
}
async function renderParent() {
  document.getElementById("tabs").classList.add("hidden");
  skeleton(90, 160, 200, 140);
  const r = await api("/parent");
  S.me.today = r.today;                               // для подписей сроков заданий
  const st = r.month, color = p => p == null ? "var(--hint)" : p >= 85 ? "var(--P)" : p >= 70 ? "var(--L)" : "var(--A)";
  const first = r.student.split(" ")[1] || r.student;
  const hw = r.homework.filter(x => !x.done && daysLeft(x.due_date) >= 0);
  mount("fade",
    h("div", { class: "hero rise" }, h("div", { class: "row" }, h("div", { class: "avatar", style: "background:linear-gradient(135deg,#22c55e,#0ea5e9)" }, initials(r.student)),
      h("div", { class: "grow" }, h("h1", {}, r.student), h("div", { class: "sub" }, r.group, " · ", fmtDateLong(r.today))))),
    h("div", { class: "kpis rise" },
      h("div", { class: "kpi" }, h("b", { style: `color:${color(st.percent)}` }, st.percent == null ? "—" : st.percent + "%"), h("span", {}, "посещаемость за 30 дней")),
      h("div", { class: "kpi" }, h("b", { style: `color:${color(r.semester_percent)}` }, r.semester_percent == null ? "—" : r.semester_percent + "%"), h("span", {}, "за семестр"))),
    r.streak >= 3 || r.badges.length ? h("div", { class: "card rise streak-card row" }, h("div", { class: "flame on" }, "🔥", h("b", { class: "num" }, r.streak)),
      h("div", { class: "grow" }, h("b", {}, r.streak >= 3 ? `${first}: ${r.streak} ${plural(r.streak, "пара", "пары", "пар")} подряд без пропусков` : `${first} получает значки за посещаемость`),
        r.badges.length ? h("div", { class: "muted small" }, "Значки: " + r.badges.join(" ")) : null)) : null,
    h("div", { class: "section rise" }, `Сегодня · ${r.lessons.length ? r.lessons.length + " " + plural(r.lessons.length, "пара", "пары", "пар") : "пар нет"}`),
    r.lessons.length ? h("div", { class: "list rise" }, r.lessons.map(l => h("div", { class: "item" + (l.cancelled || l.moved ? " lesson-off" : "") },
      h("div", { class: "time", style: "min-width:48px" }, l.t_start), h("div", { class: "grow", style: "min-width:0" }, h("div", { class: "ellipsis", style: "font-weight:600" }, l.subject),
        h("div", { class: "muted tiny" }, [l.kind, l.room ? "ауд. " + l.room : null].filter(Boolean).join(" · "))),
      l.cancelled ? h("span", { class: "badge A" }, "отменена") : l.moved ? h("span", { class: "badge L" }, "перенесена") : l.status ? h("span", { class: "badge " + l.status }, ST[l.status]) : h("span", { class: "badge kind" }, "—"))))
      : h("div", { class: "card rise muted small center" }, "Сегодня занятий нет"),
    st.P + st.L + st.A + st.N + st.E ? [h("div", { class: "section rise" }, "Последние 30 дней"),
      h("div", { class: "card rise" }, h("div", { class: "legend", style: "display:grid;grid-template-columns:1fr 1fr;gap:6px" }, [["P", "Был"], ["L", "Опоздал"], ["A", "Не был"], ["N", "Не ответил"], ["E", "Уважит."]].map(([k, t]) =>
        h("div", {}, h("span", { class: "dot", style: `background:var(--${k})` }), " ", t, " ", h("b", {}, st[k]))))),
      r.subjects.length ? h("div", { class: "list rise" }, r.subjects.map(sb => h("div", { class: "item" }, h("div", { class: "grow" }, h("div", { class: "ellipsis", style: "font-weight:600" }, sb.subject),
        h("div", { class: "muted tiny" }, `пропусков ${sb.missed} · опозданий ${sb.L}`)), h("span", { class: "pct", style: `color:${color(sb.percent)}` }, sb.percent == null ? "—" : sb.percent + "%")))) : null] : null,
    r.grades ? [h("div", { class: "section rise" }, "Оценки · " + r.grades.title.toLowerCase()), h("div", { class: "card rise" },
      h("div", { class: "row", style: "margin-bottom:8px" }, h("b", { class: "grow" }, "Средний балл"), h("b", { style: "font-size:20px" }, r.grades.avg == null ? "—" : String(r.grades.avg).replace(".", ","))),
      h("div", { style: "display:flex;flex-wrap:wrap;gap:6px" }, r.grades.items.map(x => h("span", { class: "badge kind" }, x.name, ": ", h("b", {}, x.value || "—")))),
      r.grades.missed_total != null ? h("div", { class: "muted tiny", style: "margin-top:8px" }, `Пропущено часов: ${r.grades.missed_total}` + (r.grades.missed_bad != null ? `, без уважительной причины: ${r.grades.missed_bad}` : "")) : null)] : null,
    hw.length ? [h("div", { class: "section rise" }, "Задания", h("span", {}, hw.length)), h("div", { class: "list rise" }, hw.map(x => h("div", { class: "item" },
      h("div", { class: "grow", style: "min-width:0" }, h("div", { class: "ellipsis", style: "font-weight:600" }, x.subject, " · ", x.title)), h("span", { class: "badge " + dueCls(x.due_date) }, dueText(x.due_date)))))] : null,
    r.announcements.length ? [h("div", { class: "section rise" }, "Объявления группы"), r.announcements.slice(0, 3).map(a => h("div", { class: "card rise" + (a.pinned ? " pinned" : "") },
      a.title ? h("b", {}, a.title) : null, h("div", { style: "white-space:pre-wrap;margin-top:2px" }, a.text)))] : null,
    h("div", { class: "btns rise" }, h("button", { class: "btn plain", onclick: () => setTimeout(openAppearance, 0) }, icon("sun", "sm"), "Оформление"),
      h("button", { class: "btn danger", onclick: () => confirmDo("Выйти из аккаунта родителя?", logoutApp) }, icon("logout", "sm"), "Выйти")),
    copyrightFooter());
}
function issueParentCode(s, recordInput) {
  if (!(s.record_no || "").trim()) return toast(recordInput?.trim() ? "Сначала сохраните номер студенческого" : "Сначала укажите номер студенческого", "alert");
  confirmDo(`Выдать код для родителя ${s.full_name}? Родитель сможет смотреть посещаемость, оценки и задания (без изменений).`, () => safe(async () => {
    const r = await api(`/students/${s.id}/parent-code`, { body: {} });
    notify(); closeSheet();
    const until = new Date(r.expires * 1000).toLocaleString("ru", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
    const msg = `Вход для родителей в «Куратор +»:\n1) Откройте ${location.origin} или приложение\n2) «Родитель» → «Первый вход или забыли пароль?»\n3) Номер студенческого: ${r.record_no}, код: ${r.code}\nКод одноразовый, действует до ${until}.`;
    openSheet(h("div", { class: "center", style: "padding:6px 0" }, h("div", { class: "muted small" }, "Для родителя · " + s.full_name),
        h("div", { class: "code pop", style: "font-size:46px;letter-spacing:10px;margin:10px 0" }, r.code), h("div", { class: "muted small" }, "Одноразовый · действует до " + until)),
      h("div", { class: "note", style: "font-size:14px;margin-top:12px" }, "Передайте код родителю (можно через студента). Родитель видит только данные этого студента и ничего не может изменить."),
      h("div", { class: "btns" }, h("button", { class: "btn ghost", onclick: () => navigator.clipboard?.writeText(msg).then(() => toast("Скопировано", "check")) }, icon("copy", "sm"), "Копировать с инструкцией")));
  }));
}

/* запуск — после того как загружены все скрипты (app.js, views.js, features.js) */
boot();
