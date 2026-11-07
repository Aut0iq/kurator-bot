"use strict";



function renderOnboarding() {
  const name = h("input", { placeholder: "Например, 15-116П" });
  let myRole = "head";
  const roleChips = h("div", { class: "chips" });
  const drawRole = () => roleChips.replaceChildren(...[["head", "Староста"], ["curator", "Куратор"]].map(([k, v]) => h("button", { class: "chip " + (myRole === k ? "on" : ""), onclick: () => { myRole = k; selTick(); drawRole(); } }, v)));
  drawRole();
  const code = h("input", { placeholder: "Код из приглашения", style: "text-transform:uppercase;letter-spacing:3px;font-weight:700" });
  const q = new URLSearchParams(location.search);
  code.value = (q.get("join") || q.get("staff") || "").toUpperCase();
  mount("fade",
    h("div", { class: "hero rise", style: "padding-top:34px;text-align:center" },
      h("img", { class: "brand-logo pop", src: "/static/logo.webp", alt: "Куратор +", width: 84, height: 84, style: "display:block;margin:0 auto 14px" }),
      h("h1", { style: "font-size:26px" }, "Куратор +"),
      h("div", { class: "sub", style: "font-size:15px;margin-top:6px" }, "Опрос перед каждой парой, журнал, прогулы и отчёт для деканата — без таблиц")),
    h("div", { class: "card rise" },
      h("div", { class: "row" }, h("div", { class: "tile c1 qa", style: "padding:0;box-shadow:none;width:38px;height:38px;display:grid;place-items:center;border-radius:12px" }, icon("shield")),
        h("div", {}, h("b", {}, "Я староста или куратор"), h("div", { class: "muted small" }, "Создайте группу и пригласите студентов"))),
      h("label", { class: "f" }, "Название группы"), name,
      h("label", { class: "f" }, "Я в этой группе"), roleChips,
      h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
        await api("/group", { body: { name: name.value, role: myRole } }); notify(); confetti(); boot();
      }) }, "Создать группу"))),
    h("div", { class: "card rise" },
      h("div", { class: "row" }, h("div", { class: "tile c5", style: "width:38px;height:38px;display:grid;place-items:center;border-radius:12px" }, icon("user")),
        h("div", {}, h("b", {}, "У меня есть приглашение"), h("div", { class: "muted small" }, "Проще всего — перейти по ссылке старосты. Или введите код:"))),
      h("label", { class: "f" }, "Код группы"), code,
      h("div", { class: "btns" }, h("button", { class: "btn ghost", onclick: act(async () => {
        await api("/join", { body: { code: code.value } }); notify(); boot();
      }) }, "Вступить"))),
    demoButton(), copyrightFooter());
  if (store.get("intent") === "create") { store.set("intent", null); setTimeout(() => { name.focus(); name.scrollIntoView({ block: "center", behavior: "smooth" }); }, 400); }
}


async function renderRegister() {
  const { students } = await api("/students");
  const name = h("input", { placeholder: "Фамилия Имя", autocomplete: "name" });
  const free = students.filter(s => !s.linked);
  mount("fade",
    h("div", { class: "hero rise", style: "padding-top:30px" },
      h("div", { class: "avatar pop", style: "margin-bottom:14px" }, groupMark(S.me.group.name) || "Г"),
      h("h1", {}, "Вы в группе ", S.me.group.name, " 👋"),
      h("div", { class: "sub", style: "font-size:15px;margin-top:6px" }, "Осталось представиться — так отметки будут вашими")),
    h("div", { class: "card rise" }, h("label", { class: "f", style: "margin-top:0" }, "Фамилия и имя, как в журнале"), name,
      h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
        const r = await api("/me/register", { body: { full_name: name.value } });
        if (r.choose) return chooseSelf(r.choose, name.value);
        notify(); confetti(); if (r.matched) toast("Нашли вас в списке группы — оценки доступны", "check"); boot();
      }) }, "Готово"))),
    free.length ? [h("div", { class: "section rise" }, "Или найдите себя в списке"),
      h("div", { class: "list rise" }, free.map(s => h("div", { class: "item tap", onclick: () => confirmDo(`Вы — ${s.full_name}?`, () =>
        safe(async () => { await api(`/students/${s.id}/claim`, { body: {} }); notify(); boot(); })) }, ava(s.full_name), h("div", { class: "grow" }, s.full_name), icon("right", "sm chev"))))] : null);
}

function chooseSelf(list, typed) {
  openSheet(h("h3", {}, "Это вы?"), h("p", { class: "muted small" }, "В списке группы несколько похожих записей — выберите свою."),
    h("div", { class: "list" }, list.map(c => h("div", { class: "item tap", onclick: act(async () => {
      await api(`/students/${c.id}/claim`, { body: {} }); notify(); closeSheet(); confetti(); boot(); }) },
      ava(c.full_name), h("div", { class: "grow" }, h("b", {}, c.full_name), c.record_no ? h("div", { class: "muted tiny" }, "№ " + c.record_no) : null), icon("right", "sm chev")))),
    h("div", { class: "btns" }, h("button", { class: "btn plain", onclick: act(async () => {
      await api("/me/register", { body: { full_name: typed, new: true } }); closeSheet(); notify(); boot(); }) }, "Меня здесь нет")));
}


let liveTimer = null;
async function renderHome() {
  clearInterval(liveTimer);
  if (!S.homeLoaded) skeleton(90, 230, 120, 120);
  const [day, live, ann, hw, ach] = await Promise.all([api("/day?date=" + S.me.today), api("/live"), api("/announcements"),
    api("/homework").catch(() => null), S.me.student ? api("/achievements").catch(() => null) : null]);
  S.hwCache = hw;
  S.homeLoaded = true;
  const g = S.me.group, first = (S.me.user.first_name || "").trim();
  const hero = h("div", { class: "hero rise" },
    h("div", { class: "row" }, h("div", { class: "avatar" }, groupMark(g.name) || "Г"),
      h("div", { class: "grow" }, h("h1", {}, greeting(), first ? ", " + first : ""),
        h("div", { class: "sub" }, g.name, " · ", fmtDateLong(S.me.today), S.me.week ? ` · ${S.me.week}-я неделя (${S.me.week % 2 ? "нечёт" : "чёт"})` : "")),
      h("button", { class: "icon-btn", onclick: openGuide, title: "Как это работает" }, icon("help"))));

  const parts = [hero];
  if (day.period) parts.push(h("div", { class: "card rise row", style: "background:linear-gradient(135deg,color-mix(in srgb,var(--E) 16%,var(--card)),var(--card))" },
    h("div", { class: "tile c5", style: "width:42px;height:42px;border-radius:13px;display:grid;place-items:center" }, icon("palm")),
    h("div", {}, h("b", {}, PERIODS[day.period.kind], day.period.title ? ": " + day.period.title : ""),
      h("div", { class: "muted small" }, `до ${fmtDate(day.period.d2)} · регулярных пар нет, опросы не приходят`))));
  const pwHint = passwordHint();
  if (pwHint) parts.push(pwHint);
  parts.push(liveCard(live, day));
  if (ach?.student) parts.push(streakCard(ach));
  const hwCard = homeworkHomeCard(hw);
  if (hwCard) parts.push(hwCard);
  if ([12, 1, 5, 6, 7].includes(+S.me.today.slice(5, 7))) parts.push(wrappedCard());
  if (can("settings", "schedule", "invite")) parts.push(onboardingCard());


  if (day.lessons.length) {
    const nm = new Date().getHours() * 60 + new Date().getMinutes();
    parts.push(h("div", { class: "section rise" }, `Сегодня · ${day.lessons.length} ${plural(day.lessons.length, "пара", "пары", "пар")}`,
      h("a", { onclick: () => go("schedule") }, "Неделя")));
    parts.push(h("div", { class: "timeline" }, day.lessons.map(l => {
      const off = l.cancelled || l.moved;
      const st = off ? "past" : nm > toMin(l.t_end) ? "past" : nm >= toMin(l.t_start) ? "now" : "";
      const marked = Object.values(l.counts).reduce((a, b) => a + b, 0), present = (l.counts.P || 0) + (l.counts.L || 0);
      return h("div", { class: "tl rise " + st },
        h("div", { class: "rail" }, h("span", { class: "dot" + (st === "now" ? " pulse" : "") })),
        h("div", { class: "card tap" + (off ? " lesson-off" : ""), onclick: () => off ? openLessonInfo(l, S.me.today) : can("attendance") ? openAttendance(l, S.me.today) : openLessonInfo(l, S.me.today) },
          h("div", { class: "row" }, h("div", { class: "time" }, l.t_start, h("small", {}, " – ", l.t_end)),
            l.kind ? h("span", { class: "badge kind" }, KIND_SHORT[l.kind] || l.kind) : null, h("div", { class: "grow" }),
            off ? changeBadge(l) : isStaff() ? (marked ? h("span", { class: "badge " + (present === marked ? "P" : "L") }, `${present}/${marked}`) : st === "past" ? h("span", { class: "badge A" }, "не отмечено") : null)
              : (l.my_status ? h("span", { class: "badge " + l.my_status }, ST[l.my_status]) : null)),
          h("div", { style: "font-weight:700;margin-top:4px" }, l.subject, l.moved_from ? h("span", { class: "badge E", style: "margin-left:6px" }, "перенос") : null),
          h("div", { class: "muted small" }, l.room_was !== undefined ? h("b", { class: "room-new" }, "ауд. " + l.room + " (новая)") : (l.room ? "ауд. " + l.room : ""),
            [l.room ? "" : null, l.teacher].filter(x => x != null).join(" · ")),
          off ? h("div", { class: "note" }, changeLine(l)) : null,
          l.note ? h("div", { class: "note" }, "📌 ", l.note) : null,
          !isStaff() && l.checkin && !["P"].includes(l.my_status) ? codeInput() : null));
    })));
  }


  const pinned = ann.items.filter(a => a.pinned).slice(0, 2);
  if (pinned.length) parts.push(h("div", { class: "section rise" }, "Важное", h("a", { onclick: () => go(S.tab, "announcements") }, "Все")),
    pinned.map(a => h("div", { class: "card rise pinned" }, a.title ? h("b", {}, a.title) : null, h("div", { style: "white-space:pre-wrap;margin-top:2px" }, a.text))));


  const qa = (ic, c, title, sub, fn) => h("button", { class: "qa rise", onclick: fn }, h("div", { class: "tile " + c }, icon(ic)), h("b", {}, title), h("span", {}, sub));
  parts.push(h("div", { class: "section rise" }, "Быстрые действия"));
  parts.push(isStaff()
    ? h("div", { class: "qgrid" },
      qa("journal", "c2", "Журнал", "Посещаемость по дням", () => go("journal")),
      can("journal") ? qa("alert", "c4", "Прогулы", "Кто на грани", () => go("home", "truancy")) : null,
      can("journal") ? qa("chart", "c1", "Статистика", "Проценты и динамика", () => go("home", "stats")) : null,
      can("export") ? qa("table", "c3", "Отчёт", "Excel для деканата", () => exportSheet()) : null,
      qa("award", "c2", "Успеваемость", "Оценки за месяц", () => go("home", "grades")),
      qa("edit", "c5", "Задания", can("homework") ? "Выдать домашнее" : "Домашние и дедлайны", () => go("home", "homework")),
      qa("mega", "c6", "Объявления", can("announce") ? "Важное для группы" : "От старосты", () => go("home", "announcements")),
      qa("book", "c5", "База знаний", "Методички и конспекты", () => go("home", "files")),
      qa("sparkles", "c1", "Итоги семестра", "В формате историй", openWrapped))
    : h("div", { class: "qgrid" },
      qa("chart", "c1", "Мои пропуски", "Статистика по предметам", () => go("stats")),
      qa("award", "c2", "Мои оценки", "Ведомость за месяц", () => go("grades")),
      qa("edit", "c5", "Задания", "Что сдать на неделе", () => go("home", "homework")),
      qa("sparkles", "c1", "Значки", "Серии и награды", () => go("home", "badges")),
      qa("book", "c5", "База знаний", "Методички и конспекты", () => go("home", "files")),
      qa("mega", "c6", "Объявления", "От старосты", () => go("home", "announcements")),
      qa("sparkles", "c3", "Итоги семестра", "Твой семестр в историях", openWrapped),
    ));

  mount(S.anim, parts);
  if (ach?.student) checkNewBadges(false, ach);
  liveTimer = setInterval(async () => {
    if (S.tab !== "home" || S.sub || sheetStack.length || document.hidden) return;
    try { const nl = await api("/live"); const old = document.getElementById("live"); if (old) { const n = liveCard(nl, day, true); old.replaceWith(n); } } catch (_) {}
  }, 20000);
}

function liveCard(live, day, quiet = false) {
  const cls = "card live" + (quiet ? "" : " rise");
  if (!live.lesson) {
    const next = live.next;
    return h("div", { class: cls, id: "live" },
      h("div", { class: "phase" }, h("span", { class: "dot", style: "background:var(--hint)" }), next ? "Дальше" : "Сейчас"),
      next ? [h("h2", {}, next.subject), h("div", { class: "meta" }, `в ${next.t_start}`, next.room ? ` · ауд. ${next.room}` : "",
        " · опрос придёт за ", S.me.group.remind_minutes, " мин")]
        : [h("h2", {}, live.total_today ? "Пары на сегодня закончились" : "Сегодня пар нет"),
          h("div", { class: "meta" }, live.total_today ? "Хорошего вечера! Итоги уже в журнале." : "Опросы придут перед следующей парой автоматически.")]);
  }
  const l = live.lesson, c = live.counts;
  const phaseText = { poll: `Идёт опрос · до ${live.close_at}`, live: "Пара идёт", soon: `Через ${live.minutes_to_start} мин` }[live.phase];
  const head = [h("div", { class: "phase" }, h("span", { class: "dot pulse", style: `background:${live.phase === "poll" ? "var(--L)" : "var(--P)"}` }), phaseText),
    h("h2", {}, l.subject), h("div", { class: "meta" }, `${l.t_start}–${l.t_end}`, l.room ? ` · ауд. ${l.room}` : "", l.teacher ? ` · ${l.teacher}` : "")];

  if (isStaff()) {
    const n = k => (c[k] || []).length;
    const total = ["P", "L", "A", "E", "N", "none"].reduce((a, k) => a + n(k), 0);
    const present = n("P") + n("L");
    const legend = [["P", "На паре"], ["L", "Опаздывают"], ["A", "Не придут"], ["E", "Уважит."], ["N", "Не ответили"], ["none", "Ждём ответа"]]
      .filter(([k]) => n(k) || ["P", "none"].includes(k))
      .map(([k, t]) => h("div", {}, h("span", { class: "dot", style: `background:${k === "none" ? "var(--sep)" : `var(--${k})`}` }), t, h("b", {}, n(k))));
    const lbl = h("b");
    const r = ring([["var(--P)", n("P")], ["var(--L)", n("L")], ["var(--E)", n("E")], ["var(--A)", n("A")], ["var(--N)", n("N")]], total, "", `из ${total}`);
    r.querySelector(".lbl b").replaceWith(lbl);
    quiet ? (lbl.textContent = present) : countUp(lbl, present);
    const dayLesson = day.lessons.find(x => x.id === l.id) || l;
    return h("div", { class: cls, id: "live" }, head,
      h("div", { class: "ring-wrap" }, r, h("div", { class: "legend" }, legend)),
      h("div", { class: "btns" },
        h("button", { class: "btn ghost sm", onclick: () => openLiveList(live) }, icon("users", "sm"), "Кто где"),
        can("attendance") ? h("button", { class: "btn ghost sm", onclick: () => openCheckin(dayLesson, live.date) }, icon("key", "sm"), dayLesson.checkin ? dayLesson.checkin.code : "Код") : null,
        can("attendance") ? h("button", { class: "btn sm", onclick: () => openAttendance(dayLesson, live.date) }, icon("edit", "sm"), "Отметить") : null));
  }

  const my = live.my_status;
  const dayLesson = day.lessons.find(x => x.id === l.id) || l;
  const answer = (k, ic, color, text) => h("button", { class: `answer ${k} ${my === k ? "on" : ""}`, onclick: act(async () => {
    await api("/poll", { body: { lesson_id: l.id, date: live.date, status: k } });
    notify(); toast(k === "A" ? "Записал. Уважительную причину можно указать в чате с ботом" : "Ответ записан 👍", "check");
    renderHome();
  }) }, h("div", { class: "ic", style: `background:${color}` }, icon(ic, "sm")), h("span", {}, text));
  return h("div", { class: cls, id: "live" }, head,
    live.phase === "poll"
      ? h("div", { class: "answer-btns" }, answer("P", "check", "var(--P)", "Буду на паре"), answer("L", "clock", "var(--L)", "Опоздаю"), answer("A", "x", "var(--A)", "Не смогу прийти"))
      : h("div", { style: "margin-top:12px" }, my ? h("span", { class: "badge " + my, style: "font-size:14px;padding:6px 12px" }, ST[my]) : h("span", { class: "muted small" }, live.phase === "soon" ? "Опрос скоро придёт в чат" : "Опрос закрыт")),
    dayLesson.checkin && my !== "P" ? codeInput() : null,
    h("div", { class: "muted tiny", style: "margin-top:10px" }, `Ответили ${c.P + c.L + c.A + c.E} из ${c.P + c.L + c.A + c.E + c.N + c.none}`));
}

function openLiveList(live) {
  const c = live.counts;
  const group = (k, title) => (c[k] || []).length ? [h("div", { class: "section" }, title, h("span", { class: "badge " + (k === "none" ? "kind" : k) }, c[k].length)),
    h("div", { class: "list" }, c[k].map(s => h("div", { class: "item" }, ava(s.full_name), h("div", { class: "grow" }, s.full_name,
      s.reason ? h("div", { class: "muted small" }, "📄 ", s.reason) : null, !s.linked ? h("div", { class: "muted tiny" }, "нет аккаунта") : null))))] : null;
  openSheet(h("h3", {}, live.lesson.subject), h("div", { class: "muted small" }, `${live.lesson.t_start}–${live.lesson.t_end}`),
    group("P", "На паре"), group("L", "Опаздывают"), group("A", "Не придут"), group("E", "Уважительная"), group("N", "Не ответили"), group("none", "Ждём ответа"));
}

