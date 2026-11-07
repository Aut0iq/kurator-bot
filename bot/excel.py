"""Отчёт по посещаемости в Excel: сводка + журнал (студенты × пары)."""
import io
from datetime import date

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from logic import STATUS_NAMES, build_stats

FILL = {
    "P": PatternFill("solid", fgColor="C6EFCE"),
    "L": PatternFill("solid", fgColor="FFEB9C"),
    "A": PatternFill("solid", fgColor="FFC7CE"),
    "E": PatternFill("solid", fgColor="DDEBF7"),
    "N": PatternFill("solid", fgColor="E7E6E6"),
}
SYMBOL = {"P": "+", "A": "н", "L": "оп", "E": "ув", "N": "—"}
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="2F5597")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _header(ws, row: int, values: list[str]) -> None:
    for i, v in enumerate(values, 1):
        c = ws.cell(row=row, column=i, value=v)
        c.font, c.fill, c.border = HEAD, HEAD_FILL, BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def build_report(group: dict, students: list[dict], records: list[dict], d1: date, d2: date) -> bytes:
    wb = Workbook()

    ws = wb.active
    ws.title = "Сводка"
    ws["A1"] = f"Посещаемость: {group['name']}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Период: {d1:%d.%m.%Y} – {d2:%d.%m.%Y}"
    _header(ws, 4, ["№", "Студент", "Был", "Опоздал", "Не был", "Не ответил", "Уважит.", "Всего", "Посещаемость, %"])
    stats = sorted(build_stats(students, records), key=lambda s: s["full_name"].lower())
    for i, s in enumerate(stats, 1):
        row = [i, s["full_name"], s["P"], s["L"], s["A"], s["N"], s["E"], s["total"], s["percent"]]
        for j, v in enumerate(row, 1):
            c = ws.cell(row=4 + i, column=j, value=v)
            c.border = BORDER
            if j > 2:
                c.alignment = Alignment(horizontal="center")
    last = 4 + len(stats)
    if stats:
        ws.conditional_formatting.add(
            f"I5:I{last}",
            ColorScaleRule(start_type="num", start_value=50, start_color="F8696B",
                           mid_type="num", mid_value=75, mid_color="FFEB84",
                           end_type="num", end_value=100, end_color="63BE7B"),
        )
    for col, w in zip("ABCDEFGHI", (5, 34, 8, 9, 8, 11, 9, 8, 16)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "C5"
    ws.cell(row=last + 2, column=2, value="Опоздание считается присутствием; уважительные причины не снижают процент; «не ответил на опрос» — пропуск.").font = Font(italic=True, color="808080")

    wj = wb.create_sheet("Журнал")
    sessions = sorted({(r["date"], r["t_start"], r["lesson_id"], r["subject"]) for r in records})
    marks = {(r["student_id"], r["date"], r["lesson_id"]): r["status"] for r in records}
    _header(wj, 1, ["Студент"] + [f"{date.fromisoformat(d):%d.%m}\n{t}\n{subj}" for d, t, _, subj in sessions])
    wj.row_dimensions[1].height = 60
    for i, s in enumerate(sorted(students, key=lambda s: s["full_name"].lower()), 2):
        c = wj.cell(row=i, column=1, value=s["full_name"])
        c.border = BORDER
        for j, (d, _, lid, _) in enumerate(sessions, 2):
            st = marks.get((s["id"], d, lid))
            c = wj.cell(row=i, column=j, value=SYMBOL.get(st, ""))
            c.border = BORDER
            c.alignment = Alignment(horizontal="center")
            if st:
                c.fill = FILL[st]
    wj.column_dimensions["A"].width = 34
    for j in range(2, len(sessions) + 2):
        wj.column_dimensions[get_column_letter(j)].width = 11
    wj.freeze_panes = "B2"
    legend_row = len(students) + 3
    wj.cell(row=legend_row, column=1, value="Обозначения:").font = Font(bold=True)
    for k, (code, sym) in enumerate(SYMBOL.items(), 1):
        c = wj.cell(row=legend_row + k, column=1, value=f"{sym} — {STATUS_NAMES[code]}")
        c.fill = FILL[code]

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


TEMPLATE_HEAD = ["День", "Начало", "Конец", "Предмет", "Тип", "Аудитория", "Преподаватель", "Неделя"]
DAYS = {"пн": 0, "понедельник": 0, "вт": 1, "вторник": 1, "ср": 2, "среда": 2, "чт": 3, "четверг": 3,
        "пт": 4, "пятница": 4, "сб": 5, "суббота": 5, "вс": 6, "воскресенье": 6}


def schedule_template(lessons: list[dict] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Расписание"
    _header(ws, 1, TEMPLATE_HEAD)
    names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    par = ["каждую", "нечёт", "чёт"]
    rows = [[names[l["weekday"]], l["t_start"], l["t_end"], l["subject"], l.get("kind") or "", l.get("room") or "",
             l.get("teacher") or "", par[l["parity"]]] for l in (lessons or []) if not l.get("date")]
    if not rows:
        rows = [["Пн", "08:30", "10:00", "Математика", "Лекция", "305", "Иванов И.И.", "каждую"],
                ["Пн", "10:10", "11:40", "Физика", "Практика", "412", "", "нечёт"]]
    for r in rows:
        ws.append(r)
    for col, w in zip("ABCDEFGH", (10, 9, 9, 36, 14, 11, 24, 11)):
        ws.column_dimensions[col].width = w
    ws.cell(row=len(rows) + 3, column=1, value="День: Пн…Сб. Время ЧЧ:ММ. Неделя: каждую / нечёт / чёт. "
            "Строки можно добавлять и удалять. Пришлите файл обратно боту.").font = Font(italic=True, color="808080")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _t(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    s = str(v).strip().replace(".", ":")
    return s[:5]


def parse_schedule(data: bytes) -> tuple[list[dict], list[str]]:
    """Читает xlsx по шаблону. Возвращает (пары, ошибки)."""
    from openpyxl import load_workbook
    from logic import validate_lesson
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.active
    out, errors = [], []
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        cells = list(row) + [None] * 8
        day = str(cells[0] or "").strip().lower().rstrip(".")
        if i == 1 and day == "день":
            continue
        if not day:
            continue
        if day not in DAYS:
            if len(day) < 15:
                errors.append(f"строка {i}: непонятный день «{cells[0]}»")
            continue
        p = str(cells[7] or "").strip().lower()
        parity = 1 if p.startswith("неч") else 2 if p.startswith("чёт") or p.startswith("чет") else 0
        try:
            out.append(validate_lesson({"weekday": DAYS[day], "t_start": _t(cells[1]), "t_end": _t(cells[2]),
                                        "subject": cells[3], "kind": cells[4], "room": cells[5],
                                        "teacher": cells[6], "parity": parity}))
        except ValueError as e:
            errors.append(f"строка {i}: {e}")
    return out, errors
