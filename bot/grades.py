"""Ведомость успеваемости за месяц: разбор Excel, расчёт показателей, выгрузка.

Формат — как «Сведения успеваемости студентов группы … за <месяц>»:
столбцы «Фамилия, имя и отчество», «№ студенческого», дисциплины (название + ФИО преподавателя),
«Пропущено часов: всего / без уважительной причины», «Средний балл», «Примечание».
«0» — неаттестация по дисциплине.
"""
import io
import re
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTHS_CAP = [m.capitalize() for m in MONTHS]
TEACHER_RE = re.compile(r"\s*([А-ЯЁA-Z][а-яёa-z\-]+\s+[А-ЯЁA-Z]\.\s*[А-ЯЁA-Z]\.?)\s*$")
NUMERIC = {"5", "4", "3", "2", "1", "0"}


# ---------- разбор
def _s(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def split_subject(text: str) -> dict:
    t = _s(text)
    m = TEACHER_RE.search(t)
    if m and m.start() > 0:
        return {"name": t[:m.start()].strip(" ,–-"), "teacher": m.group(1).replace(" .", ".")}
    return {"name": t, "teacher": None}


def norm_grade(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if float(v).is_integer():
            return str(int(v))
        return str(v)
    s = _s(v).lower().replace("ё", "е")
    if not s:
        return None
    if s in ("н/а", "на", "н\\а", "неат", "не ат"):
        return "0"
    if s.startswith("зач"):
        return "зач"
    if s.startswith("незач") or s.startswith("не зач"):
        return "незач"
    if s.startswith("осв"):
        return "осв"
    return s[:6]


def _month_from(sheet) -> str | None:
    """Ищет «за <Месяц> … 2026 – 2027 учебного года» в шапке."""
    text = " ".join(_s(c.value) for row in sheet.iter_rows(min_row=1, max_row=9) for c in row if c.value is not None).lower()
    mi = next((i for i, m in enumerate(MONTHS) if m[:4] in text), None)
    years = [int(y) for y in re.findall(r"(20\d\d)", text)]
    if mi is None:
        return None
    if len(years) >= 2:
        year = years[0] if mi >= 7 else years[1]       # сентябрь–декабрь — первый год, январь–август — второй
    elif years:
        year = years[0]
    else:
        year = date.today().year
    return f"{year}-{mi + 1:02d}"


def parse_sheet(ws) -> dict | None:
    rows = list(ws.iter_rows(values_only=True))
    head_i = next((i for i, r in enumerate(rows[:30]) if any("фамилия" in _s(v).lower() for v in r if v)), None)
    if head_i is None:
        return None
    head = rows[head_i]
    col_name = next(j for j, v in enumerate(head) if v and "фамилия" in _s(v).lower())
    col_rec = next((j for j, v in enumerate(head) if v and "студенч" in _s(v).lower()), None)
    col_disc = next((j for j, v in enumerate(head) if v and "дисциплин" in _s(v).lower()), col_name + 2)
    col_miss = next((j for j, v in enumerate(head) if v and "пропущ" in _s(v).lower()), None)
    col_avg = next((j for j, v in enumerate(head) if v and "средн" in _s(v).lower()), None)
    col_note = next((j for j, v in enumerate(head) if v and "примеч" in _s(v).lower()), None)
    end = col_miss if col_miss is not None else (col_avg if col_avg is not None else len(head))
    sub_row = rows[head_i + 1] if head_i + 1 < len(rows) else ()
    subjects, cols = [], []
    for j in range(col_disc, end):
        v = sub_row[j] if j < len(sub_row) else None
        if v and _s(v):
            subjects.append(split_subject(v))
            cols.append(j)
    # одинаковые названия (подгруппы) — различаем по преподавателю
    names = [s["name"] for s in subjects]
    for s in subjects:
        if names.count(s["name"]) > 1 and s["teacher"]:
            s["name"] = f"{s['name']} ({s['teacher']})"
    # студенты: строки после шапки, где в колонке ФИО есть буквы
    students = []
    for r in rows[head_i + 2:]:
        name = _s(r[col_name] if col_name < len(r) else None)
        if not name or not re.search(r"[А-ЯЁа-яёA-Za-z]", name) or len(name) > 60:
            continue
        low = name.lower()
        if low.startswith(("итого", "пропуски", "качество", "%", "дата", "примечание", "средние")):
            break
        grades = [norm_grade(r[j] if j < len(r) else None) for j in cols]
        def num(j):
            v = r[j] if j is not None and j < len(r) else None
            return int(v) if isinstance(v, (int, float)) else None
        note = _s(r[col_note]) if col_note is not None and col_note < len(r) and r[col_note] else None
        students.append({"name": name, "record_no": _s(r[col_rec]) if col_rec is not None and col_rec < len(r) and r[col_rec] else None,
                         "grades": grades, "missed_total": num(col_miss),
                         "missed_bad": num(col_miss + 1) if col_miss is not None else None, "note": note})
    if not subjects or not students:
        return None
    return {"month": _month_from(ws), "subjects": subjects, "students": students, "sheet": ws.title}


def parse_workbook(data: bytes) -> list[dict]:
    wb = load_workbook(io.BytesIO(data), data_only=True)
    return [p for p in (parse_sheet(ws) for ws in wb.worksheets) if p]


def looks_like_grades(data: bytes) -> bool:
    try:
        return bool(parse_workbook(data))
    except Exception:  # noqa: BLE001
        return False


# ---------- сопоставление ФИО
def name_key(name: str) -> tuple[str, str]:
    """«АНТОНЮК А.С.» / «Антонюк Алексей Сергеевич» → ('антонюк', 'ас')."""
    parts = [p for p in re.split(r"[\s.]+", name.replace("ё", "е").replace("Ё", "Е")) if p]
    if not parts:
        return "", ""
    return parts[0].lower(), "".join(p[0].lower() for p in parts[1:3])


def match_students(rows: list[dict], students: list[dict]) -> dict[int, int | None]:
    """Индекс строки ведомости → id студента (или None — не найден).
    Сначала по № студенческого, затем по фамилии и инициалам без учёта регистра (см. names.py)."""
    import names
    used, out = set(), {}
    for i, r in enumerate(rows):
        rec = (r.get("record_no") or "").strip().lower()
        free = [s for s in students if s["id"] not in used]
        cand = [s for s in free if rec and (s.get("record_no") or "").strip().lower() == rec]
        if not cand:
            cand = names.candidates(r["name"], free)
            if len(cand) > 1:                      # несколько однофамильцев — предпочтём привязанного к Telegram
                linked = [s for s in cand if s.get("tg_id")]
                cand = linked if len(linked) == 1 else cand[:1]
        out[i] = cand[0]["id"] if cand else None
        if out[i]:
            used.add(out[i])
    return out


def pretty_name(raw: str) -> str:
    """«АНТОНЮК А.С.» → «Антонюк А.С.»"""
    parts = raw.split(maxsplit=1)
    if not parts:
        return raw
    sur = parts[0].capitalize() if parts[0].isupper() else parts[0]
    return (sur + (" " + parts[1] if len(parts) > 1 else "")).strip()


# ---------- показатели
def numeric(g: str | None) -> int | None:
    return int(g) if g in NUMERIC else None


def row_avg(grades: list) -> float | None:
    """Как в ведомости: среднее по всем числовым оценкам, «0» (неаттестация) тоже учитывается."""
    nums = [numeric(g) for g in grades if numeric(g) is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def subject_stats(values: list) -> dict:
    nums = [numeric(v) for v in values if numeric(v) is not None]
    n = len(nums)
    return {"avg": round(sum(nums) / n, 2) if n else None,
            "quality": round(100 * sum(1 for x in nums if x >= 4) / n, 1) if n else None,     # качество знаний
            "progress": round(100 * sum(1 for x in nums if x >= 3) / n, 1) if n else None,    # % успеваемости
            "fails": sum(1 for x in nums if x <= 2), "count": n}


def month_title(month: str) -> str:
    y, m = month.split("-")
    return f"{MONTHS_CAP[int(m) - 1]} {y}"


def academic_years(month: str) -> str:
    y, m = map(int, month.split("-"))
    first = y if m >= 9 else y - 1
    return f"{first} – {first + 1}"


# ---------- выгрузка в том же виде
THIN = Side(style="thin", color="000000")
B = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
FILL = {"5": "C6EFCE", "4": "DDEBF7", "3": "FFEB9C", "2": "FFC7CE", "0": "FFC7CE"}


def build_sheet(group: dict, month: str, subjects: list[dict], rows: list[dict], curator: str | None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = month_title(month)
    n = len(subjects)
    c_first = 4                                   # D
    c_miss = c_first + n                           # пропущено всего
    c_bad, c_avg, c_note = c_miss + 1, c_miss + 2, c_miss + 3
    last = get_column_letter(c_note)
    L = get_column_letter

    ws["A1"] = "Таблица № 1"
    ws.merge_cells(f"A4:{last}4"); ws["A4"] = "С В Е Д Е Н И Я"; ws["A4"].font = Font(bold=True, size=14); ws["A4"].alignment = CENTER
    ws.merge_cells(f"A5:{last}5"); ws["A5"] = f"успеваемости студентов группы {group['name']}"; ws["A5"].alignment = CENTER; ws["A5"].font = Font(bold=True)
    ws.merge_cells(f"A7:{last}7")
    ws["A7"] = f"за {MONTHS_CAP[int(month[5:]) - 1]} {academic_years(month)} учебного года"; ws["A7"].alignment = CENTER

    h1, h2 = 9, 10
    for col, text in ((1, "Поряд. №"), (2, "Фамилия, имя и отчество учащегося"), (3, "№ студенческого"),
                      (c_avg, "Средний балл"), (c_note, "Примечание")):
        ws.merge_cells(start_row=h1, start_column=col, end_row=h2, end_column=col)
        ws.cell(row=h1, column=col, value=text)
    if n:
        ws.merge_cells(start_row=h1, start_column=c_first, end_row=h1, end_column=c_first + n - 1)
    ws.cell(row=h1, column=c_first, value="Учебные дисциплины, модули, Ф.И.О. преподавателей")
    ws.merge_cells(start_row=h1, start_column=c_miss, end_row=h1, end_column=c_bad)
    ws.cell(row=h1, column=c_miss, value="Пропущено часов")
    ws.cell(row=h2, column=c_miss, value="В С Е Г О")
    ws.cell(row=h2, column=c_bad, value="Без уважительной причины")
    for j, s in enumerate(subjects):
        nm = s["name"]
        if s.get("teacher") and nm.endswith(f" ({s['teacher']})"):
            nm = nm[: -len(s["teacher"]) - 3]
        ws.cell(row=h2, column=c_first + j, value=nm + (f"\n{s['teacher']}" if s.get("teacher") else ""))
    for col in range(1, c_note + 1):
        ws.cell(row=11, column=col, value=col)
        for r in (h1, h2, 11):
            c = ws.cell(row=r, column=col); c.border = B; c.alignment = CENTER; c.font = Font(bold=r != 11, size=9 if r == h2 else 10)
    ws.row_dimensions[h2].height = 120
    for j in range(n):
        ws.cell(row=h2, column=c_first + j).alignment = Alignment(text_rotation=90, horizontal="center", vertical="bottom", wrap_text=True)

    r0 = 12
    for i, row in enumerate(rows):
        r = r0 + i
        vals = [i + 1, row["name"], row.get("record_no")]
        for col, v in enumerate(vals, 1):
            ws.cell(row=r, column=col, value=v)
        for j, g in enumerate(row["grades"]):
            v = numeric(g) if numeric(g) is not None else g
            c = ws.cell(row=r, column=c_first + j, value=v)
            if g in FILL:
                c.fill = PatternFill("solid", fgColor=FILL[g])
        ws.cell(row=r, column=c_miss, value=row.get("missed_total"))
        ws.cell(row=r, column=c_bad, value=row.get("missed_bad"))
        rng = f"{L(c_first)}{r}:{L(c_first + n - 1)}{r}"
        ws.cell(row=r, column=c_avg, value=f'=IF(COUNT({rng})=0,"",ROUND(AVERAGE({rng}),2))' if n else None)
        ws.cell(row=r, column=c_note, value=row.get("note"))
        for col in range(1, c_note + 1):
            c = ws.cell(row=r, column=col); c.border = B
            c.alignment = Alignment(horizontal="left" if col == 2 else "center", vertical="center")
    rl = r0 + max(len(rows), 1) - 1
    t = rl + 1
    ws.merge_cells(start_row=t, start_column=1, end_row=t, end_column=c_first - 1)
    ws.cell(row=t, column=1, value="Итого пропусков занятий по группе").font = Font(bold=True)
    ws.cell(row=t, column=c_miss, value=f"=SUM({L(c_miss)}{r0}:{L(c_miss)}{rl})")
    ws.cell(row=t, column=c_bad, value=f"=SUM({L(c_bad)}{r0}:{L(c_bad)}{rl})")
    ws.cell(row=t, column=c_avg, value=f'=IFERROR(ROUND(AVERAGE({L(c_avg)}{r0}:{L(c_avg)}{rl}),2),"")')
    ws.merge_cells(start_row=t + 1, start_column=1, end_row=t + 1, end_column=c_first - 1)
    ws.cell(row=t + 1, column=1, value="Пропуски занятий без уважительной причины на 1 студента")
    ws.cell(row=t + 1, column=c_bad, value=f'=IFERROR(ROUND(AVERAGE({L(c_bad)}{r0}:{L(c_bad)}{rl}),1),"")')
    for k, (title, low) in enumerate((("Качество знаний", 4), ("% успеваемости", 3))):
        rr = t + 2 + k
        ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=c_first - 1)
        ws.cell(row=rr, column=1, value=title).font = Font(bold=True)
        for j in range(n):
            col = L(c_first + j)
            rng = f"{col}{r0}:{col}{rl}"
            cond = f'COUNTIF({rng},">={low}")'
            ws.cell(row=rr, column=c_first + j, value=f'=IF(COUNT({rng})=0,"",ROUND({cond}/COUNT({rng})*100,0))')
        ws.cell(row=rr, column=c_avg, value=f'=IFERROR(ROUND(AVERAGE({L(c_first)}{rr}:{L(c_first + n - 1)}{rr}),1),"")' if n else None)
    for rr in range(t, t + 4):
        for col in range(1, c_note + 1):
            ws.cell(row=rr, column=col).border = B
            if col > 2:
                ws.cell(row=rr, column=col).alignment = CENTER
    f = t + 6
    ws.cell(row=f, column=1, value="Дата")
    ws.cell(row=f, column=2, value=datetime.now().strftime("%d.%m.%Y"))
    ws.cell(row=f, column=c_first + 2, value="Куратор группы")
    ws.cell(row=f, column=c_bad, value=curator or "")
    ws.cell(row=f + 2, column=c_first + 2, value="Зав. отделением")
    ws.cell(row=f + 4, column=2, value="Примечание: «0» — неаттестация по дисциплине").font = Font(italic=True)

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 11
    for j in range(n):
        ws.column_dimensions[L(c_first + j)].width = 5.5
    for col, w in ((c_miss, 7), (c_bad, 9), (c_avg, 8), (c_note, 12)):
        ws.column_dimensions[L(col)].width = w
    ws.freeze_panes = ws.cell(row=r0, column=c_first)
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- работа с базой
def import_parsed(db, gid: int, parsed: dict, by: int | None, month: str | None = None) -> dict:
    """Сохраняет разобранную ведомость. Ненайденных студентов добавляет в группу."""
    month = month or parsed["month"]
    if not month:
        raise ValueError("Не удалось определить месяц ведомости")
    students = db.students(gid, include_archived=True)
    match = match_students(parsed["students"], students)
    mid = db.save_grade_month(gid, month, parsed["subjects"], by)
    created, matched = [], 0
    for i, row in enumerate(parsed["students"]):
        sid = match.get(i)
        if sid:
            matched += 1
            if row.get("record_no"):
                db.update_student(gid, sid, record_no=row["record_no"])
        else:
            sid = db.x("INSERT INTO students(group_id, full_name, record_no) VALUES (?,?,?)",
                       (gid, pretty_name(row["name"]), row.get("record_no")))
            created.append(pretty_name(row["name"]))
        db.save_grade_row(mid, sid, row["grades"], row.get("missed_total"), row.get("missed_bad"), row.get("note"))
    merged = db.auto_merge(gid)
    return {"month": month, "title": month_title(month), "subjects": len(parsed["subjects"]),
            "students": len(parsed["students"]), "matched": matched, "created": created, "merged": merged}


def month_view(db, gid: int, month: str) -> dict | None:
    gm = db.grade_month(gid, month)
    if not gm:
        return None
    rows = db.grade_rows(gm["id"])
    students = {s["id"]: s for s in db.students(gid, include_archived=True)}
    out = []
    for sid, r in rows.items():
        s = students.get(sid)
        if not s:
            continue
        g = list(r["grades"]) + [None] * (len(gm["subjects"]) - len(r["grades"]))
        out.append({"student_id": sid, "full_name": s["full_name"], "record_no": s.get("record_no"),
                    "archived": s["archived"], "tg_id": s["tg_id"],
                    "grades": g[:len(gm["subjects"])], "avg": row_avg(g), "missed_total": r["missed_total"],
                    "missed_bad": r["missed_bad"], "note": r["note"],
                    "fails": sum(1 for x in g if x in ("0", "2", "незач"))})
    out.sort(key=lambda x: x["full_name"].lower())
    subj = []
    for j, s in enumerate(gm["subjects"]):
        name = s["name"]
        if s.get("teacher") and name.endswith(f" ({s['teacher']})"):   # подгруппы: преподаватель и так виден ниже
            name = name[: -len(s["teacher"]) - 3]
        subj.append({**s, "name": name, **subject_stats([r["grades"][j] for r in out])})
    avgs = [r["avg"] for r in out if r["avg"] is not None]
    allg = [g for r in out for g in r["grades"]]
    st = subject_stats(allg)
    return {"month": month, "title": month_title(month), "id": gm["id"], "updated_at": gm["updated_at"],
            "subjects": subj, "rows": out,
            "summary": {"avg": round(sum(avgs) / len(avgs), 2) if avgs else None, "quality": st["quality"],
                        "progress": st["progress"], "fails": sum(r["fails"] for r in out),
                        "missed_total": sum(r["missed_total"] or 0 for r in out),
                        "missed_bad": sum(r["missed_bad"] or 0 for r in out),
                        "excellent": sum(1 for r in out if r["grades"] and all(g in (None, "5", "зач", "осв") for g in r["grades"]) and r["avg"]),
                        "students": len(out)}}


def fill_missed_from_journal(db, gid: int, month: str, hours_per_lesson: int = 2) -> int:
    """Пересчитывает часы пропусков из журнала посещаемости (пара = 2 академических часа)."""
    gm = db.grade_month(gid, month)
    if not gm:
        raise ValueError("Ведомость за этот месяц не найдена")
    y, m = map(int, month.split("-"))
    d1 = date(y, m, 1)
    d2 = date(y + (m == 12), m % 12 + 1, 1)
    recs = db.attendance_range(gid, d1.isoformat(), (d2.fromordinal(d2.toordinal() - 1)).isoformat())
    agg: dict[int, list[int]] = {}
    for r in recs:
        a = agg.setdefault(r["student_id"], [0, 0])
        if r["status"] in ("A", "N"):
            a[0] += hours_per_lesson; a[1] += hours_per_lesson
        elif r["status"] == "E":
            a[0] += hours_per_lesson
    rows = db.grade_rows(gm["id"])
    n = 0
    for s in db.students(gid):
        r = rows.get(s["id"])
        tot, bad = agg.get(s["id"], [0, 0])
        db.save_grade_row(gm["id"], s["id"], r["grades"] if r else [None] * len(gm["subjects"]), tot, bad, r["note"] if r else None)
        n += 1
    return n