function onboardingCard() {
  const o = S.me.onboarding;
  if (!o || store.get("onb_hidden_" + S.me.group.id, false)) return null;
  const steps = [
    [o.linked > 0, "Пригласите студентов", o.linked ? `Подключились: ${o.linked}` : "Отправьте ссылку в беседу группы", shareInvite],
    [o.lessons > 0, "Внесите расписание", o.lessons ? `Пар в неделе: ${o.lessons}` : "Вручную или из Excel", () => go("schedule")],
    [o.semester, "Укажите даты семестра", "Для чётных/нечётных недель и каникул", () => go("more", "settings")],
    [o.polls, "Первый опрос", "Придёт сам перед ближайшей парой", null],
  ];
  const done = steps.filter(s => s[0]).length;
  if (done === steps.length) return null;
  return h("div", { class: "card rise" },
    h("div", { class: "row" }, h("b", { class: "grow", style: "font-size:16px" }, "Первые шаги"), h("span", { class: "muted small" }, `${done} из ${steps.length}`),
      h("button", { class: "icon-btn", style: "width:30px;height:30px;box-shadow:none;background:var(--soft)", onclick: e => {
        store.set("onb_hidden_" + S.me.group.id, true); e.currentTarget.closest(".card").remove(); } }, icon("x", "sm"))),
    h("div", { class: "progress", style: "margin:10px 0 4px" }, h("i", { style: `width:${100 * done / steps.length}%;background:var(--grad)` })),
    h("div", { class: "steps" }, steps.map(([ok, t, sub, fn], i) => h("div", { class: "step" + (ok ? " done" : ""), style: fn && !ok ? "cursor:pointer" : "", onclick: () => !ok && fn && fn() },
      h("div", { class: "mark" }, ok ? icon("check", "sm") : i + 1), h("div", { class: "grow" }, h("b", {}, t), h("div", { class: "muted small" }, sub)),
      fn && !ok ? icon("right", "sm chev") : null))));
}

function codeInput() {
  const inp = h("input", { inputmode: "numeric", maxlength: 4, placeholder: "• • • •", class: "code-input" });
  return h("div", { style: "margin-top:12px" }, h("div", { class: "small muted", style: "margin-bottom:6px" }, "🔑 Староста открыл отметку — введите код с доски:"),
    h("div", { class: "grid2" }, inp, h("button", { class: "btn", onclick: act(async () => {
      const r = await api("/checkin", { body: { code: inp.value } });
      notify(); confetti(); toast("Отмечено: " + r.subject, "check"); renderHome();
    }) }, "Отметиться")));
}

function openLessonInfo(l, date) {
  const manage = date && can("changes", "schedule");
  openSheet(h("h3", {}, l.subject), h("div", { class: "muted" }, `${date ? fmtDateLong(date) : WD[l.weekday]} · ${l.t_start}–${l.t_end}`),
    l.change ? h("div", { class: "card change-card " + l.change.kind, style: "margin-top:12px" }, changeLine(l),
      l.change.reason ? h("div", { class: "muted small", style: "margin-top:4px" }, l.change.reason) : null,
      l.change.by_name ? h("div", { class: "muted tiny", style: "margin-top:4px" }, "Отметил(а): " + l.change.by_name) : null) : null,
    h("div", { class: "list", style: "margin-top:14px" },
      l.kind ? h("div", { class: "item" }, icon("book", "sm"), "Тип", h("div", { class: "grow" }), h("b", {}, l.kind)) : null,
      l.room ? h("div", { class: "item" }, icon("home", "sm"), "Аудитория", h("div", { class: "grow" }), h("b", {}, l.room)) : null,
      l.teacher ? h("div", { class: "item" }, icon("user", "sm"), "Преподаватель", h("div", { class: "grow" }), h("b", {}, l.teacher)) : null,
      h("div", { class: "item" }, icon("calendar", "sm"), "Неделя", h("div", { class: "grow" }), h("b", {}, l.date ? "Разовая: " + fmtDate(l.date) : PARITY[l.parity]))),
    l.note ? h("div", { class: "note", style: "font-size:14px" }, "📌 ", l.note) : null,
    date && can("homework") ? h("div", { class: "btns" }, h("button", { class: "btn ghost", onclick: () => { closeSheet(); openHomeworkEditor({ subject: l.subject, lesson_id: l.id, lesson_date: date }); } }, icon("book", "sm"), "Задать домашнее задание")) : null,
    manage ? h("div", { class: "btns" }, l.change
      ? h("button", { class: "btn ghost", onclick: () => undoChange(l.change.id) }, icon("refresh", "sm"), "Вернуть как было")
      : h("button", { class: "btn ghost", onclick: () => openChangeSheet(l, date) }, icon("edit", "sm"), "Перенос / отмена")) : null);
}


function changeBadge(l) {
  return l.cancelled ? h("span", { class: "badge A" }, "отменена") : l.moved ? h("span", { class: "badge L" }, "перенесена") : null;
}
function changeLine(l) {
  const c = l.change || {};
  if (c.kind === "cancel") return "❌ Пара отменена";
  if (c.kind === "move") return `🔁 Перенесена на ${fmtDate(c.new_date)} (${WD[wdOf(c.new_date)].toLowerCase()}), ${c.new_start}–${c.new_end}` + (c.new_room ? `, ауд. ${c.new_room}` : "");
  if (c.kind === "room") return `🚪 Аудитория изменена: ${c.new_room}` + (l.room_was ? ` (была ${l.room_was})` : "");
  return "";
}
function undoChange(cid) {
  confirmDo("Вернуть пару по расписанию? Группа получит уведомление.", () => safe(async () => {
    await api("/changes/" + cid, { method: "DELETE" }); notify(); closeAllSheets(); toast("Пара снова по расписанию", "check"); render();
  }));
}
function openChangeSheet(l, date) {
  let kind = "cancel";
  const box = h("div");
  const nd = h("input", { type: "date", value: date, min: S.me.today });
  const t1 = h("input", { type: "time", value: l.t_start }), t2 = h("input", { type: "time", value: l.t_end });
  const room = h("input", { placeholder: l.room ? "Сейчас: " + l.room : "Например, 305" });
  const reason = h("input", { placeholder: "Например: преподаватель заболел", maxlength: 200 });
  const notifyBox = h("input", { type: "checkbox", checked: true });
  const tabs = h("div", { class: "seg", style: "margin:12px 0 4px" });
  const draw = () => {
    tabs.replaceChildren(...[["cancel", "Отменить"], ["move", "Перенести"], ["room", "Аудитория"]].map(([k, t]) =>
      h("button", { class: kind === k ? "on" : "", onclick: () => { kind = k; selTick(); draw(); } }, t)));
    box.replaceChildren(...[
      kind === "move" ? [h("label", { class: "f" }, "Новая дата"), nd,
        h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f" }, "Начало"), t1), h("div", {}, h("label", { class: "f" }, "Конец"), t2)),
        h("label", { class: "f" }, "Аудитория (если другая)"), room] : [],
      kind === "room" ? [h("label", { class: "f" }, "Новая аудитория"), room] : [],
      h("label", { class: "f" }, "Причина (необязательно)"), reason].flat());
  };
  draw();
  openSheet(h("h3", {}, l.subject), h("div", { class: "muted small" }, `${fmtDateLong(date)} · ${l.t_start}–${l.t_end}` + (l.room ? ` · ауд. ${l.room}` : "")),
    tabs, box,
    h("label", { class: "item", style: "padding:14px 2px 0;cursor:pointer" }, h("div", { class: "grow" }, "Сообщить группе"), h("span", { class: "switch" }, notifyBox, h("i"))),
    h("div", { class: "btns" }, h("button", { class: "btn block", onclick: act(async () => {
      const body = { date, kind, reason: reason.value, notify: notifyBox.checked };
      if (kind === "move") Object.assign(body, { new_date: nd.value, new_start: t1.value, new_end: t2.value, new_room: room.value });
      if (kind === "room") body.new_room = room.value;
      const r = await api(`/lessons/${l.id}/change`, { body });
      notify(); closeAllSheets();
      toast((kind === "cancel" ? "Пара отменена" : kind === "move" ? "Пара перенесена" : "Аудитория изменена") + (r.sent ? ` · уведомлено ${r.sent}` : ""), "check");
      render();
    }) }, "Сохранить")));
}
async function pickLessonToChange() {
  const dIn = h("input", { type: "date", value: S.me.today, min: S.me.today });
  const list = h("div", { class: "list", style: "margin-top:12px" });
  const load = async () => {
    list.replaceChildren(h("div", { class: "item muted small" }, "Загрузка…"));
    const day = await safe(() => api("/day?date=" + dIn.value));
    list.replaceChildren(...(day.lessons.length ? day.lessons.map(l => h("div", { class: "item tap", onclick: () => l.change ? openLessonInfo(l, dIn.value) : openChangeSheet(l, dIn.value) },
      h("div", { class: "time", style: "min-width:46px" }, l.t_start), h("div", { class: "grow" }, h("div", { style: "font-weight:600" }, l.subject),
        h("div", { class: "muted tiny" }, l.change ? changeLine(l) : [l.kind, l.room && "ауд. " + l.room].filter(Boolean).join(" · "))),
      changeBadge(l) || icon("right", "sm chev"))) : [h("div", { class: "item muted small" }, "В этот день пар нет")]));
  };
  dIn.onchange = load;
  openSheet(h("h3", {}, "Перенос или отмена пары"), h("p", { class: "muted small", style: "margin:4px 0 0" }, "Выберите день и пару — группа получит уведомление."),
    h("label", { class: "f" }, "День"), dIn, list);
  load();
}


async function openAttendance(lesson, date) {
  const { students } = await safe(() => api(`/attendance?lesson_id=${lesson.id}&date=${date}`));
  const marks = Object.fromEntries(students.map(s => [s.id, s.status]));
  const draws = new Map();
  const counter = h("div", { class: "legend-row", style: "margin:12px 2px 8px" });
  const recount = () => {
    const c = { P: 0, L: 0, A: 0, E: 0, N: 0 }; let empty = 0;
    for (const v of Object.values(marks)) v ? c[v]++ : empty++;
    counter.replaceChildren(...Object.entries(c).map(([k, n]) => h("span", {}, h("span", { class: "dot", style: `background:var(--${k})` }), `${ST[k]} ${n}`)),
      empty ? h("span", {}, h("span", { class: "dot", style: "background:var(--sep)" }), `без отметки ${empty}`) : null);
  };
  const seg = s => {
    const box = h("div", { style: "display:flex;gap:4px" });
    const draw = () => box.replaceChildren(...["P", "L", "A", "E"].map(k => h("button", {
      class: "cell " + (marks[s.id] === k ? k : ""), style: marks[s.id] === k ? "" : "color:var(--hint)", title: ST[k],
      onclick: e => { marks[s.id] = marks[s.id] === k ? null : k; selTick(); draw(); recount(); box.children[["P", "L", "A", "E"].indexOf(k)]?.classList.add("changed"); } }, ST_SHORT[k])));
    draws.set(s.id, draw); draw(); return box;
  };
  const setRest = () => { students.forEach(s => { if (!marks[s.id] || marks[s.id] === "N") marks[s.id] = "P"; draws.get(s.id)(); }); recount(); haptic("medium"); };
  recount();
  openSheet(h("h3", {}, lesson.subject), h("div", { class: "muted small" }, `${fmtDateLong(date)} · ${lesson.t_start}–${lesson.t_end}`),
    h("div", { class: "btns" },
      h("button", { class: "btn ghost sm", onclick: setRest }, icon("check", "sm"), "Остальные были"),
      h("button", { class: "btn ghost sm", onclick: () => openCheckin(lesson, date) }, icon("key", "sm"), lesson.checkin ? "Код " + lesson.checkin.code : "Код на доску"),
      can("changes", "schedule") ? h("button", { class: "btn ghost sm", onclick: () => openChangeSheet(lesson, date) }, icon("edit", "sm"), "Перенос / отмена") : null),
    counter,
    students.length ? h("div", { class: "list" }, students.map(s => h("div", { class: "item", style: "padding:9px 12px" },
      h("div", { class: "grow" }, h("div", { class: "ellipsis", style: "font-size:14px;font-weight:600" }, s.full_name),
        h("div", { class: "muted tiny" }, s.reason ? "📄 " + s.reason : s.source === "poll" ? "ответил в опросе" : s.source === "code" ? "отметился кодом" : s.status === "N" ? "не ответил на опрос" : !s.linked ? "нет аккаунта" : "")),
      seg(s))))
      : empty("users", "Пока нет студентов", "Пригласите группу — студенты появятся сами"),
    h("div", { class: "btns" }, h("button", { class: "btn block", onclick: act(async () => {
      await api("/attendance", { body: { lesson_id: lesson.id, date, marks } });
      notify(); closeSheet();
      const vals = Object.values(marks); if (vals.length && vals.every(v => v === "P" || v === "L")) { confetti(); toast("Все на месте! 🎉"); } else toast("Сохранено", "check");
      render();
    }) }, "Сохранить")));
}

function openCheckin(lesson, date) {
  if (lesson.checkin) return showCode(lesson, lesson.checkin);
  const mins = h("div", { class: "chips" });
  let val = 10;
  const draw = () => mins.replaceChildren(...[3, 5, 10, 15, 20].map(m => h("button", { class: "chip " + (m === val ? "on" : ""), onclick: () => { val = m; selTick(); draw(); } }, m + " мин")));
  draw();
  openSheet(h("h3", {}, "Код на доску"), h("p", { class: "muted small" },
    "Защита от «буду», а самого нет: покажите 4 цифры на доске — студенты введут их в приложении или пришлют боту. Отметиться можно только своим аккаунтом."),
    h("label", { class: "f" }, "Код действует"), mins,
    h("div", { class: "btns" }, h("button", { class: "btn block", onclick: act(async () => {
      const { checkin } = await api("/checkin/open", { body: { lesson_id: lesson.id, date, minutes: val } });
      lesson.checkin = checkin; haptic("heavy"); closeSheet(); showCode(lesson, checkin);
    }) }, icon("key", "sm"), "Сгенерировать код")));
}

