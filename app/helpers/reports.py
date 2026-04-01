from __future__ import annotations

from datetime import date, datetime

AGE_BUCKETS = [
    ("under_5", "Menos de 5 años"),
    ("5_7", "5 - 7 años"),
    ("8_10", "8 - 10 años"),
    ("11_15", "11 - 15 años"),
    ("16_21", "16 - 21 años"),
    ("22_59", "22 - 59 años"),
    ("60_plus", "60 años en adelante"),
]


def calc_age(dob):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def normalize_text(value: str | None) -> str:
    return (value or "").strip()


def chunk_rows(rows: list[dict], size: int) -> list[list[dict]]:
    if size <= 0:
        return [rows]
    chunks = [rows[i:i + size] for i in range(0, len(rows), size)]
    return chunks or [[]]


def get_age_bucket(age: int | None) -> str | None:
    if age is None or age < 0:
        return None
    if age < 5:
        return "under_5"
    if age <= 7:
        return "5_7"
    if age <= 10:
        return "8_10"
    if age <= 15:
        return "11_15"
    if age <= 21:
        return "16_21"
    if age <= 59:
        return "22_59"
    return "60_plus"


def parse_optional_int(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    value = value.strip()
    if not value:
        return None
    return int(value)


def parse_optional_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    value = value.strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_period_filter(period_type: str | None, month, year, start_date, end_date):
    month = parse_optional_int(month)
    year = parse_optional_int(year)
    start_date = parse_optional_date(start_date)
    end_date = parse_optional_date(end_date)
    is_custom = period_type == "custom" and start_date and end_date
    return {
        "period_type": period_type or "monthly",
        "month": month,
        "year": year,
        "start_date": start_date,
        "end_date": end_date,
        "is_custom": bool(is_custom),
    }


def describe_period(period: dict, month_lookup: dict[int, str]) -> str:
    if period["is_custom"]:
        return f"{period['start_date'].strftime('%d/%m/%Y')} al {period['end_date'].strftime('%d/%m/%Y')}"
    if period["month"] and period["year"]:
        return f"{month_lookup.get(period['month'], period['month'])} {period['year']}"
    return ""


def period_filename_suffix(context: dict) -> str:
    if context.get("selected_period_type") == "custom" and context.get("selected_start_date") and context.get("selected_end_date"):
        return f"{context['selected_start_date']}_a_{context['selected_end_date']}"
    month = context.get("selected_month") or ""
    year = context.get("selected_year") or ""
    return f"{year}_{month}"


def grade_letter_from_average(average: float | int | None) -> str:
    if average is None:
        return ""
    avg = float(average)
    if avg >= 90:
        return "A"
    if avg >= 80:
        return "B"
    if avg >= 70:
        return "C"
    if avg >= 60:
        return "D"
    return "F"


def notes_age_bucket(age: int | None) -> str | None:
    if age is None or age < 0:
        return None
    if age <= 4:
        return "Menos de 5 años"
    if age <= 7:
        return "5 - 7 años"
    if age <= 10:
        return "8 - 10 años"
    if age <= 15:
        return "11 - 15 años"
    if age <= 21:
        return "16 - 21 años"
    return None


def build_percentage_breakdown(counts: dict[str, int], labels: list[str]) -> list[dict[str, float | int | str]]:
    total = sum(int(counts.get(label, 0) or 0) for label in labels)
    breakdown = []
    for label in labels:
        value = int(counts.get(label, 0) or 0)
        percentage = round((value / total) * 100, 2) if total else 0.0
        breakdown.append({
            "label": label,
            "value": value,
            "percentage": percentage,
        })
    return breakdown


def summarize_participants_by_age_and_gender(participants: list):
    summary = {key: {"label": label, "f": 0, "m": 0, "total": 0} for key, label in AGE_BUCKETS}

    for participant in participants:
        age = calc_age(participant.fecha_nacimiento)
        bucket = get_age_bucket(age)
        if not bucket:
            continue
        gender = normalize_text(participant.genero).upper()
        if gender.startswith("F"):
            summary[bucket]["f"] += 1
        elif gender.startswith("M"):
            summary[bucket]["m"] += 1
        summary[bucket]["total"] += 1

    rows = []
    total_f = total_m = total_all = 0
    for key, label in AGE_BUCKETS:
        row = summary[key]
        rows.append({"label": label, "f": row["f"], "m": row["m"], "total": row["total"]})
        total_f += row["f"]
        total_m += row["m"]
        total_all += row["total"]

    return {
        "rows": rows,
        "total_f": total_f,
        "total_m": total_m,
        "total_all": total_all,
    }