function showCode(lesson, c) {
  const left = h("div", { class: "muted center num" });
  const bar = h("i", { style: "background:var(--grad);transition:width 1s linear" });
  const total = Math.max(1, c.expires_at - Math.floor(Date.now() / 1000));
  const body = openSheet(h("div", { class: "center", style: "padding:8px 0" }, h("div", { class: "muted" }, lesson.subject),
    h("div", { class: "code pop" }, c.code), left, h("div", { class: "progress", style: "margin:12px 20px 0" }, bar)),
    h("p", { class: "muted small center" }, "Студенты: «Главная» → ввести код, или отправить боту 4 цифры."),
    h("div", { class: "btns" },
      h("button", { class: "btn plain", onclick: () => { closeSheet(); openAttendance(lesson, S.me.today); } }, "К списку"),
      h("button", { class: "btn danger", onclick: act(async () => { await api("/checkin/" + c.id, { method: "DELETE" }); lesson.checkin = null; closeSheet(); render(); }) }, "Закрыть код")));
  const tick = () => {
    const s = c.expires_at - Math.floor(Date.now() / 1000);
    left.textContent = s > 0 ? `осталось ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "время вышло";
    bar.style.width = Math.max(0, 100 * s / total) + "%";
    if (s > 0 && body.isConnected) setTimeout(tick, 1000);
  };
  tick();
}


async function renderJournal() {
  if (S.journalDate) return renderJournalDay();
  const month = S.journalMonth || S.me.today.slice(0, 7);
  const data = await api("/journal/month?month=" + month);
  const first = parseIso(month + "-01"), pad = (first.getDay() + 6) % 7;
  const days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const shift = n => { const d = new Date(first.getFullYear(), first.getMonth() + n, 1); S.journalMonth = iso(d).slice(0, 7); S.anim = n > 0 ? "view-slide-l" : "view-slide-r"; selTick(); renderJournal(); };
  const cells = [...WDS.map(w => h("div", { class: "wd" }, w)), ...Array.from({ length: pad }, () => h("div"))];
  let todo = 0, done = 0;
  for (let i = 1; i <= days; i++) {
    const ds = `${month}-${String(i).padStart(2, "0")}`, info = data.days[ds];
    const future = ds > data.today;
    const cls = ["d", info?.lessons || info?.marked ? "has" : "", ds === data.today ? "today" : "", info?.period === "holiday" ? "holiday" : "", info?.period === "session" ? "session" : "", !info && future ? "off" : ""].join(" ");
    const dots = info && (info.lessons || info.marked) ? h("div", { class: "marks" }, info.marked ? h("i") : (!future && info.lessons ? h("i", { class: "todo" }) : null)) : h("div", { class: "marks" });
    if (info?.lessons && !future) info.marked ? done++ : todo++;
    cells.push(h("button", { class: cls, onclick: () => { if (!info && future) return; S.journalDate = ds; S.anim = "view-slide-l"; haptic(); renderJournal(); } }, i, dots));
  }
  mount(S.anim,
    pageTitle("Журнал"),
    h("div", { class: "card rise" },
      h("div", { class: "cal-head" }, h("button", { class: "icon-btn", onclick: () => shift(-1) }, icon("left")),
        h("b", {}, MONTHS[first.getMonth()], " ", first.getFullYear()), h("button", { class: "icon-btn", onclick: () => shift(1) }, icon("right"))),
      h("div", { class: "cal" }, cells)),
    h("div", { class: "legend-row rise" },
      h("span", {}, h("span", { class: "dot", style: "background:var(--P)" }), "отмечено"),
      h("span", {}, h("span", { class: "dot", style: "box-shadow:inset 0 0 0 1.5px var(--A)" }), "не отмечено"),
      h("span", {}, h("span", { class: "dot", style: "background:color-mix(in srgb,var(--E) 40%,transparent)" }), "каникулы"),
      h("span", {}, h("span", { class: "dot", style: "background:color-mix(in srgb,var(--L) 40%,transparent)" }), "сессия")),
    h("div", { class: "kpis rise" },
      h("div", { class: "kpi" }, countUp(h("b"), done), h("span", {}, "дней отмечено")),
      h("div", { class: "kpi" }, countUp(h("b", { style: todo ? "color:var(--A)" : "" }), todo), h("span", {}, "дней без отметок"))),
    can("export") ? h("button", { class: "btn block ghost rise", onclick: () => exportSheet() }, icon("download", "sm"), "Отчёт в Excel") : null);
}

async function renderJournalDay() {
  const ds = S.journalDate;
  const data = await api("/journal/day?date=" + ds);
  const back = h("button", { class: "back", onclick: () => { S.journalDate = null; S.anim = "view-slide-r"; renderJournal(); } }, icon("left", "sm"), "Календарь");
  const nav = n => { S.journalDate = addDays(ds, n); S.anim = n > 0 ? "view-slide-l" : "view-slide-r"; selTick(); renderJournal(); };
  const head = h("div", { class: "page-title rise" }, h("button", { class: "icon-btn", onclick: () => nav(-1) }, icon("left")),
    h("div", { class: "grow center" }, h("h1", { style: "font-size:21px" }, fmtDate(ds)), h("div", { class: "muted small" }, WD[wdOf(ds)])),
    h("button", { class: "icon-btn", onclick: () => nav(1) }, icon("right")));
  const parts = [back, head];
  if (data.period) parts.push(h("div", { class: "card rise row" }, icon("palm"), h("b", {}, PERIODS[data.period.kind], data.period.title ? ": " + data.period.title : "")));
  if (!data.lessons.length) parts.push(empty("calendar", "В этот день пар нет", "Можно добавить разовую пару — например, перенос или консультацию"));
  else if (!data.students.length) parts.push(empty("users", "Нет студентов", "Пригласите группу"));
  else {
    const table = h("table", {},
      h("tr", {}, h("th", { class: "name muted" }, "Студент"), data.lessons.map(l => h("th", {}, l.subject.length > 14 ? l.subject.slice(0, 13) + "…" : l.subject, h("small", {}, l.t_start),
        h("small", {}, (() => { const m = Object.values(data.marks[l.id] || {}); const p = m.filter(x => x.status === "P" || x.status === "L").length; return `${p}/${data.students.length}`; })())))),
      data.students.map(s => h("tr", {}, h("td", { class: "name" }, s.full_name),
        data.lessons.map(l => {
          const m = (data.marks[l.id] || {})[s.id];
          const b = h("button", { class: "cell " + (m?.status || "") }, m ? ST_SHORT[m.status] : "", m?.reason || m?.has_file ? h("span", { class: "clip" }, "📄") : null);
          b.onclick = () => !can("attendance") ? toast("Нет права отмечать посещаемость", "shield") : pickStatus(s, l, ds, m, st => {
            (data.marks[l.id] ||= {})[s.id] = st ? { ...(m || {}), status: st } : undefined;
            b.className = "cell changed " + (st || "");
            b.replaceChildren(st ? ST_SHORT[st] : "", st && (m?.reason || m?.has_file) ? h("span", { class: "clip" }, "📄") : "");
          });
          return h("td", {}, b);
        }))));
    parts.push(h("div", { class: "jgrid rise" }, table),
      h("div", { class: "legend-row rise" }, Object.entries(ST).map(([k, v]) => h("span", {}, h("span", { class: "dot", style: `background:var(--${k})` }), v)), h("span", {}, "📄 причина/справка")),
      h("p", { class: "muted small rise", style: "margin:0 6px 12px" }, can("attendance") ? "Нажмите на клетку, чтобы поставить или исправить отметку. Студенты отмечаются сами в опросе — здесь вы поправляете." : "Режим просмотра: отмечать посещаемость может староста или тот, кому он выдал это право."));
  }
  if (can("schedule")) parts.push(h("button", { class: "btn block ghost rise", onclick: () => editLesson({ date: ds }) }, icon("plus", "sm"), "Добавить разовую пару"));
  mount(S.anim, parts);
}

function pickStatus(s, l, ds, m, onSet) {
  const set = st => safe(async () => {
    await api("/attendance", { body: { lesson_id: l.id, date: ds, marks: { [s.id]: st } } });
    selTick(); onSet(st); closeSheet();
  });
  openSheet(h("h3", {}, s.full_name), h("div", { class: "muted small" }, `${l.subject} · ${fmtDate(ds)}, ${l.t_start}`),
    m?.reason ? h("div", { class: "note", style: "background:color-mix(in srgb,var(--E) 12%,transparent)" }, "📄 ", m.reason) : null,
    m?.has_file ? h("button", { class: "btn ghost block sm", style: "margin-top:10px", onclick: act(async () => {
      if (IN_TG) { await api("/attendance/file", { body: { lesson_id: l.id, date: ds, student_id: s.id } }); toast("Справка отправлена в чат с ботом", "check"); }
      else { await downloadFile(`/attendance/file?lesson_id=${l.id}&date=${ds}&student_id=${s.id}`, "spravka"); toast("Справка скачивается", "check"); } }) },
      icon("file", "sm"), IN_TG ? "Получить справку в чат" : "Открыть справку") : null,
    h("div", { class: "status-pick" }, Object.entries(ST).map(([k, v]) => h("button", { class: k, onclick: () => set(k) }, h("b", { style: "font-size:16px" }, ST_SHORT[k]), v))),
    m ? h("div", { class: "btns" }, h("button", { class: "btn plain", onclick: () => set(null) }, "Снять отметку")) : null);
}


async function renderSchedule() {
  const { lessons, periods, changes = [] } = await api("/lessons");
  const g = S.me.group, todayWd = wdOf(S.me.today);
  const curParity = S.me.week ? (S.me.week % 2 ? 1 : 2) : 0;
  if (S.schedWeek == null) S.schedWeek = curParity || 1;
  const wk = S.schedWeek;
  const regular = lessons.filter(l => !l.date), oneoff = lessons.filter(l => l.date);
  const shown = regular.filter(l => !wk || !l.parity || l.parity === wk);
  const both = regular.filter(l => !l.parity).length, odd = regular.filter(l => l.parity === 1).length, even = regular.filter(l => l.parity === 2).length;
  const parts = [pageTitle("Расписание", S.me.week ? h("span", { class: "badge" }, `${S.me.week}-я неделя`) : null)];

  const seg = h("div", { class: "seg rise" }, [[1, "Нечётная"], [2, "Чётная"], [0, "Все пары"]].map(([k, t]) =>
    h("button", { class: wk === k ? "on" : "", onclick: () => { S.schedWeek = k; S.anim = k > wk ? "view-slide-l" : "view-slide-r"; selTick(); render(); } },
      t, k && curParity === k ? h("span", { class: "now-dot" }) : null)));
  parts.push(seg);
  parts.push(h("div", { class: "card rise row" },
    h("div", { class: "tile " + (wk === 2 ? "c5" : wk === 1 ? "c1" : "c2"), style: "width:42px;height:42px;border-radius:13px;display:grid;place-items:center;font-weight:900" }, wk === 1 ? "I" : wk === 2 ? "II" : icon("calendar")),
    h("div", { class: "grow" },
      h("b", {}, wk === 1 ? "Нечётная неделя" : wk === 2 ? "Чётная неделя" : "Все пары семестра"),
      h("div", { class: "muted small" }, !S.me.week ? "Укажите начало семестра — бот сам поймёт, какая сейчас неделя"
        : wk && curParity === wk ? `Идёт сейчас (${S.me.week}-я неделя)` : wk ? `Будет на следующей неделе (${S.me.week + 1}-я)` : `${both} каждую неделю · ${odd} по нечётным · ${even} по чётным`)),
    can("settings") && !g.semester_start ? h("button", { class: "btn ghost sm", onclick: () => go("more", "settings") }, "Указать") : null));

  if (can("schedule")) parts.push(h("div", { class: "btns rise", style: "margin:0 0 6px" },
    h("button", { class: "btn ghost sm", onclick: scheduleImport }, icon("upload", "sm"), "Из Excel"),
    h("button", { class: "btn ghost sm", onclick: () => go("schedule", "periods") }, icon("palm", "sm"), `Каникулы${periods.length ? " · " + periods.length : ""}`),
    both && wk ? h("button", { class: "btn ghost sm", onclick: () => splitWeeks(regular) }, icon("copy", "sm"), "Разделить") : null));

  if (can("changes", "schedule")) parts.push(h("div", { class: "btns rise", style: "margin:0 0 6px" },
    h("button", { class: "btn ghost sm", onclick: pickLessonToChange }, icon("edit", "sm"), "Перенос / отмена пары")));
  const upcoming = changes.filter(c => (c.kind === "move" ? (c.new_date >= S.me.today || c.date >= S.me.today) : c.date >= S.me.today));
  if (upcoming.length) {
    parts.push(h("div", { class: "section rise" }, "Изменения в расписании", h("span", {}, upcoming.length)));
    parts.push(h("div", { class: "list rise" }, upcoming.map(c => h("div", { class: "item" + (can("changes", "schedule") ? " tap" : ""),
      onclick: () => can("changes", "schedule") && undoChange(c.id) },
      h("div", { class: "tile " + (c.kind === "cancel" ? "c4" : c.kind === "move" ? "c3" : "c5"), style: "width:34px;height:34px;border-radius:11px;display:grid;place-items:center;font-size:16px" },
        c.kind === "cancel" ? "❌" : c.kind === "move" ? "🔁" : "🚪"),
      h("div", { class: "grow" }, h("div", { style: "font-weight:600" }, c.subject, h("span", { class: "muted small", style: "font-weight:400" }, ` · ${fmtDate(c.date)}, ${c.t_start}`)),
        h("div", { class: "muted tiny" }, changeLine({ change: c, room_was: c.room }), c.reason ? " · " + c.reason : "")),
      can("changes", "schedule") ? h("span", { class: "muted tiny" }, "вернуть") : null))));
  }
  if (!shown.length) parts.push(empty("calendar", regular.length ? "На этой неделе пар нет" : "Расписание пустое",
    can("schedule") ? "Добавьте пары кнопкой + или загрузите из Excel (столбец «Неделя»: каждую / нечёт / чёт)" : "Староста ещё не внёс расписание"));
  WD.forEach((wd, i) => {
    const items = shown.filter(l => l.weekday === i).sort((x, y) => x.t_start.localeCompare(y.t_start));
    if (!items.length) return;
    const isToday = i === todayWd && (!wk || wk === curParity || !curParity);
    parts.push(h("div", { class: "section rise", style: isToday ? "color:var(--accent)" : "" }, wd + (isToday ? " · сегодня" : ""), h("span", {}, items.length)));
    parts.push(h("div", { class: "list rise" }, items.map(l => lessonRow(l, false, wk))));
  });
  if (oneoff.length && !wk) {
    parts.push(h("div", { class: "section rise" }, "Разовые пары"));
    parts.push(h("div", { class: "list rise" }, oneoff.map(l => lessonRow(l, true))));
  }
  mount(S.anim, parts);
  if (can("schedule")) fab("plus", () => editLesson({ parity: wk }));
}

function splitWeeks(regular) {
  const common = regular.filter(l => !l.parity);
  confirmDo(`Сделать раздельное расписание? ${common.length} ${plural(common.length, "пара", "пары", "пар")} «каждую неделю» станут копиями в нечётной и чётной неделе — дальше их можно менять по отдельности.`, () => safe(async () => {
    for (const l of common) {
      const body = { ...l, parity: 1 };
      await api("/lessons/" + l.id, { method: "PUT", body });
      await api("/lessons", { body: { ...l, parity: 2 } });
    }
    notify(); toast("Готово: недели разделены", "check"); render();
  }));
}

function lessonRow(l, showDate = false, wk = 0) {
  return h("div", { class: "item tap", onclick: () => can("schedule") ? editLesson(l) : openLessonInfo(l) },
    h("div", { class: "time", style: "width:46px;text-align:center" }, l.t_start, h("div", { class: "tiny muted", style: "font-weight:500" }, l.t_end)),
    h("div", { class: "grow" }, h("div", { class: "row", style: "gap:6px" }, l.kind ? h("span", { class: "badge kind" }, KIND_SHORT[l.kind] || l.kind) : null,
      h("b", { class: "ellipsis" }, l.subject)),
      h("div", { class: "muted small ellipsis" }, [showDate && fmtDate(l.date), l.room && "ауд. " + l.room, l.teacher, l.note && "📌 " + l.note].filter(Boolean).join(" · "))),
    l.parity && !wk ? h("span", { class: "badge " + (l.parity === 1 ? "" : "E") }, l.parity === 1 ? "нечёт" : "чёт") : null,
    l.parity && wk ? h("span", { class: "badge " + (l.parity === 1 ? "" : "E") }, "только " + (l.parity === 1 ? "нечёт" : "чёт")) : null,
    can("schedule") ? icon("right", "sm chev") : null);
}

function editLesson(l = {}) {
  const isOne = !!l.date;
  const f = {
    subject: h("input", { value: l.subject || "", placeholder: "Например, Математический анализ", list: "subj" }),
    weekday: h("select", {}, WD.map((d, i) => h("option", { value: i, selected: (l.weekday ?? Math.min(wdOf(S.me.today), 5)) === i }, d))),
    date: h("input", { type: "date", value: l.date || "" }),
    t_start: h("input", { type: "time", value: l.t_start || "08:30" }),
    t_end: h("input", { type: "time", value: l.t_end || "10:00" }),
    kind: h("select", {}, ["", ...KINDS].map(k => h("option", { value: k, selected: (l.kind || "") === k }, k || "—"))),
    parity: h("select", {}, PARITY.map((p, i) => h("option", { value: i, selected: (l.parity || 0) === i }, p))),
    teacher: h("input", { value: l.teacher || "", placeholder: "Иванов И.И." }),
    room: h("input", { value: l.room || "", placeholder: "204" }),
    note: h("input", { value: l.note || "", placeholder: "Например, «принести форму»" }),
  };
  const dl = h("datalist", { id: "subj" }, (S.me.subjects || []).map(s => h("option", { value: s })));

  f.t_start.addEventListener("change", () => { const m = toMin(f.t_start.value) + 90; f.t_end.value = `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; });
  const save = act(async () => {
    const body = Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value]));
    if (!isOne) body.date = null;
    await api("/lessons" + (l.id ? "/" + l.id : ""), { method: l.id ? "PUT" : "POST", body });
    notify(); closeSheet(); S.me = await api("/me"); render();
  });
  openSheet(h("h3", {}, l.id ? "Изменить пару" : isOne ? "Разовая пара" : "Новая пара"), dl,
    h("label", { class: "f" }, "Предмет"), f.subject,
    isOne ? [h("label", { class: "f" }, "Дата"), f.date]
      : h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f" }, "День недели"), f.weekday), h("div", {}, h("label", { class: "f" }, "Неделя"), f.parity)),
    h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f" }, "Начало"), f.t_start), h("div", {}, h("label", { class: "f" }, "Конец"), f.t_end)),
    h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f" }, "Тип занятия"), f.kind), h("div", {}, h("label", { class: "f" }, "Аудитория"), f.room)),
    h("label", { class: "f" }, "Преподаватель"), f.teacher,
    h("label", { class: "f" }, "Заметка для студентов"), f.note,
    h("div", { class: "btns" },
      l.id ? h("button", { class: "btn danger", style: "flex:0 0 52px", onclick: () => confirmDo("Удалить пару? Отметки по ней тоже удалятся.", () => safe(async () => {
        await api("/lessons/" + l.id, { method: "DELETE" }); closeSheet(); render(); })) }, icon("trash", "sm")) : null,
      l.id && !isOne ? h("button", { class: "btn plain", style: "flex:0 0 52px", title: "Копия", onclick: () => { const c = { ...l }; delete c.id; closeSheet(); editLesson(c); } }, icon("copy", "sm")) : null,
      h("button", { class: "btn", onclick: save }, l.id ? "Сохранить" : "Добавить")));
}

async function renderPeriods() {
  const { periods } = await api("/periods");
  mount(S.anim, pageTitle("Каникулы и сессии"),
    h("p", { class: "muted small rise", style: "margin:-4px 6px 12px" }, "В эти дни регулярные пары не идут и опросы не приходят. Разовые пары (зачёты, консультации) — работают."),
    periods.length ? h("div", { class: "list rise" }, periods.map(p => h("div", { class: "item" },
      h("div", { class: "tile " + (p.kind === "holiday" ? "c5" : p.kind === "session" ? "c3" : "c2"), style: "width:38px;height:38px;border-radius:12px;display:grid;place-items:center" }, icon(p.kind === "holiday" ? "palm" : "book", "sm")),
      h("div", { class: "grow" }, h("b", {}, PERIODS[p.kind], p.title ? ": " + p.title : ""), h("div", { class: "muted small" }, `${fmtDate(p.d1)} — ${fmtDate(p.d2)}`)),
      can("schedule") ? h("button", { class: "icon-btn", style: "box-shadow:none;background:var(--soft)", onclick: () => confirmDo("Удалить период?", () => safe(async () => { await api("/periods/" + p.id, { method: "DELETE" }); render(); })) }, icon("trash", "sm")) : null)))
      : empty("palm", "Периодов пока нет", "Добавьте каникулы или сессию"));
  if (can("schedule")) fab("plus", () => {
    let kind = "holiday";
    const chips = h("div", { class: "chips" });
    const draw = () => chips.replaceChildren(...Object.entries(PERIODS).map(([k, v]) => h("button", { class: "chip " + (k === kind ? "on" : ""), onclick: () => { kind = k; draw(); } }, v)));
    draw();
    const title = h("input", { placeholder: "Например, зимние" }), d1 = h("input", { type: "date", value: S.me.today }), d2 = h("input", { type: "date", value: addDays(S.me.today, 7) });
    openSheet(h("h3", {}, "Новый период"), h("label", { class: "f" }, "Тип"), chips, h("label", { class: "f" }, "Название (необязательно)"), title,
      h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f" }, "С"), d1), h("div", {}, h("label", { class: "f" }, "По"), d2)),
      h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
        await api("/periods", { body: { kind, title: title.value, d1: d1.value, d2: d2.value } }); notify(); closeSheet(); render(); }) }, "Добавить")));
  });
}


async function renderStudents() {
  const { students, grades_month } = await api("/students" + (S.showArch ? "?archived=1" : ""));
  const active = students.filter(s => !s.archived), linked = active.filter(s => s.tg_id).length;
  const notInGrades = grades_month ? active.filter(s => s.in_grades === false) : [];
  const dupes = active.filter(s => s.dupes && s.dupes.length);
  const canRemove = can("students", "remove_students");
  const filter = S.stuFilter || "all";
  const q = h("input", { placeholder: `Поиск среди ${students.length}`, style: "margin-bottom:12px" });
  const list = h("div", { class: "list rise" });
  const base = filter === "extra" ? notInGrades : filter === "dupes" ? dupes : students;
  const draw = () => {
    const f = q.value.trim().toLowerCase();
    const rows = base.filter(s => !f || s.full_name.toLowerCase().includes(f));
    list.replaceChildren(...(rows.length ? rows.map(s => h("div", { class: "item tap", style: s.archived ? "opacity:.55" : "", onclick: () => editStudent(s, students) },
      ava(s.full_name), h("div", { class: "grow" }, h("div", { class: "ellipsis", style: "font-weight:600" }, s.full_name),
        h("div", { class: "muted tiny" }, [s.record_no && "№ " + s.record_no, s.note || s.phone, s.dupes?.length ? "похож на: " + s.dupes.map(id => (students.find(x => x.id === id) || {}).full_name).filter(Boolean).join(", ") : null].filter(Boolean).join(" · "))),
      s.archived ? h("span", { class: "badge A" }, "отчислен") : s.in_grades === false ? h("span", { class: "badge L" }, "нет в ведомости")
        : s.tg_id ? h("span", { class: "badge P" }, "активен") : h("span", { class: "badge kind" }, "нет в боте"),
      icon("right", "sm chev")))
      : [h("div", { class: "item muted" }, filter === "all" ? (students.length ? "Никого не найдено" : "Пока пусто") : "Таких нет 👌")]));
  };
  q.oninput = draw; draw();
  const chip = (k, t) => h("button", { class: "chip " + (filter === k ? "on" : ""), onclick: () => { S.stuFilter = k; S.anim = "fade"; selTick(); render(); } }, t);
  mount(S.anim, pageTitle("Студенты", canSeeOnline() ? h("button", { class: "btn ghost sm", onclick: () => go("students", "online") }, h("span", { class: "dot", style: "background:var(--P)" }), "Кто в сети") : null),
    h("div", { class: "card rise", style: "background:linear-gradient(135deg,color-mix(in srgb,var(--a1) 14%,var(--card)),var(--card))" },
      h("div", { class: "row" }, h("div", { class: "grow" }, h("b", {}, `${linked} из ${active.length} с аккаунтом`),
        h("div", { class: "muted small" }, "Только подключённые получают опросы перед парой")),
        can("invite", "roles") ? h("button", { class: "btn sm", onclick: shareInvite }, icon("share", "sm"), "Пригласить") : null),
      h("div", { class: "progress", style: "margin-top:12px" }, h("i", { style: `width:${active.length ? 100 * linked / active.length : 0}%` }))),
    (notInGrades.length || dupes.length) ? h("div", { class: "chips rise" }, chip("all", "Все"),
      notInGrades.length ? chip("extra", `Нет в ведомости · ${notInGrades.length}`) : null,
      dupes.length ? chip("dupes", `Похожие · ${dupes.length}`) : null) : null,
    filter === "extra" ? h("div", { class: "card rise note", style: "background:color-mix(in srgb,var(--L) 10%,var(--card));margin-top:0" },
      "Эти студенты есть в списке группы, но их нет в последней ведомости. Это могут быть чужие, ошибочные записи или дубли. ",
      canRemove ? h("button", { class: "btn danger sm", style: "margin-top:10px;width:100%", onclick: () => confirmDo(
        `Удалить из группы ${notInGrades.length} ${plural(notInGrades.length, "запись", "записи", "записей")}? Их отметки посещаемости тоже удалятся, а у студентов пропадёт доступ к группе.`,
        () => safe(async () => { const r = await api("/students/delete", { body: { ids: notInGrades.map(s => s.id) } }); notify(); toast(`Удалено: ${r.deleted}`, "check"); S.stuFilter = "all"; render(); })) },
        icon("trash", "sm"), `Удалить всех лишних (${notInGrades.length})`) : null) : null,
    filter === "dupes" ? h("p", { class: "muted small rise", style: "margin:0 6px 10px" }, "Похоже, один человек записан дважды (например, «антонюк алексей» и «АНТОНЮК А.С.» из ведомости). Откройте запись и нажмите «Объединить» — отметки и оценки сольются.") : null,
    q, list,
    h("div", { class: "chips rise" }, h("button", { class: "chip " + (S.showArch ? "on" : ""), onclick: () => { S.showArch = !S.showArch; render(); } }, "Показывать отчисленных")));
  if (can("students")) fab("plus", addStudents);
}

function addStudents() {
  const ta = h("textarea", { placeholder: "Иванов Иван Иванович\nПетрова Мария Сергеевна\n…" });
  openSheet(h("h3", {}, "Добавить студентов"),
    h("p", { class: "muted small" }, "Необязательно: студенты могут вписать себя сами по ссылке. Но если список уже есть — вставьте его целиком, по одному ФИО в строке."),
    ta, h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
      const r = await api("/students", { body: { names: ta.value } }); notify(); toast(`Добавлено: ${r.added}`, "check"); closeSheet(); render();
    }) }, "Добавить")));
}

function editStudent(s, all = []) {
  const edit = can("students", "student_info"), manage = can("students"), remove = can("students", "remove_students");
  const twins = (s.dupes || []).map(id => all.find(x => x.id === id)).filter(Boolean);
  const inp = (key, attrs = {}) => h("input", { value: s[key] || "", disabled: !edit, ...attrs });
  const f = {
    full_name: inp("full_name", { placeholder: "Фамилия Имя Отчество", autocomplete: "off" }),
    record_no: inp("record_no", { placeholder: "Например, А-309" }),
    birth_date: inp("birth_date", { type: "date" }),
    phone: inp("phone", { type: "tel", placeholder: "+7…", inputmode: "tel" }),
    email: inp("email", { type: "email", placeholder: "name@mail.ru", inputmode: "email" }),
    parent_name: inp("parent_name", { placeholder: "ФИО родителя / законного представителя" }),
    parent_phone: inp("parent_phone", { type: "tel", placeholder: "+7…", inputmode: "tel" }),
    note: h("textarea", { value: s.note || "", disabled: !edit, style: "min-height:70px", placeholder: "Например, «староста подгруппы», «справка до 15.11»" }),
  };
  const dial = v => v ? h("a", { href: "tel:" + v.replace(/[^+\d]/g, ""), class: "icon-btn", style: "width:44px;height:44px;flex:none;box-shadow:none;background:var(--accent-soft);color:var(--accent)" }, icon("phone", "sm")) : null;
  const age = s.birth_date ? Math.floor((parseIso(S.me.today) - parseIso(s.birth_date)) / 3.15576e10) : null;
  const save = act(async () => {
    const body = Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value]));
    await api("/students/" + s.id, { method: "PATCH", body }); notify(); toast("Данные сохранены", "check"); closeSheet(); render();
  });
  openSheet(
    h("div", { class: "row", style: "margin-bottom:6px" }, ava(s.full_name), h("div", { class: "grow" }, h("h3", {}, s.full_name),
      h("div", { class: "muted small" }, [s.archived ? "Отчислен" : s.tg_id ? "Аккаунт подключён" : "Аккаунта нет", age ? `${age} ${plural(age, "год", "года", "лет")}` : null].filter(Boolean).join(" · ")))),
    h("div", { class: "section" }, "Основное"),
    h("label", { class: "f", style: "margin-top:0" }, "ФИО"), f.full_name,
    h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f" }, "№ студенческого"), f.record_no), h("div", {}, h("label", { class: "f" }, "Дата рождения"), f.birth_date)),
    h("div", { class: "section" }, "Контакты"),
    h("label", { class: "f", style: "margin-top:0" }, "Телефон"), h("div", { class: "row", style: "gap:8px" }, f.phone, dial(s.phone)),
    h("label", { class: "f" }, "Почта"), f.email,
    h("label", { class: "f" }, "Родитель / представитель"), f.parent_name,
    h("label", { class: "f" }, "Телефон родителя"), h("div", { class: "row", style: "gap:8px" }, f.parent_phone, dial(s.parent_phone)),
    h("label", { class: "f" }, "Заметка (видят староста, зам и куратор)"), f.note,
    edit ? h("div", { class: "btns" }, h("button", { class: "btn", onclick: save }, "Сохранить")) : null,
    edit ? [h("div", { class: "section" }, "Вход без Telegram"),
      h("div", { class: "card", style: "padding:12px 14px" },
        h("div", { class: "row" }, h("div", { class: "grow" },
          h("b", {}, s.auth?.password ? "Пароль задан" : "Пароль ещё не задан"),
          h("div", { class: "muted tiny" }, s.auth?.code_until && s.auth.code_until * 1000 > Date.now()
            ? "Выдан код, действует до " + new Date(s.auth.code_until * 1000).toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
            : "Вход: номер студенческого + пароль. Первый пароль и восстановление — по коду")),
          h("button", { class: "btn ghost sm", style: "flex:0 0 auto", onclick: () => issueLoginCode(s, f.record_no.value) }, icon("key", "sm"), "Выдать код"))),
      h("div", { class: "card", style: "padding:12px 14px" },
        h("div", { class: "row" }, h("div", { class: "grow" },
          h("b", {}, s.parent_auth?.password ? "Родитель подключён" : "Вход для родителя"),
          h("div", { class: "muted tiny" }, s.parent_auth?.code_until && s.parent_auth.code_until * 1000 > Date.now()
            ? "Код выдан, действует до " + new Date(s.parent_auth.code_until * 1000).toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
            : "Только просмотр: посещаемость, оценки, задания")),
          h("button", { class: "btn ghost sm", style: "flex:0 0 auto", onclick: () => issueParentCode(s, f.record_no.value) }, icon("users", "sm"), "Код родителю")))] : null,
    manage ? h("div", { class: "btns" },
      h("button", { class: "btn plain sm", onclick: act(async () => { await api("/students/" + s.id, { method: "PATCH", body: { archived: !s.archived } }); closeSheet(); render(); }) }, s.archived ? "Восстановить" : "Отметить отчисленным"),
      s.tg_id ? h("button", { class: "btn plain sm", onclick: act(async () => { await api("/students/" + s.id, { method: "PATCH", body: { unlink: true } }); closeSheet(); render(); }) }, "Отвязать Telegram") : null) : null,
    edit && twins.length ? [h("div", { class: "section" }, "Похожие записи"), h("div", { class: "list" }, twins.map(t => h("div", { class: "item" },
      ava(t.full_name), h("div", { class: "grow" }, h("b", {}, t.full_name), h("div", { class: "muted tiny" }, [t.tg_id ? "в боте" : "нет в боте", t.in_grades ? "есть в ведомости" : t.in_grades === false ? "нет в ведомости" : null].filter(Boolean).join(" · "))),
      h("button", { class: "btn ghost sm", onclick: () => confirmDo(`Объединить «${s.full_name}» и «${t.full_name}» в одну запись? Отметки, оценки и Telegram перейдут в одну карточку.`, () => safe(async () => {
        const keep = t.in_grades ? t.id : s.in_grades ? s.id : (t.tg_id ? t.id : s.id);
        await api("/students/merge", { body: { keep, drop: keep === s.id ? t.id : s.id } }); notify(); toast("Записи объединены", "check"); closeSheet(); render(); })) }, "Объединить"))))] : null,
    remove ? h("div", { class: "btns" }, h("button", { class: "btn danger sm", onclick: () => confirmDo(`Удалить ${s.full_name} из группы? Удалятся отметки посещаемости и оценки, а у студента пропадёт доступ к группе. ${manage ? "Если он просто ушёл — лучше отметить отчисленным." : ""}`, () => safe(async () => {
      await api("/students/" + s.id, { method: "DELETE" }); notify(); toast("Удалён из группы", "check"); closeSheet(); render(); })) }, icon("trash", "sm"), "Удалить из группы")) : null);
}

function shareInvite() {
  const g = S.me.group;
  if (!g.invite_link && !g.staff_link) return toast("Приглашение доступно старосте");
  const text = S.me?.telegram
    ? `👋 Ребята, подключил группу «${g.name}» к боту «Куратор +». Перейдите по ссылке и впишите ФИО — дальше бот сам будет спрашивать перед парами`
    : `👋 Ребята, подключил группу «${g.name}» к «Куратор +». Перейдите по ссылке и впишите ФИО — дальше приложение само будет спрашивать перед парами`;
  const staffPart = g.staff_link ? [h("div", { class: "section" }, "Куратор и зам. старосты"),
    h("div", { class: "card" }, h("div", { class: "muted small" }, "Отдельная ссылка для преподавателя-куратора. Вступивший по ней получает роль «Куратор»; потом в «Участниках» её можно сменить на «Зам. старосты» и настроить права."),
      h("div", { class: "btns" },
        S.me?.telegram ? h("button", { class: "btn ghost sm", onclick: () => { haptic(); openLink(`https://t.me/share/url?url=${encodeURIComponent(g.staff_link)}&text=${encodeURIComponent(`Приглашение в группу «${g.name}» в роли куратора`)}`); } }, icon("share", "sm"), "Отправить") : null,
        h("button", { class: "btn plain sm", onclick: () => navigator.clipboard?.writeText(g.staff_link).then(() => toast("Ссылка скопирована", "check")) }, icon("copy", "sm"), "Копировать"),
        h("button", { class: "btn plain sm", style: "flex:0 0 46px", title: "Перевыпустить", onclick: () => confirmDo("Старая ссылка для кураторов перестанет работать. Продолжить?", () => safe(async () => {
          const r = await api("/group/invite", { body: { staff: true } }); g.staff_link = r.staff_link; closeSheet(); shareInvite(); toast("Новая ссылка готова", "check"); })) }, icon("refresh", "sm"))))] : null;
  if (!g.invite_link) return openSheet(h("h3", {}, "Пригласить"), staffPart);
  openSheet(h("h3", {}, "Пригласить студентов"),
    h("div", { class: "card", style: "text-align:center;margin-top:12px" }, h("div", { class: "muted tiny", style: "font-weight:700;letter-spacing:.08em" }, "КОД ГРУППЫ"),
      h("div", { class: "code pop", style: "font-size:40px;letter-spacing:8px" }, g.invite_code || ""), h("div", { class: "muted small ellipsis" }, g.invite_link)),
    h("p", { class: "muted small" }, "Отправьте группе готовое сообщение со ссылкой. Студент нажмёт — код подставится сам, останется вписать ФИО."),
    S.me?.telegram ? h("div", { class: "btns" }, h("button", { class: "btn", onclick: () => {
      haptic(); openLink(`https://t.me/share/url?url=${encodeURIComponent(g.invite_link)}&text=${encodeURIComponent(text)}`);
    } }, icon("share", "sm"), "Отправить в беседу")) : null,
    h("div", { class: "btns" },
      h("button", { class: "btn plain sm", onclick: () => navigator.clipboard?.writeText(text + "\n" + g.invite_link).then(() => toast("Приглашение скопировано", "check")) }, icon("copy", "sm"), "Копировать"),
      can("settings") ? h("button", { class: "btn plain sm", onclick: () => confirmDo("Старая ссылка перестанет работать. Продолжить?", () => safe(async () => {
        const r = await api("/group/invite", { body: {} }); Object.assign(S.me.group, r); closeSheet(); shareInvite(); toast("Новая ссылка готова", "check"); })) }, icon("refresh", "sm"), "Перевыпустить") : null), staffPart);
}


async function renderStats() {
  const to = S.me.today, from = addDays(to, -S.statsDays + 1);
  const data = await api(`/stats?from=${from}&to=${to}`);
  const chips = h("div", { class: "chips rise" }, [[7, "Неделя"], [30, "Месяц"], [90, "3 месяца"], [180, "Семестр"]].map(([d, n]) =>
    h("button", { class: "chip " + (S.statsDays === d ? "on" : ""), onclick: () => { S.statsDays = d; S.anim = "fade"; selTick(); render(); } }, n)));
  const color = p => p == null ? "var(--hint)" : p >= 85 ? "var(--P)" : p >= 70 ? "var(--L)" : "var(--A)";
  const subjRows = list => h("div", { class: "list rise" }, list.map(s => h("div", { class: "item" },
    h("div", { class: "grow" }, h("div", { class: "ellipsis", style: "font-weight:600" }, s.subject),
      h("div", { class: "muted tiny" }, `пропусков ${s.missed} · опозданий ${s.L}` + (s.E ? ` · уваж. ${s.E}` : "")),
      h("div", { class: "progress", style: "margin-top:6px" }, h("i", { style: `width:${s.percent ?? 0}%;background:${color(s.percent)}` }))),
    h("span", { class: "pct", style: `color:${color(s.percent)}` }, s.percent == null ? "—" : s.percent + "%"))));

  if (!can("journal")) {
    const s = data.stats[0];
    if (!s || !s.total) return mount(S.anim, pageTitle("Мои пропуски"), chips, empty("chart", "Отметок пока нет", "Отвечайте на опросы перед парами — здесь появится статистика"));
    const big = h("b");
    let ach = null;
    try { ach = await api("/achievements"); } catch (_) {}
    return mount(S.anim, pageTitle("Мои пропуски"), chips, ach?.student ? streakCard(ach) : null,
      h("div", { class: "card live rise" }, h("div", { class: "ring-wrap", style: "margin-top:0" },
        (() => { const r = ring([["var(--P)", s.P], ["var(--L)", s.L], ["var(--E)", s.E], ["var(--A)", s.A], ["var(--N)", s.N]], s.total, "", "посещаемость"); r.querySelector(".lbl b").replaceWith(big); countUp(big, Math.round(s.percent ?? 0), "%"); return r; })(),
        h("div", { class: "legend" }, [["P", "Был"], ["L", "Опоздал"], ["A", "Не был"], ["N", "Не ответил"], ["E", "Уважит."]].map(([k, t]) =>
          h("div", {}, h("span", { class: "dot", style: `background:var(--${k})` }), t, h("b", {}, s[k])))))),
      data.subjects.length ? [h("div", { class: "section rise" }, "По предметам"), subjRows(data.subjects)] : null,
      h("div", { class: "section rise" }, "История"),
      h("div", { class: "list rise" }, data.history.slice(0, 40).map(r => h("div", { class: "item" }, h("span", { class: "muted small num", style: "width:42px" }, short(r.date)),
        h("div", { class: "grow ellipsis" }, r.subject), h("span", { class: "badge " + r.status }, ST[r.status]),
        r.status === "E" ? h("button", { class: "icon-btn", style: "width:30px;height:30px;box-shadow:none;background:var(--soft)", title: "Приложить справку",
          onclick: e => { e.stopPropagation(); confirmDo("Приложить фото или pdf справки к этой отметке?", () => safe(async () => {
            const file = await pickFile(".jpg,.jpeg,.png,.webp,.pdf"); if (!file) return;
            await apiUpload("/attendance/file", { lesson_id: r.lesson_id, date: r.date }, file);
            notify(); toast("Справка прикреплена — староста её увидит", "check"); })); } }, icon("upload", "sm")) : null))));
  }
  const rated = data.stats.filter(s => s.percent != null);
  const avg = rated.length ? +(rated.reduce((a, s) => a + s.percent, 0) / rated.length).toFixed(1) : null;
  const missed = data.stats.reduce((a, s) => a + s.missed, 0);
  mount(S.anim, pageTitle("Статистика"), chips,
    h("div", { class: "kpis rise" },
      h("div", { class: "kpi" }, avg == null ? h("b", {}, "—") : countUp(h("b", { style: `color:${color(avg)}` }), avg, "%"), h("span", {}, "средняя посещаемость")),
      h("div", { class: "kpi" }, countUp(h("b"), missed), h("span", {}, "пропусков всего"))),
    data.trend.length > 1 ? h("div", { class: "card rise" }, h("div", { class: "row" }, h("b", { class: "grow" }, "Динамика"), h("span", { class: "muted small" }, "% присутствующих по дням")), sparkline(data.trend.map(t => t.percent))) : null,
    can("export") ? h("button", { class: "btn block ghost rise", style: "margin-bottom:4px", onclick: () => exportSheet(from, to) }, icon("download", "sm"), "Отчёт в Excel") : null,
    data.subjects.length ? [h("div", { class: "section rise" }, "По предметам"), subjRows(data.subjects)] : null,
    h("div", { class: "section rise" }, "По студентам · сначала проблемные"),
    rated.length ? h("div", { class: "list rise" }, data.stats.map(s => h("div", { class: "item" }, ava(s.full_name),
      h("div", { class: "grow" }, h("div", { class: "ellipsis", style: "font-weight:600" }, s.full_name),
        h("div", { class: "muted tiny" }, s.total ? `пропусков ${s.missed} · опозданий ${s.L}` : "нет отметок"),
        s.percent != null ? h("div", { class: "progress", style: "margin-top:6px" }, h("i", { style: `width:${s.percent}%;background:${color(s.percent)}` })) : null),
      h("span", { class: "pct", style: `color:${color(s.percent)}` }, s.percent == null ? "—" : s.percent + "%"))))
      : empty("chart", "Пока нет отметок", "Статистика появится после первых опросов"));
}

async function renderTruancy() {
  const data = await api("/truancy");
  mount(S.anim, pageTitle("Прогулы"),
    h("p", { class: "muted small rise", style: "margin:-6px 6px 12px" }, `Порог — ${data.limit} ${plural(data.limit, "пропуск", "пропуска", "пропусков")} по предмету за семестр. Показаны те, кто достиг порога или в шаге от него. «Не ответил на опрос» тоже считается.`),
    data.rows.length ? h("div", { class: "list rise" }, data.rows.map(r => h("div", { class: "item", style: "align-items:flex-start" }, ava(r.full_name),
      h("div", { class: "grow" }, h("b", {}, r.full_name), h("div", { style: "display:flex;flex-wrap:wrap;gap:6px;margin-top:6px" },
        r.subjects.map(s => h("span", { class: "badge " + (s.over ? "A" : "L") }, `${s.subject}: ${s.missed}`)))))))
      : empty("shield", "Никто не на грани 👏", "Здесь появятся студенты с пропусками по предмету"),
    can("settings") ? h("button", { class: "btn plain block rise", onclick: () => go("more", "settings") }, icon("settings", "sm"), "Изменить порог") : null);
}

function scheduleImport() {
  const warn = h("p", { class: "muted small" }, "Шаблон скачается как .xlsx — заполните его в Excel и выберите файл ниже. ⚠️ Текущее регулярное расписание будет заменено (разовые переносы сохранятся).");
  openSheet(h("h3", {}, "Расписание из Excel"), warn,
    h("div", { class: "btns" }, h("button", { class: "btn ghost", onclick: act(async () => {
      await downloadFile("/schedule/template", "raspisanie.xlsx"); toast("Шаблон скачивается", "check"); }) }, icon("download", "sm"), "Скачать шаблон")),
    h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
      const file = await pickFile(".xlsx,.xlsm"); if (!file) return;
      const r = await apiUpload("/schedule/import", {}, file); notify(); closeSheet();
      toast(`Загружено пар: ${r.count}` + (r.errors?.length ? ` · пропущено строк: ${r.errors.length}` : ""), "check"); render();
    }) }, icon("upload", "sm"), "Выбрать файл и загрузить")));
}

function exportSheet(from, to) {
  let d1 = from || addDays(S.me.today, -29), d2 = to || S.me.today;
  const f = h("input", { type: "date", value: d1 }), t = h("input", { type: "date", value: d2 });
  const chips = h("div", { class: "chips" }, [["Неделя", 6], ["Месяц", 29], ["Семестр", null]].map(([n, days]) => h("button", { class: "chip", onclick: () => {
    t.value = S.me.today; f.value = days == null ? (S.me.group.semester_start || addDays(S.me.today, -120)) : addDays(S.me.today, -days); selTick(); } }, n)));
  openSheet(h("h3", {}, "Отчёт для деканата"),
    h("p", { class: "muted small" }, IN_TG ? "Excel-файл придёт в чат с ботом: лист «Сводка» с процентами и цветной «Журнал» — строки студенты, столбцы пары."
      : "Excel-файл скачается сразу: лист «Сводка» с процентами и цветной «Журнал» — строки студенты, столбцы пары."),
    chips, h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f" }, "С"), f), h("div", {}, h("label", { class: "f" }, "По"), t)),
    h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
      if (IN_TG) { await api("/export", { body: { from: f.value, to: t.value } }); toast("Отчёт отправлен в чат", "check"); }
      else await downloadFile(`/export?from=${f.value}&to=${t.value}`, "otchet.xlsx");
      notify(); closeSheet();
    }) }, icon("download", "sm"), IN_TG ? "Прислать в чат" : "Скачать отчёт")));
}


async function renderAnnouncements() {
  const { items } = await api("/announcements");
  mount(S.anim, pageTitle("Объявления"),
    items.length ? items.map(a => h("div", { class: "card rise" + (a.pinned ? " pinned" : "") },
      h("div", { class: "row", style: "gap:8px" }, a.pinned ? h("span", { class: "badge" }, icon("pin", "sm"), "закреплено") : null, h("div", { class: "grow" }),
        h("span", { class: "muted tiny" }, new Date(a.created_at * 1000).toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }))),
      a.title ? h("b", { style: "display:block;font-size:16px;margin-top:6px" }, a.title) : null,
      h("div", { style: "white-space:pre-wrap;margin-top:4px" }, a.text),
      h("div", { class: "row", style: "margin-top:10px" }, h("span", { class: "muted tiny grow" }, a.author_name ? "— " + a.author_name : "", can("announce") ? ` · доставлено ${a.delivered}` : ""),
        can("announce") ? [h("button", { class: "icon-btn", style: "width:32px;height:32px;box-shadow:none;background:var(--soft)", onclick: act(async () => {
          await api("/announcements/" + a.id, { method: "PATCH", body: { pinned: !a.pinned } }); render(); }) }, icon("pin", "sm")),
          h("button", { class: "icon-btn", style: "width:32px;height:32px;box-shadow:none;background:var(--soft)", onclick: () => confirmDo("Удалить объявление?", () => safe(async () => {
            await api("/announcements/" + a.id, { method: "DELETE" }); render(); })) }, icon("trash", "sm"))] : null)))
      : empty("mega", "Объявлений пока нет", can("announce") ? "Нажмите +, чтобы написать первое — придёт всей группе" : "Здесь появятся новости от старосты"));
  if (can("announce")) fab("plus", () => {
    const title = h("input", { placeholder: "Например, Собрание группы" }), text = h("textarea", { placeholder: "Что нужно донести до группы" });
    const pin = h("input", { type: "checkbox" });
    openSheet(h("h3", {}, "Новое объявление"), h("p", { class: "muted small", style: "margin:4px 0 0" }, S.me?.telegram ? "Придёт каждому студенту личным сообщением от бота." : "Появится у каждого студента в ленте приложения."),
      h("label", { class: "f" }, "Заголовок"), title, h("label", { class: "f" }, "Текст"), text,
      h("label", { class: "item", style: "padding:14px 2px 0;cursor:pointer" }, h("div", { class: "grow" }, "Закрепить сверху ленты"), h("span", { class: "switch" }, pin, h("i"))),
      h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
        const r = await api("/announce", { body: { title: title.value, text: text.value, pinned: pin.checked } });
        notify(); closeSheet(); toast(`Доставлено: ${r.sent}`, "check"); render(); }) }, icon("mega", "sm"), "Опубликовать")));
  });
}


async function renderFiles() {
  const { files, subjects } = await api("/files");
  const by = {};
  files.forEach(f => (by[f.subject] ||= []).push(f));
  const fmtSize = n => !n ? "" : n > 1e6 ? (n / 1e6).toFixed(1) + " МБ" : Math.ceil(n / 1e3) + " КБ";
  const ext = f => f.file_type === "photo" ? "IMG" : ((f.title.match(/\.(\w{2,4})$/) || [])[1] || "FILE").toUpperCase().slice(0, 4);
  mount(S.anim, pageTitle("База знаний"),
    h("p", { class: "muted small rise", style: "margin:-6px 6px 12px" }, IN_TG ? "Методички, конспекты и задания группы по предметам. Нажмите на файл — бот пришлёт его в чат."
      : "Методички, конспекты и задания группы по предметам. Нажмите на файл — он скачается."),
    files.length ? Object.entries(by).map(([subj, list]) => [h("div", { class: "section rise" }, subj, h("span", {}, list.length)),
      h("div", { class: "list rise" }, list.map(f => h("div", { class: "item tap", onclick: act(async () => {
        if (IN_TG) { await api(`/files/${f.id}/send`, { body: {} }); toast("Файл отправлен в чат", "check"); }
        else await downloadFile(`/files/${f.id}`, f.title);
        notify(); }) },
        h("div", { class: "file-ic" }, ext(f)), h("div", { class: "grow" }, h("div", { class: "ellipsis", style: "font-weight:600" }, f.title),
          h("div", { class: "muted tiny" }, [f.uploader_name, fmtSize(f.size), new Date(f.created_at * 1000).toLocaleDateString("ru")].filter(Boolean).join(" · "))),
        f.can_delete ? h("button", { class: "icon-btn", style: "width:32px;height:32px;box-shadow:none;background:var(--soft)", onclick: e => { e.stopPropagation(); confirmDo("Удалить файл?", () => safe(async () => {
          await api("/files/" + f.id, { method: "DELETE" }); render(); })); } }, icon("trash", "sm")) : icon("download", "sm chev"))))])
      : empty("book", "Пока пусто", IN_TG ? "Загрузите первую методичку кнопкой ↑ или просто пришлите файл боту" : "Загрузите первую методичку кнопкой ↑"));
  fab("upload", () => {
    let subj = subjects[0] || "Общее";
    const chips = h("div", { class: "chips", style: "flex-wrap:wrap" });
    const draw = () => chips.replaceChildren(...(subjects.length ? subjects : ["Общее"]).map(s => h("button", { class: "chip " + (s === subj ? "on" : ""), onclick: () => { subj = s; selTick(); draw(); } }, s)));
    draw();
    const filePick = async () => {
      const file = await pickFile("*/*"); if (!file) return;
      await apiUpload("/files/upload", { subject: subj }, file);
      notify(); closeSheet(); toast("Файл загружен в «" + subj + "»", "check"); render();
    };
    openSheet(h("h3", {}, "Загрузить файл"),
      h("p", { class: "muted small" }, IN_TG ? "Выберите предмет — затем пришлите файлы или фото в чат с ботом, или загрузите прямо здесь."
        : "Выберите предмет — затем файл с устройства. До 20 МБ."),
      chips,
      h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(filePick) }, icon("upload", "sm"), "Выбрать файл"),
        IN_TG ? h("button", { class: "btn ghost sm", onclick: act(async () => {
          await api("/files/upload", { body: { subject: subj } }); notify(); closeSheet(); toast("Пришлите файл в чат с ботом", "upload");
          setTimeout(goToBotChat, 1200); }) }, icon("share", "sm"), "Через бота") : null));
  });
}


async function renderMore() {
  const g = S.me.group, m = S.me.member;
  const role = S.me.role_name;
  const link = (ic, c, title, sub, fn, right) => h("div", { class: "item tap", onclick: fn },
    h("div", { class: "tile " + c, style: "width:34px;height:34px;border-radius:11px;display:grid;place-items:center" }, icon(ic, "sm")),
    h("div", { class: "grow" }, h("div", { style: "font-weight:600" }, title), sub ? h("div", { class: "muted tiny" }, sub) : null), right || icon("right", "sm chev"));
  const remind = h("input", { type: "checkbox", checked: !!m.reminders, onchange: e => safe(() => api("/me/reminders", { body: { on: e.target.checked } }))
    .then(() => { m.reminders = e.target.checked ? 1 : 0; selTick(); toast(e.target.checked ? "Напоминания включены" : "Напоминания выключены", "bell"); }) });
  const parts = [pageTitle("Ещё"),
    h("div", { class: "card rise row" }, h("div", { class: "avatar" }, groupMark(g.name) || "Г"),
      h("div", { class: "grow" }, h("b", { style: "font-size:17px" }, g.name), h("div", { class: "muted small" }, role, S.me.student ? " · " + S.me.student.full_name : ""))),
  ];
  if (isStaff()) parts.push(h("div", { class: "section rise" }, "Группа"), h("div", { class: "list rise" },
    can("invite", "roles") ? link("share", "c1", "Пригласить", can("roles") ? "Студентов, куратора, зама" : "Код " + (g.invite_code || ""), shareInvite) : null,
    can("settings") ? link("settings", "c5", "Настройки группы", "Опросы, семестр, часовой пояс", () => go("more", "settings")) : null,
    link("palm", "c2", "Каникулы и сессии", null, () => go("more", "periods")),
    link("mega", "c6", "Объявления", null, () => go("more", "announcements")),
    link("book", "c3", "База знаний", null, () => go("more", "files")),
    can("journal") ? link("chart", "c4", "Статистика", null, () => go("more", "stats")) : null,
    link("award", "c2", "Успеваемость", "Ведомость оценок за месяц", () => go("more", "grades")),
    link("edit", "c5", "Задания", "Домашние задания и дедлайны", () => go("more", "homework")),
    canSeeOnline() ? link("journal", "c1", "Журнал действий", "Кто, когда и что изменил", () => go("more", "audit")) : null,
    link("sparkles", "c3", "Итоги семестра", "Как прошёл семестр у группы", openWrapped)));
  else parts.push(h("div", { class: "section rise" }, "Группа"), h("div", { class: "list rise" },
    link("edit", "c5", "Задания", "Что сдать на этой неделе", () => go("more", "homework")),
    S.me.student ? link("award", "c2", "Значки и серии", "Награды за посещаемость", () => go("more", "badges")) : null,
    S.me.student ? link("sparkles", "c3", "Итоги семестра", "Твой семестр в формате историй", openWrapped) : null,
    canSeeOnline() ? link("journal", "c1", "Журнал действий", "Кто, когда и что изменил", () => go("more", "audit")) : null,
    link("mega", "c6", "Объявления", null, () => go("more", "announcements")),
    link("book", "c3", "База знаний", null, () => go("more", "files"))));

  parts.push(h("div", { class: "section rise" }, "Уведомления"), h("div", { class: "list rise" },
    h("label", { class: "item", style: "cursor:pointer" }, h("div", { class: "tile c3", style: "width:34px;height:34px;border-radius:11px;display:grid;place-items:center" }, icon("bell", "sm")),
      h("div", { class: "grow" }, h("div", { style: "font-weight:600" }, isStaff() ? "Напоминания и сводки" : "Напоминания"),
        h("div", { class: "muted tiny" }, isStaff() ? "Сводка по паре, итоги недели" : "Опросы перед парой приходят всегда — по ним ставится посещаемость")),
      h("span", { class: "switch" }, remind, h("i"))),
    pushRow()));
  const tp = themePrefs();
  parts.push(h("div", { class: "section rise" }, "Оформление"), h("div", { class: "list rise" },
    link("sun", "c3", "Тема и цвет", ({ system: "Как в системе", light: "Светлая", dark: "Тёмная" })[tp.mode] + " · " + ACCENTS[tp.accent].name.toLowerCase(), openAppearance,
      h("span", { class: "accent-dot", style: `background:linear-gradient(135deg,${ACCENTS[tp.accent].a.join(",")})` }))));

  let alone = false;
  if (can("roles")) {
    const data = await api("/members");
    S.permCatalog = data;
    const { members } = data;
    alone = members.length === 1;
    parts.push(h("div", { class: "section rise" }, `Участники · ${members.length}`), h("div", { class: "list rise" }, members.map(x => h("div", { class: "item " + (x.tg_id !== m.tg_id ? "tap" : ""), onclick: () => x.tg_id !== m.tg_id && editMember(x) },
      ava(x.student_name || x.full_name || "?"), h("div", { class: "grow" }, h("div", { class: "ellipsis", style: "font-weight:600" }, x.student_name || x.full_name),
        h("div", { class: "muted tiny" }, (x.username ? "@" + x.username + " · " : "") + x.role_name.toLowerCase() + (x.custom ? " · свои права" : ""))),
      x.tg_id === m.tg_id ? h("span", { class: "badge kind" }, "вы") : h("span", { class: "badge " + (x.role === "student" ? "kind" : "") }, x.role_name)))),
      h("p", { class: "muted tiny rise", style: "margin:0 8px 10px" }, "Зам. старосты — все права старосты. Куратору и студентам права настраиваются по отдельности: нажмите на участника."));
  }

  let appInfo = {};
  try { appInfo = await api("/app-info"); } catch (_) {}
  const appRows = [
    !NATIVE && appInfo.apk ? link("download", "c2", "Приложение для Android", "Установить на телефон" + (appInfo.size ? " · " + (appInfo.size > 1e6 ? (appInfo.size / 1e6).toFixed(1) + " МБ" : Math.ceil(appInfo.size / 1e3) + " КБ") : ""), () => openLink(location.origin + "/app.apk")) : null,
    NATIVE ? link("download", "c2", "Проверить обновления", appInfo.update_available ? `Доступна версия ${appInfo.version_name}` : "Версия " + (appInfo.installed?.name || appVer()), () => checkUpdates(),
      appInfo.update_available ? h("span", { class: "badge P" }, "новое") : null) : null,
    NATIVE?.resetServer ? link("refresh", "c5", "Адрес сервера", (NATIVE.serverUrl?.() || location.origin).replace(/^https?:\/\//, ""), () => confirmDo("Сменить адрес сервера? Потребуется войти заново.", () => NATIVE.resetServer())) : null,
    !IN_TG ? link("logout", "c4", "Выйти из аккаунта", "На этом устройстве", () => confirmDo("Выйти из аккаунта на этом устройстве?", logoutApp)) : null,
  ].filter(Boolean);
  if (S.me.super) parts.push(h("div", { class: "section rise" }, "Главный куратор"), h("div", { class: "list rise" },
    link("server", "c3", "Мониторинг сервера", "Нагрузка, статистика, резервные копии, ошибки", () => go("more", "server")),
    link("key", "c1", "Входы сотрудников", "Логины старост и кураторов, сброс пароля", () => go("more", "staff")),
    lockSwitchRow(),
    link("edit", "c5", "Сообщение при закрытом доступе", S.me.lock?.text || "Что увидят пользователи · рассылка в Telegram", () => openLockSheet())));
  if (appRows.length) parts.push(h("div", { class: "section rise" }, NATIVE ? "Приложение" + (NATIVE.version ? " · " + NATIVE.version() : "") : "Приложение"), h("div", { class: "list rise" }, appRows));

  if (S.me.staff_login) parts.push(h("div", { class: "section rise" }, "Аккаунт"), h("div", { class: "list rise" },
    link("key", "c5", "Вход по логину и паролю", S.me.staff_login.has_password ? "Логин " + S.me.staff_login.login : "Чтобы входить и без Telegram", staffLoginSheet,
      S.me.staff_login.has_password ? null : h("span", { class: "badge L" }, "не задан"))));
  else if (S.me.student && !S.demo && !S.me.demo) parts.push(h("div", { class: "section rise" }, "Аккаунт"), h("div", { class: "list rise" },
    S.me.has_password
      ? link("key", "c5", "Сменить пароль", "Вход по номеру студенческого" + (S.me.student?.record_no ? " " + S.me.student.record_no : ""), () => changePassword())
      : link("key", "c5", "Установить пароль", "Чтобы входить и без Telegram — по номеру студенческого", () => setPasswordSheet(),
          h("span", { class: "badge L" }, "не задан"))));
  parts.push(h("div", { class: "section rise" }, "Документы"), h("div", { class: "list rise" },
    link("shield", "c3", "Политики и согласие", "Согласие на обработку данных, политика, соглашение" + (S.me.consent_at ? " · согласие от " + new Date(S.me.consent_at * 1000).toLocaleDateString("ru") : ""), () => openDoc("consent"))));
  parts.push(h("div", { class: "section rise" }, "Помощь"), h("div", { class: "list rise" },
    link("help", "c1", "Как это работает", null, openGuide),
    S.me?.telegram ? link("bell", "c5", "Команды бота", "/today, /week, /here, /stats" + (isStaff() ? ", /announce, /export, /import" : ""), () => openSheet(h("h3", {}, "Команды бота"),
      h("div", { class: "list", style: "margin-top:12px" }, [["/today", "пары сегодня"], ["/tomorrow", "пары завтра"], ["/week", "расписание на неделю"], ["/here 1234", "отметиться кодом"], ["/stats", "посещаемость"], ["/remind on|off", "напоминания"],
        ...(isStaff() ? [["/invite", "приглашение"], ["/announce текст", "объявление"], ["/export 30", "отчёт в Excel"], ["/import", "расписание из Excel"]] : [])]
        .map(([c, t]) => h("div", { class: "item" }, h("b", { style: "font-family:ui-monospace,monospace;font-size:13px" }, c), h("div", { class: "grow muted small", style: "text-align:right" }, t)))))) : null),
    h("div", { class: "btns rise" }, alone
      ? h("button", { class: "btn danger", onclick: deleteGroup }, icon("trash", "sm"), "Удалить группу")
      : h("button", { class: "btn danger", onclick: leaveGroup }, icon("logout", "sm"), "Выйти из группы")),
    h("p", { class: "muted tiny center rise", style: "margin-top:16px" }, "Куратор + · бесплатно и без рекламы"), copyrightFooter());
  mount(S.anim, parts);
}

const ROLE_INFO = {
  head: ["Староста", "Все права. Только староста может назначить или снять другого старосту."],
  deputy: ["Зам. старосты", "Все те же права, что у старосты."],
  curator: ["Куратор", "Права настраиваются: по умолчанию видит журнал и статистику, выгружает отчёты, пишет объявления."],
  student: ["Студент", "Отвечает на опросы, видит свои пропуски. Можно выдать отдельные права — например, отмечать посещаемость."],
};


function deleteGroup() {
  confirmDo("Вы один в группе. Удалить группу «" + (S.me?.group?.name || "") + "» вместе со студентами, журналом, оценками и расписанием? Это нельзя отменить.",
    () => safe(async () => { await api("/leave", { body: { delete_group: true } }); notify(); toast("Группа удалена", "check"); S.tab = "home"; S.sub = null; boot(); }));
}
function leaveGroup() {
  confirmDo("Выйти из группы?", async () => {
    try { await api("/leave", { body: {} }); S.tab = "home"; S.sub = null; boot(); }
    catch (e) { if (/один в группе/.test(e.message)) deleteGroup(); else toast(e.message, "alert"); }
  });
}
async function editMember(x) {
  const { catalog, defaults } = S.permCatalog || (S.permCatalog = await api("/members"));
  const full = ["head", "deputy"].includes(x.role) || x.super;
  const meHead = S.me.member.role === "head" || S.me.super;
  const lockedHead = (x.role === "head" && !meHead) || x.super;
  const sel = new Set(x.perms_list);
  const roleBtn = (role) => h("button", { class: "chip " + (x.role === role ? "on" : ""), disabled: lockedHead || (role === "head" && !meHead),
    style: (role === "head" && !meHead) ? "opacity:.45" : "", onclick: act(async () => {
      if (role === x.role) return;
      await api("/members/role", { body: { tg_id: x.tg_id, role } }); notify(); closeSheet(); toast("Роль изменена", "check"); render();
    }) }, ROLE_INFO[role][0]);
  const rows = h("div", { class: "list" });
  const drawPerms = () => rows.replaceChildren(...catalog.map(p => {
    const inp = h("input", { type: "checkbox", checked: full || sel.has(p.key), disabled: full || lockedHead,
      onchange: e => { e.target.checked ? sel.add(p.key) : sel.delete(p.key); selTick(); dirty(); } });
    return h("label", { class: "item", style: "cursor:pointer;padding:11px 14px" + (full ? ";opacity:.7" : "") },
      h("div", { class: "grow" }, h("div", { style: "font-weight:600;font-size:14px" }, p.title), h("div", { class: "muted tiny" }, p.hint)),
      h("span", { class: "switch" }, inp, h("i")));
  }));
  const saveBtn = h("button", { class: "btn", disabled: true, onclick: act(async () => {
    await api("/members/perms", { body: { tg_id: x.tg_id, perms: [...sel] } }); notify(); toast("Права сохранены", "check"); closeSheet(); render();
  }) }, "Сохранить права");
  const dirty = () => { saveBtn.disabled = false; };
  drawPerms();
  openSheet(
    h("div", { class: "row", style: "margin-bottom:4px" }, ava(x.student_name || x.full_name || "?"),
      h("div", {}, h("h3", {}, x.student_name || x.full_name), h("div", { class: "muted small" }, [x.username && "@" + x.username, x.role_name].filter(Boolean).join(" · ")))),
    h("label", { class: "f" }, "Роль"),
    h("div", { class: "chips", style: "flex-wrap:wrap" }, ["student", "curator", "deputy", "head"].map(roleBtn)),
    h("p", { class: "muted small", style: "margin:0 4px" }, x.super ? "Главный куратор — все права всегда. Его роль и права изменить нельзя." : ROLE_INFO[x.role][1]),
    h("div", { class: "section", style: "margin-top:16px" }, "Права", full ? h("span", { class: "badge P" }, "все") : x.custom ? h("span", { class: "badge" }, "свои") : h("span", { class: "badge kind" }, "по умолчанию")),
    rows,
    !full && !lockedHead ? h("div", { class: "btns" },
      x.custom ? h("button", { class: "btn plain", onclick: act(async () => {
        await api("/members/perms", { body: { tg_id: x.tg_id, reset: true } }); notify(); toast("Права сброшены к роли", "check"); closeSheet(); render(); }) }, "Как у роли") : null,
      saveBtn) : null,
    !lockedHead ? h("div", { class: "btns" }, h("button", { class: "btn danger sm", onclick: () => confirmDo("Удалить участника из группы? Отметки сохранятся.", () => safe(async () => {
      await api("/members/" + x.tg_id, { method: "DELETE" }); closeSheet(); render(); })) }, icon("trash", "sm"), "Удалить из группы")) : null);
}

async function renderSettings() {
  const g = S.me.group;
  const f = {
    name: h("input", { value: g.name }),
    semester_start: h("input", { type: "date", value: g.semester_start || "" }),
    semester_end: h("input", { type: "date", value: g.semester_end || "" }),
    polls_enabled: h("input", { type: "checkbox", checked: !!g.polls_enabled }),
    remind_minutes: h("select", {}, [5, 10, 15, 20, 30, 45, 60].map(v => h("option", { value: v, selected: g.remind_minutes === v }, `за ${v} мин`))),
    summary_minutes: h("select", {}, [3, 5, 10, 15, 20, 30].map(v => h("option", { value: v, selected: g.summary_minutes === v }, `через ${v} мин`))),
    truancy_limit: h("select", {}, [2, 3, 4, 5, 6, 8, 10].map(v => h("option", { value: v, selected: g.truancy_limit === v }, `${v} ${plural(v, "пропуск", "пропуска", "пропусков")}`))),
    tz: h("select", {}, ["Europe/Kaliningrad", "Europe/Moscow", "Europe/Samara", "Asia/Yekaterinburg", "Asia/Omsk", "Asia/Novosibirsk", "Asia/Krasnoyarsk",
      "Asia/Irkutsk", "Asia/Yakutsk", "Asia/Vladivostok", "Asia/Magadan", "Asia/Kamchatka", "Asia/Almaty", "Asia/Tashkent", "Europe/Minsk"]
      .concat(g.tz).filter((v, i, a) => a.indexOf(v) === i).map(z => h("option", { value: z, selected: g.tz === z }, z.split("/")[1].replace("_", " ")))),
  };
  mount(S.anim, pageTitle("Настройки"),
    h("div", { class: "card rise" }, h("label", { class: "f", style: "margin-top:0" }, "Название группы"), f.name,
      h("label", { class: "f" }, "Часовой пояс"), f.tz),
    h("div", { class: "section rise" }, "Опрос перед парой"),
    h("div", { class: "card rise" },
      h("label", { class: "row", style: "cursor:pointer" }, h("div", { class: "grow" }, h("b", {}, "Опрашивать студентов"),
        h("div", { class: "muted small" }, "«Буду / Опоздаю / Не смогу» каждому в личку")), h("span", { class: "switch" }, f.polls_enabled, h("i"))),
      h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f" }, "Присылать опрос"), f.remind_minutes), h("div", {}, h("label", { class: "f" }, "Сводка старосте"), f.summary_minutes)),
      h("p", { class: "muted tiny", style: "margin:8px 2px 0" }, "Кто не ответил до сводки — получает «не ответил», это считается пропуском.")),
    h("div", { class: "section rise" }, "Прогулы"),
    h("div", { class: "card rise" }, h("label", { class: "f", style: "margin-top:0" }, "Предупреждать после (по одному предмету)"), f.truancy_limit),
    h("div", { class: "section rise" }, "Семестр"),
    h("div", { class: "card rise" }, h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f", style: "margin-top:0" }, "Начало"), f.semester_start),
      h("div", {}, h("label", { class: "f", style: "margin-top:0" }, "Конец"), f.semester_end)),
      h("p", { class: "muted tiny", style: "margin:8px 2px 0" }, "От начала семестра считаются чётные и нечётные недели. После конца пары не показываются.")),
    h("button", { class: "btn block rise", style: "margin-top:4px", onclick: act(async () => {
      await api("/group", { method: "PATCH", body: { name: f.name.value, tz: f.tz.value, semester_start: f.semester_start.value || null, semester_end: f.semester_end.value || null,
        polls_enabled: f.polls_enabled.checked, remind_minutes: +f.remind_minutes.value, summary_minutes: +f.summary_minutes.value, truancy_limit: +f.truancy_limit.value } });
      notify(); toast("Сохранено", "check"); S.me = await api("/me"); go(S.tab);
    }) }, "Сохранить"));
}


const GRADE_LABEL = g => g == null ? "" : g === "0" ? "н/а" : g === "незач" ? "н/з" : g === "зач" ? "зач" : g === "осв" ? "осв" : g;
const gradeCls = g => g === "5" ? "g5" : g === "4" ? "g4" : g === "3" ? "g3" : (g === "2" || g === "0" || g === "незач") ? "g2" : g ? "gz" : "g-";
const avgColor = a => a == null ? "var(--hint)" : a >= 4.5 ? "var(--P)" : a >= 3.5 ? "var(--E)" : a >= 3 ? "var(--L)" : "var(--A)";
const fmtAvg = a => a == null ? "—" : a.toFixed(2).replace(".", ",");
const gchip = (g, extra = "") => h("span", { class: "gchip " + gradeCls(g) + " " + extra }, GRADE_LABEL(g) || "·");

async function renderGrades() {
  const q = S.gradesMonth ? "?month=" + S.gradesMonth : "";
  const data = await api("/grades" + q);
  if (data.month) S.gradesMonth = data.month;
  const months = data.months || [];
  const staff = can("journal", "grades");
  const chips = months.length ? h("div", { class: "chips rise" }, months.slice().reverse().map(m => h("button", {
    class: "chip " + (m.month === data.month ? "on" : ""), onclick: () => { S.gradesMonth = m.month; S.anim = "fade"; selTick(); render(); } }, m.title)),
    can("grades") ? h("button", { class: "chip", onclick: newGradeMonth }, icon("plus", "sm")) : null) : null;

  if (!months.length || data.empty) {
    return mount(S.anim, pageTitle(staff ? "Успеваемость" : "Оценки"), chips,
      empty("book", "Оценок пока нет", can("grades") ? "Загрузите ведомость «Сведения успеваемости» из Excel — бот разберёт оценки, пропуски и примечания. Или заполните вручную." : "Как только куратор загрузит ведомость за месяц, оценки появятся здесь",
        can("grades") ? h("div", { class: "btns" }, h("button", { class: "btn", onclick: uploadGrades }, icon("upload", "sm"), "Загрузить Excel"),
          h("button", { class: "btn ghost", onclick: newGradeMonth }, icon("edit", "sm"), "Вручную")) : null));
  }
  if (!staff) return renderMyGrades(data, chips);

  const s = data.summary;
  const kpi = (val, label, color, suffix = "", dec = null) => h("div", { class: "kpi" }, val == null ? h("b", {}, "—") : countUp(h("b", { style: color ? `color:${color}` : "" }), val, suffix, 900, dec), h("span", {}, label));
  const view = S.gradesView || "students";
  const seg = h("div", { class: "seg rise" }, [["students", "Студенты"], ["subjects", "Предметы"], ["table", "Таблица"]].map(([k, t]) =>
    h("button", { class: view === k ? "on" : "", onclick: () => { S.gradesView = k; S.anim = "fade"; selTick(); render(); } }, t)));
  const body = view === "subjects" ? gradesBySubject(data) : view === "table" ? gradesTable(data) : gradesByStudent(data);
  mount(S.anim, pageTitle("Успеваемость"), chips,
    h("div", { class: "kpis rise", style: "grid-template-columns:1fr 1fr" },
      kpi(s.avg, "средний балл группы", avgColor(s.avg), "", 2), kpi(s.quality, "качество знаний", null, "%"),
      kpi(s.progress, "успеваемость", null, "%"), kpi(s.fails, "двоек и неаттестаций", s.fails ? "var(--A)" : "var(--P)")),
    h("div", { class: "card rise row", style: "padding:12px 14px" }, icon("clock", "sm"),
      h("div", { class: "grow small" }, `Пропущено ${s.missed_total} ч · без уважительной ${s.missed_bad} ч`),
      s.excellent ? h("span", { class: "badge P" }, `отличников: ${s.excellent}`) : null),
    can("grades", "export") ? h("div", { class: "btns rise", style: "margin:0 0 12px" },
      can("grades") ? h("button", { class: "btn ghost sm", onclick: uploadGrades }, icon("upload", "sm"), "Загрузить") : null,
      h("button", { class: "btn ghost sm", onclick: act(async () => {
        if (IN_TG) { await api("/grades/export", { body: { month: data.month } }); toast("Ведомость отправлена в чат", "check"); }
        else await downloadFile(`/grades/export?month=${data.month}`, "vedomost.xlsx");
        notify(); }) }, icon("download", "sm"), "Ведомость"),
      can("grades") ? h("button", { class: "btn ghost sm", style: "flex:0 0 46px", onclick: () => gradesMenu(data) }, icon("more", "sm")) : null) : null,
    seg, body);
}

function gradesByStudent(data) {
  const sorted = data.rows.slice().sort((a, b) => (S.gradesSort === "name" ? a.full_name.localeCompare(b.full_name) : (a.avg ?? 9) - (b.avg ?? 9)));
  return [h("div", { class: "row rise", style: "margin:2px 6px 8px" }, h("span", { class: "muted small grow" }, `${data.rows.length} ${plural(data.rows.length, "студент", "студента", "студентов")}`),
      h("a", { class: "small", style: "color:var(--link);cursor:pointer", onclick: () => { S.gradesSort = S.gradesSort === "name" ? "avg" : "name"; S.anim = "fade"; render(); } },
        S.gradesSort === "name" ? "по алфавиту ↕" : "сначала слабые ↕")),
    h("div", { class: "list rise" }, sorted.map(r => h("div", { class: "item tap", onclick: () => openGradeCard(data, r) },
      ava(r.full_name),
      h("div", { class: "grow" },
        h("div", { class: "row", style: "gap:6px" }, h("b", { class: "ellipsis", style: "font-weight:600" }, r.full_name), r.note ? h("span", { class: "badge", title: "Примечание" }, r.note) : null),
        h("div", { class: "mini-grades" }, r.grades.map(g => h("i", { class: gradeCls(g) }))),
        h("div", { class: "muted tiny" }, [r.record_no, r.missed_total != null ? `пропущено ${r.missed_total} ч` + (r.missed_bad ? ` (${r.missed_bad} без уваж.)` : "") : null, r.fails ? `⚠️ ${r.fails} ${plural(r.fails, "долг", "долга", "долгов")}` : null].filter(Boolean).join(" · "))),
      h("span", { class: "avg-pill", style: `background:${avgColor(r.avg)}` }, fmtAvg(r.avg)))))];
}

function gradesBySubject(data) {
  return h("div", { class: "list rise" }, data.subjects.map((s, j) => h("div", { class: "item tap", onclick: () => openSubjectGrades(data, j) },
    h("div", { class: "grow" }, h("div", { class: "ellipsis", style: "font-weight:600" }, s.name), h("div", { class: "muted tiny" }, s.teacher || ""),
      h("div", { class: "row", style: "gap:8px;margin-top:6px" },
        h("div", { class: "progress grow" }, h("i", { style: `width:${s.quality ?? 0}%;background:${avgColor(s.avg)}` })),
        h("span", { class: "tiny muted", style: "width:92px;text-align:right" }, s.quality != null ? `качество ${Math.round(s.quality)}%` : "нет оценок"))),
    s.fails ? h("span", { class: "badge A" }, s.fails) : null,
    h("span", { class: "avg-pill", style: `background:${avgColor(s.avg)}` }, fmtAvg(s.avg)))));
}

function gradesTable(data) {
  const short = n => n.length > 12 ? n.slice(0, 11) + "…" : n;
  return [h("div", { class: "jgrid rise" }, h("table", {},
      h("tr", {}, h("th", { class: "name muted" }, "Студент"), data.subjects.map(s => h("th", { title: s.name, style: "min-width:44px" }, h("div", { class: "vtext" }, short(s.name)))), h("th", {}, "Ср.")),
      data.rows.map(r => h("tr", {}, h("td", { class: "name", onclick: () => openGradeCard(data, r), style: "cursor:pointer" }, r.full_name),
        r.grades.map((g, j) => h("td", {}, h("button", { class: "gcell " + gradeCls(g), onclick: e => can("grades") ? pickGrade(data, r, j, e.currentTarget) : null }, GRADE_LABEL(g)))),
        h("td", {}, h("b", { style: `color:${avgColor(r.avg)};font-size:13px` }, fmtAvg(r.avg))))))),
    h("p", { class: "muted tiny rise", style: "margin:0 6px 12px" }, can("grades") ? "Нажмите на оценку, чтобы исправить. «н/а» — неаттестация (0), учитывается в среднем, как в ведомости." : "«н/а» — неаттестация по дисциплине.")];
}

function pickGrade(data, r, j, cell, onDone) {
  const subj = data.subjects[j];
  const set = v => safe(async () => {
    const res = await api("/grades/cell", { method: "PATCH", body: { month: data.month, student_id: r.student_id, index: j, value: v } });
    r.grades[j] = v; r.avg = res.avg; selTick(); closeSheet();
    if (cell) { cell.className = "gcell changed " + gradeCls(v); cell.textContent = GRADE_LABEL(v); }
    onDone ? onDone() : (S.anim = null, render());
  });
  openSheet(h("h3", {}, r.full_name), h("div", { class: "muted small" }, subj.name + (subj.teacher ? " · " + subj.teacher : "")),
    h("div", { class: "grade-pick" }, ["5", "4", "3", "2", "0", "зач"].map(v => h("button", { class: gradeCls(v) + (r.grades[j] === v ? " on" : ""), onclick: () => set(v) }, GRADE_LABEL(v)))),
    r.grades[j] != null ? h("div", { class: "btns" }, h("button", { class: "btn plain", onclick: () => set(null) }, "Убрать оценку")) : null);
}

async function openGradeCard(data, r) {
  const editable = can("grades");
  const list = h("div", { class: "list" });
  const avgEl = h("b", { class: "num", style: `color:${avgColor(r.avg)}` }, fmtAvg(r.avg));
  const draw = () => {
    list.replaceChildren(...data.subjects.map((s, j) => h("div", { class: "item" + (editable ? " tap" : ""), onclick: () => editable && pickGrade(data, r, j, null, () => { draw(); avgEl.textContent = fmtAvg(r.avg); avgEl.style.color = avgColor(r.avg); }) },
      h("div", { class: "grow" }, h("div", { style: "font-weight:600;font-size:14px" }, s.name), s.teacher ? h("div", { class: "muted tiny" }, s.teacher) : null),
      s.avg != null ? h("span", { class: "tiny muted", style: "margin-right:6px" }, "гр. " + fmtAvg(s.avg)) : null,
      gchip(r.grades[j], "lg"))));
  };
  draw();
  const mt = h("input", { type: "number", min: 0, value: r.missed_total ?? "", inputmode: "numeric", disabled: !editable });
  const mb = h("input", { type: "number", min: 0, value: r.missed_bad ?? "", inputmode: "numeric", disabled: !editable });
  const note = h("input", { value: r.note || "", placeholder: "Например, АС", disabled: !editable });
  const hist = h("div");
  openSheet(
    h("div", { class: "row" }, ava(r.full_name), h("div", { class: "grow" }, h("h3", {}, r.full_name), h("div", { class: "muted small" }, [data.title, r.record_no && "№ " + r.record_no].filter(Boolean).join(" · "))),
      h("div", { class: "center" }, avgEl, h("div", { class: "muted tiny" }, "ср. балл"))),
    can("students", "student_info") ? h("button", { class: "btn plain sm block", style: "margin-top:10px", onclick: async () => {
      const { students } = await api("/students?archived=1"); const st = students.find(x => x.id === r.student_id); if (st) { closeSheet(); setTimeout(() => editStudent(st), 280); } } }, icon("user", "sm"), "Данные студента") : null,
    h("div", { class: "section" }, "Оценки за месяц"), list,
    h("div", { class: "section" }, "Пропущено часов"),
    h("div", { class: "grid2" }, h("div", {}, h("label", { class: "f", style: "margin-top:0" }, "Всего"), mt), h("div", {}, h("label", { class: "f", style: "margin-top:0" }, "Без уважительной"), mb)),
    h("label", { class: "f" }, "Примечание"), note,
    editable ? h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
      await api("/grades/cell", { method: "PATCH", body: { month: data.month, student_id: r.student_id, missed_total: mt.value, missed_bad: mb.value, note: note.value } });
      notify(); toast("Сохранено", "check"); closeSheet(); render(); }) }, "Сохранить")) : null,
    hist);
  try {
    const { history } = await api("/grades/student/" + r.student_id);
    if (history.length > 1) hist.replaceChildren(h("div", { class: "section" }, "Динамика среднего балла"),
      h("div", { class: "card" }, sparklineAvg(history.map(x => x.avg ?? 0)), h("div", { class: "row tiny muted", style: "justify-content:space-between" }, history.map(x => h("span", {}, x.title.split(" ")[0].slice(0, 3))))));
  } catch (_) {}
}

function sparklineAvg(values) {
  const svg = sparkline(values.map(v => 50 + v * 10));
  return svg;
}

function openSubjectGrades(data, j) {
  const s = data.subjects[j];
  const rows = data.rows.slice().sort((a, b) => a.full_name.localeCompare(b.full_name));
  const counts = { "5": 0, "4": 0, "3": 0, "2": 0, "0": 0 };
  rows.forEach(r => { if (r.grades[j] in counts) counts[r.grades[j]]++; });
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  const list = h("div", { class: "list" });
  const draw = () => list.replaceChildren(...rows.map(r => h("div", { class: "item" + (can("grades") ? " tap" : ""), onclick: () => can("grades") && pickGrade(data, r, j, null, draw) },
    h("div", { class: "grow ellipsis" }, r.full_name), gchip(r.grades[j], "lg"))));
  draw();
  openSheet(h("h3", {}, s.name), h("div", { class: "muted small" }, [s.teacher, data.title].filter(Boolean).join(" · ")),
    h("div", { class: "dist" }, Object.entries(counts).map(([g, n]) => h("i", { class: gradeCls(g), style: `flex:${n || 0.0001}`, title: `${GRADE_LABEL(g)}: ${n}` }, n ? GRADE_LABEL(g) + " · " + n : ""))),
    h("div", { class: "kpis", style: "margin-top:12px" },
      h("div", { class: "kpi" }, h("b", { style: `color:${avgColor(s.avg)}` }, fmtAvg(s.avg)), h("span", {}, "средний балл")),
      h("div", { class: "kpi" }, h("b", {}, s.quality != null ? Math.round(s.quality) + "%" : "—"), h("span", {}, "качество знаний"))),
    list,
    can("grades") ? h("div", { class: "btns" }, h("button", { class: "btn danger sm", onclick: () => confirmDo(`Убрать предмет «${s.name}» из ведомости за ${data.title.toLowerCase()}? Оценки по нему удалятся.`, () => safe(async () => {
      await api("/grades/subjects", { body: { month: data.month, remove: j } }); closeSheet(); render(); })) }, icon("trash", "sm"), "Убрать предмет")) : null);
}

function renderMyGrades(data, chips) {
  const me = data.me;
  if (!me) return mount(S.anim, pageTitle("Оценки"), chips, empty("book", "Вас нет в ведомости", `За ${data.title.toLowerCase()} оценок не найдено — обратитесь к старосте`));
  const big = h("b");
  const nums = me.grades.filter(g => ["5", "4", "3", "2", "0"].includes(g));
  const cnt = k => nums.filter(g => g === k).length;
  const r = ring([["var(--P)", cnt("5")], ["var(--E)", cnt("4")], ["var(--L)", cnt("3")], ["var(--A)", cnt("2") + cnt("0")]], nums.length || 1, "", "средний балл");
  r.querySelector(".lbl b").replaceWith(big);
  me.avg != null ? countUp(big, me.avg, "", 900, 2) : (big.textContent = "—");
  big.style.fontSize = "24px";
  const hist = h("div");
  mount(S.anim, pageTitle("Оценки"), chips,
    h("div", { class: "card live rise" },
      h("div", { class: "phase" }, h("span", { class: "dot", style: `background:${avgColor(me.avg)}` }), data.title),
      h("div", { class: "ring-wrap" }, r, h("div", { class: "legend" },
        [["5", "Отлично", "var(--P)"], ["4", "Хорошо", "var(--E)"], ["3", "Удовл.", "var(--L)"], ["2", "Неуд. / н/а", "var(--A)"]].map(([k, t, c]) =>
          h("div", {}, h("span", { class: "dot", style: `background:${c}` }), t, h("b", {}, k === "2" ? cnt("2") + cnt("0") : cnt(k)))))),
      h("div", { class: "row small", style: "margin-top:12px;gap:8px;flex-wrap:wrap" },
        data.group_avg != null ? h("span", { class: "badge kind" }, "по группе " + fmtAvg(data.group_avg)) : null,
        data.rank ? h("span", { class: "badge" }, `${data.rank.place} место из ${data.rank.of}`) : null,
        me.note ? h("span", { class: "badge P" }, me.note) : null)),
    me.missed_total != null ? h("div", { class: "card rise row" }, h("div", { class: "tile c3", style: "width:38px;height:38px;border-radius:12px;display:grid;place-items:center" }, icon("clock", "sm")),
      h("div", { class: "grow" }, h("b", {}, `Пропущено ${me.missed_total} ${plural(me.missed_total, "час", "часа", "часов")}`),
        h("div", { class: "muted small" }, me.missed_bad ? `из них без уважительной причины — ${me.missed_bad}` : "все по уважительной причине или без пропусков"))) : null,
    me.fails ? h("div", { class: "card rise note", style: "background:color-mix(in srgb,var(--A) 10%,var(--card))" }, `⚠️ ${me.fails} ${plural(me.fails, "долг", "долга", "долгов")} — двойки или неаттестации. Их нужно закрыть.`) : null,
    h("div", { class: "section rise" }, "По предметам"),
    h("div", { class: "list rise" }, data.subjects.map((s, j) => me.grades[j] == null ? null : h("div", { class: "item" },
      h("div", { class: "grow" }, h("div", { style: "font-weight:600;font-size:14px" }, s.name), h("div", { class: "muted tiny" }, [s.teacher, s.avg != null && "по группе " + fmtAvg(s.avg)].filter(Boolean).join(" · "))),
      gchip(me.grades[j], "lg")))),
    hist);
  api("/grades/student/" + me.student_id).then(({ history }) => {
    if (history.length > 1) hist.replaceChildren(h("div", { class: "section" }, "Динамика"), h("div", { class: "card" }, sparklineAvg(history.map(x => x.avg ?? 0)),
      h("div", { class: "row tiny muted", style: "justify-content:space-between" }, history.map(x => h("span", {}, x.title.split(" ")[0].slice(0, 3) + " " + fmtAvg(x.avg))))));
  }).catch(() => {});
}

function uploadGrades() {
  openSheet(h("h3", {}, "Загрузить ведомость"),
    h("p", { class: "muted small" }, "Выберите Excel-файл «Сведения успеваемости студентов группы … за <месяц>» — как тот, что сдаёте в учебную часть. Разберём месяц, предметы с преподавателями, оценки, пропущенные часы и примечания. Студентов сопоставим по фамилии и инициалам или по № студенческого; кого не найдём — добавим в список."),
    h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
      const file = await pickFile(".xlsx,.xlsm"); if (!file) return;
      const r = await apiUpload("/grades/upload", {}, file); notify(); closeSheet();
      toast("Ведомость загружена" + (r.lines?.length ? ": " + r.lines.join(" · ") : ""), "check"); render();
    }) }, icon("upload", "sm"), "Выбрать файл"),
      IN_TG ? h("button", { class: "btn ghost sm", onclick: act(async () => {
        await api("/grades/upload", { body: {} }); closeSheet(); toast("Пришлите файл в чат с ботом", "upload");
        setTimeout(goToBotChat, 1200); }) }, icon("share", "sm"), "Через бота") : null));
}

function newGradeMonth() {
  const d = parseIso(S.me.today);
  const inp = h("input", { type: "month", value: iso(d).slice(0, 7) });
  openSheet(h("h3", {}, "Новая ведомость"), h("p", { class: "muted small" }, "Предметы возьмём из прошлой ведомости (или из расписания), студентов — из списка группы. Оценки поставите сами."),
    h("label", { class: "f" }, "Месяц"), inp,
    h("div", { class: "btns" }, h("button", { class: "btn", onclick: act(async () => {
      const r = await api("/grades/month", { body: { month: inp.value } }); S.gradesMonth = r.month; S.gradesView = "table"; notify(); closeSheet(); render(); }) }, "Создать")));
}

function gradesMenu(data) {
  const name = h("input", { placeholder: "Название предмета" }), teacher = h("input", { placeholder: "Преподаватель (необязательно)" });
  openSheet(h("h3", {}, data.title),
    h("div", { class: "list", style: "margin-top:12px" },
      h("div", { class: "item tap", onclick: act(async () => { const r = await api("/grades/fill-missed", { body: { month: data.month } }); notify(); closeSheet(); toast(`Пропуски пересчитаны из журнала (${r.updated})`, "check"); render(); }) },
        icon("journal", "sm"), h("div", { class: "grow" }, h("b", {}, "Пропуски из журнала"), h("div", { class: "muted tiny" }, "Пара = 2 часа: «не был» и «не ответил» — без уважительной, «уважит.» — в общем числе"))),
      h("div", { class: "item tap", onclick: () => confirmDo(`Удалить ведомость за ${data.title.toLowerCase()}?`, () => safe(async () => {
        await api("/grades/" + data.month, { method: "DELETE" }); S.gradesMonth = null; closeSheet(); render(); })) },
        icon("trash", "sm"), h("div", { class: "grow" }, h("b", { style: "color:var(--A)" }, "Удалить ведомость за месяц")))),
    h("div", { class: "section" }, "Добавить предмет"), name, h("div", { style: "height:8px" }), teacher,
    h("div", { class: "btns" }, h("button", { class: "btn ghost", onclick: act(async () => {
      await api("/grades/subjects", { body: { month: data.month, add: { name: name.value, teacher: teacher.value } } }); notify(); closeSheet(); render(); }) }, icon("plus", "sm"), "Добавить предмет")));
}


function openGuide() {
  const slides = [
    ["users", "c1", "Пригласите группу", "Отправьте в беседу готовое сообщение со ссылкой. Студент нажмёт — останется вписать ФИО."],
    ["calendar", "c2", "Добавьте расписание", "Вручную или из Excel-шаблона. Укажите даты семестра — заработают чётные недели и каникулы."],
    ["bell", "c3", "Опрос перед парой — сам", "За 15 минут бот спрашивает каждого: «Буду / Опоздаю / Не смогу». Промолчал — пропуск, поэтому отвечают все. Уважительную причину можно подтвердить фото справки."],
    ["key", "c4", "Код на доску", "Если сомневаетесь, что все «будущие» пришли — покажите 4 цифры. Отметиться сможет только тот, кто в аудитории."],
    ["chart", "c5", "Итоги без таблиц", "Живая сводка на главной, журнал по дням, прогулы по предметам и Excel для деканата в пару нажатий."],
  ];
  let i = 0;
  const box = h("div");
  const draw = () => {
    const [ic, c, t, d] = slides[i];
    box.replaceChildren(h("div", { class: "center view-slide-l", style: "padding:10px 6px 0" },
      h("div", { class: "tile " + c + " pop", style: "width:76px;height:76px;border-radius:24px;display:grid;place-items:center;margin:6px auto 16px" }, icon(ic, "lg")),
      h("h3", { style: "font-size:21px" }, t), h("p", { class: "muted", style: "min-height:66px" }, d),
      h("div", { style: "display:flex;gap:6px;justify-content:center;margin:6px 0 4px" }, slides.map((_, k) => h("span", { style: `height:6px;border-radius:9px;transition:all .3s;background:${k === i ? "var(--accent)" : "var(--sep)"};width:${k === i ? 22 : 6}px` })))),
      h("div", { class: "btns" }, h("button", { class: "btn", onclick: () => { selTick(); if (++i >= slides.length) closeSheet(); else draw(); } }, i === slides.length - 1 ? "Понятно" : "Дальше")));
  };
  draw();
  openSheet(box);
}




const fmtB = n => { if (n == null) return "—"; const u = ["Б", "КБ", "МБ", "ГБ", "ТБ"]; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return (i < 2 ? Math.round(n) : n.toFixed(1).replace(".", ",")) + " " + u[i]; };
const fmtDur = s => { if (s == null) return "—"; const d = Math.floor(s / 86400), hh = Math.floor(s % 86400 / 3600), mm = Math.floor(s % 3600 / 60); return d ? `${d} дн ${hh} ч` : hh ? `${hh} ч ${mm} мин` : `${mm} мин`; };
const fmtAgo = t => { const s = Math.max(0, Date.now() / 1000 - t); return s < 90 ? "только что" : s < 3600 ? Math.round(s / 60) + " мин назад" : s < 86400 ? Math.round(s / 3600) + " ч назад" : Math.round(s / 86400) + " дн назад"; };
let serverTimer = null;
async function renderServer(again = false) {
  clearTimeout(serverTimer);
  let s;
  try { [s] = await Promise.all([api("/server"), S.bk && again ? null : api("/admin/backups").then(b => (S.bk = b)).catch(() => null)]); }
  catch (e) { if (!again) mount(S.anim, pageTitle("Сервер"), empty("alert", "Нет данных", e.message)); return; }
  if (S.sub !== "server") return;
  const level = p => p.level === "crit" ? "var(--A)" : "var(--L)";
  const meter = (title, pct, sub, warn = 80, crit = 92) => {
    const c = pct == null ? "var(--N)" : pct >= crit ? "var(--A)" : pct >= warn ? "var(--L)" : "var(--P)";
    return h("div", { class: "card srv-meter" },
      h("div", { class: "row", style: "align-items:baseline" }, h("div", { class: "muted small grow" }, title), h("b", { class: "num", style: "font-size:20px;color:" + c }, pct == null ? "—" : Math.round(pct) + "%")),
      h("div", { class: "progress", style: "margin:8px 0 6px" }, h("i", { style: `width:${Math.min(100, pct || 0)}%;background:${c}` })),
      h("div", { class: "muted tiny" }, sub));
  };
  const row = (k, v, dot) => h("div", { class: "item" }, dot ? h("span", { class: "dot", style: "background:" + dot }) : null, h("div", { class: "grow", style: "min-width:0" }, k), h("div", { class: "muted small", style: "text-align:right;max-width:60%;word-break:break-word" }, v));
  const ok = v => v === true ? "var(--P)" : v === false ? "var(--A)" : "var(--N)";
  const svcName = { active: "работает", inactive: "остановлена", failed: "сбой", activating: "запускается" };
  const mem = s.mem || {}, cpu = s.cpu, d = s.db, b = s.backups;
  const status = s.problems.length
    ? h("div", { class: "card rise srv-status bad" }, s.problems.map(p => h("div", { class: "row", style: "gap:10px;padding:3px 0" }, h("span", { class: "dot", style: "background:" + level(p) }), h("b", { style: "font-weight:600" }, p.text))))
    : h("div", { class: "card rise srv-status good row" }, h("span", { class: "srv-pulse" }), h("div", { class: "grow" }, h("b", {}, "Всё работает"), h("div", { class: "muted tiny" }, s.host.name + " · обновлено " + new Date(s.now * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit", second: "2-digit" }))));
  const parts = [pageTitle("Сервер", h("button", { class: "btn plain sm", onclick: () => { selTick(); S.anim = null; renderServer(); } }, icon("refresh", "sm"))),
    status,
    h("div", { class: "grid2 rise", style: "margin-bottom:10px" },
      meter("Процессор", cpu.pct, `${cpu.count} ${cpu.count === 1 ? "ядро" : cpu.count < 5 ? "ядра" : "ядер"}` + (cpu.load ? " · нагрузка " + cpu.load.map(x => String(x).replace(".", ",")).join(" / ") : ""), 75, 90),
      meter("Память", mem.pct, mem.total ? `${fmtB(mem.used)} из ${fmtB(mem.total)}` : "нет данных"),
      meter("Диск", s.disk.pct, `свободно ${fmtB(s.disk.free)} из ${fmtB(s.disk.total)}`, 85, 95),
      meter("Подкачка", mem.swap_total ? mem.swap_pct : null, mem.swap_total ? `${fmtB(mem.swap_used)} из ${fmtB(mem.swap_total)}` : "не включена", 50, 85)),
    h("div", { class: "section rise" }, "Связь"),
    h("div", { class: "list rise" },
      row("Mini App", s.site.ok == null ? "адрес не задан" : s.site.ok ? `открывается · ${s.site.ms} мс` : (s.site.status ? "ошибка " + s.site.status : (s.site.error || "не отвечает").slice(0, 80)), ok(s.site.ok)),
      row("Telegram", s.telegram.ok == null ? "не подключён" : s.telegram.ok ? `на связи · ${s.telegram.ms} мс` : "нет связи", s.telegram.ok),
      s.site.url ? row("Адрес", s.site.url.replace(/^https?:\/\//, "")) : null),
    s.services.length ? h("div", { class: "section rise" }, "Службы") : null,
    s.services.length ? h("div", { class: "list rise" }, s.services.map(x => row(x.title, (svcName[x.state] || x.state) + (x.sub && x.sub !== "running" && x.state === "active" ? " · " + (x.sub === "waiting" ? "ждёт" : x.sub) : ""),
      x.state === "active" ? "var(--P)" : x.state === "failed" ? "var(--A)" : "var(--N)"))) : null,
    h("div", { class: "section rise" }, "Бот и база"),
    h("div", { class: "list rise" },
      row("Сервер работает", fmtDur(s.host.uptime)),
      row("Бот работает", `${fmtDur(s.proc.uptime)} · ${fmtB(s.proc.rss)}`),
      row("База данных", fmtB(d.size)),
      row("Группы · участники · студенты", `${d.groups} · ${d.members} · ${d.students}`),
      row("Отметок в журнале", String(d.marks)),
      row("Входов в приложение", `${d.app_sessions} · за сутки ${d.app_active_day}`),
      row("Резервные копии", b.count ? `${b.count} шт · последняя ${fmtAgo(b.last_at)}` : "ещё не было", b.count ? (s.now - b.last_at > 36 * 3600 ? "var(--L)" : "var(--P)") : "var(--N)"),
      row("Система", `${s.host.os} · Python ${s.host.python}`)),
    usageBlock(s.usage), backupBlock(S.bk),
    h("div", { class: "section rise" }, s.errors.length ? `Последние ошибки · ${s.errors_hour} за час` : "Ошибки"),
    s.errors.length
      ? h("div", { class: "list rise" }, s.errors.map(e => h("div", { class: "item", style: "align-items:flex-start" }, h("span", { class: "dot", style: "background:var(--A);margin-top:7px" }),
          h("div", { class: "grow", style: "min-width:0" }, h("div", { class: "small srv-err" }, e.text), h("div", { class: "muted tiny" }, fmtAgo(e.at) + " · " + e.where)))))
      : h("div", { class: "card rise muted small center" }, "С момента запуска бота ошибок не было 👌"),
    h("p", { class: "muted tiny center rise", style: "margin-top:14px" }, "Обновляется каждые 5 секунд. При проблемах бот сам напишет вам в Telegram. Кратко — команда /server")];
  if (again) {
    const y = scrollY;
    $app.classList.add("srv-quiet");
    mount(null, parts);
    scrollTo(0, y);
  } else {
    mount(S.anim, parts);
    $app.classList.remove("srv-quiet");
  }
  serverTimer = setTimeout(() => { if (S.sub === "server" && !document.hidden) renderServer(true); else if (S.sub === "server") serverTimer = setTimeout(() => renderServer(true), 5000); }, 5000);
}



function lockSwitchRow() {
  const sw = h("input", { type: "checkbox", checked: !S.me.lock });
  const title = h("div", { style: "font-weight:600" }), sub = h("div", { class: "muted tiny" });
  const paint = () => {
    title.textContent = S.me.lock ? "Доступ закрыт" : "Доступ к приложению";
    sub.textContent = S.me.lock ? "Работает только у вас — опросы на паузе" : "Открыт для всех пользователей";
    row.classList.toggle("lock-on", !!S.me.lock);
  };
  const row = h("label", { class: "item", style: "cursor:pointer" },
    h("div", { class: "tile c4", style: "width:34px;height:34px;border-radius:11px;display:grid;place-items:center" }, icon("key", "sm")),
    h("div", { class: "grow" }, title, sub), h("span", { class: "switch" }, sw, h("i")));
  const apply = async open => {
    sw.disabled = true;
    try {
      await api("/lock", { body: { on: !open, text: S.me.lock?.text || "", notify: false } });
      S.me.lock = open ? null : { text: S.me.lock?.text || "" };
      notify(open ? "success" : "warning");
      toast(open ? "Доступ открыт для всех" : "Доступ закрыт — приложение работает только у вас", open ? "check" : "key");
      lockBadge();
    } catch (e) { sw.checked = !sw.checked; toast(e.message, "alert"); }
    finally { sw.disabled = false; paint(); }
  };
  sw.onchange = () => {
    if (sw.checked) return apply(true);
    sw.checked = true;
    confirmDo("Закрыть доступ всем пользователям, кроме вас? Опросы и сводки встанут на паузу.", () => { sw.checked = false; apply(false); });
  };
  paint();
  return row;
}



const canSeeOnline = () => ["head", "deputy", "curator"].includes(S.me.member?.role) || S.me.super;
const hm = ts => new Date(ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
function seenText(p, now) {
  if (p.online) return "в сети";
  if (!p.last_seen) return "ещё не заходил(а)";
  const d = new Date(p.last_seen * 1000), today = new Date(now * 1000);
  const days = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 864e5);
  const ago = now - p.last_seen;
  if (ago < 3600) return `был(а) ${Math.max(1, Math.round(ago / 60))} мин назад`;
  if (days === 0) return "был(а) сегодня в " + hm(p.last_seen);
  if (days === 1) return "был(а) вчера в " + hm(p.last_seen);
  return `был(а) ${d.toLocaleDateString("ru", { day: "numeric", month: "short" })} в ${hm(p.last_seen)}`;
}
const VIA = { app: "приложение", tg: "Mini App", bot: "чат с ботом" };
let onlineTimer = null;
async function renderOnline(again = false) {
  clearTimeout(onlineTimer);
  if (!canSeeOnline()) return mount(S.anim, pageTitle("Кто в сети"), empty("users", "Недоступно", "Раздел для старосты и куратора"));
  const r = await api("/online");
  if (S.sub !== "online") return;
  const on = r.people.filter(p => p.online), today = r.people.filter(p => !p.online && p.last_seen && new Date(p.last_seen * 1000).toDateString() === new Date(r.now * 1000).toDateString());
  const earlier = r.people.filter(p => !p.online && p.last_seen && !today.includes(p)), never = r.people.filter(p => !p.last_seen);
  const row = p => h("div", { class: "item tap", onclick: () => onlineDetails(p, r.now) },
    h("div", { class: "ava-wrap" }, ava(p.name || "?"), p.online ? h("span", { class: "online-dot" }) : null),
    h("div", { class: "grow", style: "min-width:0" }, h("div", { class: "ellipsis", style: "font-weight:600" }, p.name),
      h("div", { class: "muted tiny" + (p.online ? " online-text" : "") }, seenText(p, r.now), p.via && p.last_seen ? " · " + (VIA[p.via] || p.via) : "")),
    p.role !== "student" ? h("span", { class: "badge kind" }, p.super ? "Гл. куратор" : p.role_name) : null);
  const block = (title, list) => list.length ? [h("div", { class: "section" }, title, h("span", {}, list.length)), h("div", { class: "list" }, list.map(row))] : null;
  const parts = [pageTitle("Кто в сети"),
    h("div", { class: "card row" + (again ? "" : " rise") },
      h("div", { class: "online-big" }, h("span", { class: "online-dot big" }), h("b", { class: "num" }, on.length)),
      h("div", { class: "grow" }, h("b", {}, on.length ? `${on.length} ${plural(on.length, "человек", "человека", "человек")} сейчас в сети` : "Сейчас никого нет в сети"),
        h("div", { class: "muted small" }, `Сегодня заходили: ${on.length + today.length} из ${r.people.length}`))),
    block("Сейчас в сети", on), block("Сегодня", today), block("Раньше", earlier), block("Ни разу не заходили", never),
    h("p", { class: "muted tiny center", style: "margin-top:14px" }, "«В сети» — открыт бот или приложение в последние 2 минуты. Обновляется само. История хранится 30 дней.")];
  if (again) { const y = scrollY; mount(null, parts); scrollTo(0, y); } else mount(S.anim, parts);
  onlineTimer = setTimeout(() => { if (S.sub === "online" && !document.hidden) renderOnline(true); else if (S.sub === "online") onlineTimer = setTimeout(() => renderOnline(true), 15000); }, 15000);
}
function onlineDetails(p, now) {
  const dayName = ds => { const d = new Date(ds + "T12:00:00"), t = new Date(now * 1000); const diff = Math.round((new Date(t.toDateString()) - new Date(d.toDateString())) / 864e5);
    return diff === 0 ? "Сегодня" : diff === 1 ? "Вчера" : d.toLocaleDateString("ru", { weekday: "long", day: "numeric", month: "long" }); };
  openSheet(h("div", { class: "row", style: "gap:12px" }, h("div", { class: "ava-wrap" }, ava(p.name || "?"), p.online ? h("span", { class: "online-dot" }) : null),
      h("div", {}, h("h3", { style: "margin:0" }, p.name), h("div", { class: "muted small" + (p.online ? " online-text" : "") }, seenText(p, now), p.username ? " · @" + p.username : ""))),
    h("div", { class: "section", style: "margin-top:16px" }, "Активность за неделю"),
    p.days.length ? h("div", { class: "list" }, p.days.map(d => h("div", { class: "item" }, h("div", { class: "grow", style: "text-transform:capitalize" }, dayName(d.day)),
      h("b", { class: "num" }, d.first === d.last ? hm(d.first) : `${hm(d.first)} – ${hm(d.last)}`))))
      : h("div", { class: "card muted small center" }, "За последние 7 дней не заходил(а)"),
    h("p", { class: "muted tiny", style: "margin:10px 4px 0" }, "Показано время первого и последнего действия за день."));
}



const DOCS = { consent: "Согласие на обработку данных", privacy: "Политика конфиденциальности", terms: "Пользовательское соглашение" };
async function openDoc(name) {
  const body = h("div", { class: "doc-body" }, h("div", { class: "muted small center", style: "padding:30px 0" }, "Загрузка…"));
  const tabs = h("div", { class: "seg", style: "margin:4px 0 12px" });
  const revoke = h("div", { class: "btns", style: "margin-top:6px" }, h("button", { class: "btn plain sm", style: "color:var(--A)", onclick: () => revokeConsent() }, icon("trash", "sm"), "Отозвать согласие и удалить мои данные"));
  const sheet = openSheet(tabs, body, revoke);
  sheet.classList.add("doc-sheet");
  const show = async n => {
    name = n;
    tabs.replaceChildren(...Object.entries({ consent: "Согласие", privacy: "Политика", terms: "Соглашение" }).map(([k, t]) =>
      h("button", { class: k === n ? "on" : "", onclick: () => { selTick(); show(k); } }, t)));
    try {
      const html = await (await fetch("/legal/" + n, { headers: { "ngrok-skip-browser-warning": "1" } })).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const card = doc.querySelector(".card");
      body.replaceChildren(...(card ? [...card.childNodes].map(x => document.importNode(x, true)) : [h("p", {}, "Не удалось открыть документ")]));
      body.querySelectorAll("a[href^='/legal/']").forEach(a => a.addEventListener("click", e => { e.preventDefault(); show(a.getAttribute("href").split("/").pop()); }));
      body.querySelectorAll("a[href^='http'], a[href^='mailto']").forEach(a => a.addEventListener("click", e => { e.preventDefault(); openLink(a.href); }));
      sheet.scrollTop = 0;
    } catch (e) { body.replaceChildren(h("p", { class: "muted" }, "Нет связи с сервером")); }
  };
  show(name);
}
function revokeConsent() {
  openSheet(h("h3", {}, "Отозвать согласие"),
    h("p", { class: "muted small", style: "margin:6px 0 12px" }, "Будут удалены ваше членство в группе, ваша запись в журнале вместе с отметками и оценками и входы в приложение. Это нельзя отменить."),
    h("div", { class: "note", style: "font-size:14px" }, "Чтобы случайно не удалить данные, подтверждение — в чате с ботом: отправьте команду /forget и нажмите «Да, удалить мои данные»."),
    h("div", { class: "btns" }, h("button", { class: "btn danger block", onclick: () => { closeSheet(); openLink(`https://t.me/${S.me.bot}?start=forget`); } }, icon("trash", "sm"), "Открыть чат с ботом")));
}



function issueLoginCode(s, recordInput) {
  if (!(s.record_no || "").trim()) return toast(recordInput?.trim() ? "Сначала сохраните номер студенческого" : "Сначала укажите номер студенческого", "alert");
  confirmDo(`Выдать ${s.full_name} одноразовый код? Если у студента уже есть пароль, по коду он задаст новый${s.auth?.code_until ? "; прежний код перестанет работать" : ""}.`, () => safe(async () => {
    const r = await api(`/students/${s.id}/login-code`, { body: {} });
    notify();
    const until = new Date(r.expires * 1000).toLocaleString("ru", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
    const msg = `Вход в «Куратор +» без Telegram:\n1) Откройте приложение или ${location.origin}\n2) «Войти по номеру студенческого» → «Первый вход или забыли пароль?»\n3) Номер: ${r.record_no}, код: ${r.code}\nКод одноразовый, действует до ${until}.`;
    closeSheet();
    openSheet(h("div", { class: "center", style: "padding:6px 0" },
        h("div", { class: "muted small" }, s.full_name + " · № " + r.record_no),
        h("div", { class: "code pop", style: "font-size:46px;letter-spacing:10px;margin:10px 0" }, r.code),
        h("div", { class: "muted small" }, "Одноразовый · действует до " + until)),
      h("div", { class: "note", style: "font-size:14px;margin-top:12px" }, "Передайте код студенту лично. В приложении: «Войти по номеру студенческого» → «Первый вход или забыли пароль?» → номер, код и новый пароль."),
      h("div", { class: "btns" },
        h("button", { class: "btn ghost", onclick: () => navigator.clipboard?.writeText(msg).then(() => toast("Скопировано", "check")) }, icon("copy", "sm"), "Копировать с инструкцией")),
      h("p", { class: "muted tiny center" }, "Код виден только сейчас — сохранить его заново нельзя, можно только выдать новый."));
  }));
}


function changePassword() {
  const old = h("input", { type: "password", placeholder: "Текущий пароль", autocomplete: "current-password" });
  const nw = h("input", { type: "password", placeholder: "Не короче 8 символов", autocomplete: "new-password" });
  const nw2 = h("input", { type: "password", placeholder: "Ещё раз", autocomplete: "new-password" });
  openSheet(h("h3", {}, "Сменить пароль"),
    h("label", { class: "f" }, "Текущий пароль"), old, h("label", { class: "f" }, "Новый пароль"), nw, h("label", { class: "f" }, "Повторите"), nw2,
    h("div", { class: "btns" }, h("button", { class: "btn block", onclick: act(async () => {
      if (nw.value !== nw2.value) throw new Error("Пароли не совпадают");
      await api("/me/password", { body: { old: old.value, new: nw.value } }); notify(); closeSheet(); toast("Пароль изменён", "check");
    }) }, "Сохранить")),
    h("p", { class: "muted tiny center" }, "Забыли текущий пароль? Попросите у старосты или куратора одноразовый код."));
}



const PW_HINT_KEY = "kp_pw_hint_until";
function passwordHint() {
  if (!S.me.student || S.me.has_password || S.me.no_telegram || S.me.demo) return null;
  try { if (Date.now() < +(localStorage.getItem(PW_HINT_KEY) || 0)) return null; } catch (_) {}
  const card = h("div", { class: "card rise pw-hint" },
    h("div", { class: "row", style: "gap:12px;align-items:flex-start" },
      h("div", { class: "tile c5", style: "width:40px;height:40px;border-radius:12px;display:grid;place-items:center;flex:none" }, icon("key", "sm")),
      h("div", { class: "grow" },
        h("b", {}, "Установите пароль"),
        h("div", { class: "muted small", style: "margin-top:2px" }, "Сейчас вы входите через Telegram — так и останется. С паролем сможете войти и без Telegram: по номеру студенческого."),
        h("div", { class: "btns", style: "margin-top:10px" },
          h("button", { class: "btn sm", onclick: () => setPasswordSheet() }, "Установить"),
          h("button", { class: "btn plain sm", onclick: () => {
            try { localStorage.setItem(PW_HINT_KEY, String(Date.now() + 14 * 864e5)); } catch (_) {}
            card.style.transition = "opacity .25s, transform .25s"; card.style.opacity = 0; card.style.transform = "scale(.97)"; setTimeout(() => card.remove(), 260);
          } }, "Позже")))));
  return card;
}
function setPasswordSheet() {
  const rec = S.me.student?.record_no;
  if (!rec) return openSheet(h("h3", {}, "Установить пароль"),
    h("p", { class: "muted small", style: "margin:6px 0 12px" }, "Для входа без Telegram нужен номер студенческого билета, а в вашей карточке его пока нет."),
    h("div", { class: "note", style: "font-size:14px" }, "Попросите старосту или куратора внести номер: «Студенты» → ваша карточка → «№ студенческого». После этого вернитесь сюда."));
  const nw = h("input", { type: "password", placeholder: "Не короче 8 символов", autocomplete: "new-password" });
  const nw2 = h("input", { type: "password", placeholder: "Ещё раз", autocomplete: "new-password" });
  openSheet(h("h3", {}, "Установить пароль"),
    h("p", { class: "muted small", style: "margin:4px 0 8px" }, "Вход через Telegram продолжит работать. Пароль нужен, чтобы входить и без него."),
    h("div", { class: "card", style: "padding:10px 14px;margin:6px 0" }, h("div", { class: "muted tiny" }, "Логин — номер студенческого"), h("b", { style: "font-size:17px" }, rec)),
    h("label", { class: "f" }, "Пароль"), nw, h("label", { class: "f" }, "Повторите"), nw2,
    h("div", { class: "btns" }, h("button", { class: "btn block", onclick: act(async () => {
      if (nw.value !== nw2.value) throw new Error("Пароли не совпадают");
      await api("/me/password", { body: { new: nw.value } });
      S.me.has_password = true; notify(); closeSheet(); toast("Пароль установлен — теперь можно входить и по номеру студенческого", "check"); render();
    }) }, "Сохранить пароль")));
}
