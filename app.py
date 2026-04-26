from datetime import date, datetime, time, timedelta
from html import escape
import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pandas as pd
import streamlit as st


DATA_PATH = Path("data/citas.csv")
SETTINGS_PATH = Path("data/settings.json")

COLUMNS = [
    "id",
    "fecha",
    "hora",
    "cliente",
    "telefono",
    "email",
    "servicio",
    "importe",
    "estado",
    "recordatorio_enviado",
    "notas",
    "duracion_minutos",
    "fecha_notificacion",
    "fecha_confirmacion",
    "canal_recordatorio",
    "respuesta_cliente",
]

VALID_STATUSES = ["pendiente", "confirmada", "cancelada", "no-show", "completada"]
IMPORT_REQUIRED_COLUMNS = ["fecha", "hora", "cliente", "telefono", "servicio", "importe"]
IMPORT_OPTIONAL_COLUMNS = ["email", "notas", "duracion_minutos"]
CURRENCIES = ["EUR", "USD", "GBP", "MXN", "COP", "ARS", "CLP", "PEN"]
WHATSAPP_PROVIDERS = ["manual", "twilio", "whatsapp_cloud_api", "other"]
OPENING_HOUR = 8
CLOSING_HOUR = 20
SLOT_MINUTES = 15

DEFAULT_SETTINGS = {
    "business_name": "Mi negocio",
    "business_whatsapp_number": "",
    "currency": "EUR",
    "default_appointment_duration_minutes": 60,
    "reminder_hours_before": 24,
    "confirmation_deadline_hours_before": 5,
    "reminder_message_template": (
        "Hola {cliente}, te recordamos tu cita en {business_name} el {fecha} "
        "a las {hora} para {servicio}. Responde CONFIRMAR para confirmar "
        "o CANCELAR si no puedes asistir. Gracias."
    ),
    "whatsapp_provider": "manual",
    "whatsapp_api_token": "",
    "whatsapp_sender_id": "",
}


def make_id() -> str:
    return uuid4().hex[:10]


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def current_week_start(reference_date: date | None = None) -> date:
    reference_date = reference_date or date.today()
    return reference_date - timedelta(days=reference_date.weekday())


def load_settings() -> dict:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

    if SETTINGS_PATH.exists() and SETTINGS_PATH.stat().st_size > 0:
        try:
            with SETTINGS_PATH.open("r", encoding="utf-8") as file:
                saved = json.load(file)
        except (json.JSONDecodeError, OSError):
            saved = {}
    else:
        saved = {}

    if "default_appointment_duration" in saved:
        saved["default_appointment_duration_minutes"] = saved["default_appointment_duration"]
    if "confirmation_deadline_hours" in saved:
        saved["confirmation_deadline_hours_before"] = saved["confirmation_deadline_hours"]

    settings = DEFAULT_SETTINGS | {
        key: value for key, value in saved.items() if key in DEFAULT_SETTINGS
    }
    settings["business_name"] = str(settings["business_name"]).strip() or DEFAULT_SETTINGS["business_name"]
    settings["business_whatsapp_number"] = str(settings["business_whatsapp_number"]).strip()
    settings["currency"] = settings["currency"] if settings["currency"] in CURRENCIES else "EUR"
    settings["default_appointment_duration_minutes"] = safe_duration(
        settings["default_appointment_duration_minutes"],
        DEFAULT_SETTINGS["default_appointment_duration_minutes"],
    )
    reminder_hours = pd.to_numeric(settings["reminder_hours_before"], errors="coerce")
    settings["reminder_hours_before"] = (
        DEFAULT_SETTINGS["reminder_hours_before"]
        if pd.isna(reminder_hours)
        else max(int(reminder_hours), 0)
    )
    deadline = pd.to_numeric(settings["confirmation_deadline_hours_before"], errors="coerce")
    settings["confirmation_deadline_hours_before"] = (
        DEFAULT_SETTINGS["confirmation_deadline_hours_before"]
        if pd.isna(deadline)
        else max(int(deadline), 0)
    )
    settings["reminder_message_template"] = (
        str(settings["reminder_message_template"]).strip()
        or DEFAULT_SETTINGS["reminder_message_template"]
    )
    settings["whatsapp_provider"] = (
        settings["whatsapp_provider"]
        if settings["whatsapp_provider"] in WHATSAPP_PROVIDERS
        else "manual"
    )
    settings["whatsapp_api_token"] = str(settings["whatsapp_api_token"]).strip()
    settings["whatsapp_sender_id"] = str(settings["whatsapp_sender_id"]).strip()
    save_settings(settings)
    return settings


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as file:
        json.dump(settings, file, indent=2, ensure_ascii=False)


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    if ":" in text and not any(separator in text for separator in ["-", "/", "."]):
        return None

    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed.date()


def normalize_date(value) -> str:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


def normalize_time(value) -> str:
    text = str(value).strip()
    if not text:
        return ""

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return text
    return parsed.strftime("%H:%M")


def parse_datetime_from_row(row) -> datetime | None:
    appointment_date = parse_date(row.get("fecha", ""))
    appointment_time = normalize_time(row.get("hora", ""))
    if not appointment_date or not appointment_time:
        return None

    try:
        hour, minute = [int(part) for part in appointment_time.split(":")[:2]]
        return datetime.combine(appointment_date, time(hour, minute))
    except (TypeError, ValueError):
        return None


def safe_duration(value, default_duration: int = 60) -> int:
    duration = pd.to_numeric(value, errors="coerce")
    if pd.isna(duration) or int(duration) <= 0:
        return int(default_duration)
    return int(duration)


def create_sample_appointments() -> pd.DataFrame:
    monday = current_week_start()
    samples = [
        (0, "08:30", 60, "Laura Gomez", "600 111 222", "laura@example.com", "Corte", 35, "completada", "si", "Cliente habitual.", "", now_iso()),
        (0, "10:00", 45, "Carlos Ruiz", "600 222 333", "carlos@example.com", "Barba", 18, "confirmada", "si", "", now_iso(), now_iso()),
        (0, "12:00", 60, "Marta Diaz", "600 333 444", "marta@example.com", "Color", 75, "no-show", "si", "No asistio la ultima vez.", now_iso(), ""),
        (1, "09:00", 60, "Ana Perez", "600 444 555", "ana@example.com", "Manicura", 28, "pendiente", "no", "", "", ""),
        (1, "11:30", 30, "Javier Marin", "600 555 666", "javier@example.com", "Masaje", 55, "cancelada", "no", "Cancelada por el cliente.", "", ""),
        (1, "16:00", 75, "Sofia Lopez", "600 666 777", "sofia@example.com", "Tratamiento facial", 65, "confirmada", "si", "", now_iso(), now_iso()),
        (2, "08:00", 60, "Nuria Blanco", "600 777 888", "nuria@example.com", "Depilacion", 32, "pendiente", "no", "", "", ""),
        (2, "10:30", 45, "Diego Santos", "600 888 999", "diego@example.com", "Fisioterapia", 60, "completada", "si", "", now_iso(), now_iso()),
        (2, "18:00", 60, "Marta Diaz", "600 333 444", "marta@example.com", "Color", 75, "pendiente", "no", "Mismo telefono con no-show previo.", "", ""),
        (3, "09:30", 60, "Elena Torres", "601 111 222", "elena@example.com", "Corte y peinado", 48, "confirmada", "si", "", now_iso(), now_iso()),
        (3, "13:00", 30, "Pablo Vega", "601 222 333", "pablo@example.com", "Revision", 40, "pendiente", "si", "", now_iso(), ""),
        (3, "17:30", 60, "Lucia Romero", "601 333 444", "lucia@example.com", "Uñas", 30, "no-show", "no", "", "", ""),
        (4, "08:30", 60, "Miguel Cano", "601 444 555", "miguel@example.com", "Entrenamiento", 45, "pendiente", "no", "", "", ""),
        (4, "12:30", 45, "Isabel Mora", "601 555 666", "isabel@example.com", "Consulta", 50, "confirmada", "si", "", now_iso(), now_iso()),
        (4, "19:00", 30, "Raul Navarro", "601 666 777", "raul@example.com", "Corte", 30, "cancelada", "no", "", "", ""),
        (5, "10:00", 90, "Clara Martin", "601 777 888", "clara@example.com", "Color y corte", 90, "pendiente", "no", "", "", ""),
        (5, "14:00", 60, "Hugo Leon", "601 888 999", "hugo@example.com", "Masaje", 55, "completada", "si", "", now_iso(), now_iso()),
        (5, "18:30", 45, "Teresa Gil", "601 999 000", "teresa@example.com", "Tratamiento", 70, "confirmada", "si", "", now_iso(), now_iso()),
    ]

    rows = []
    for day_offset, hour, duration, client, phone, email, service, amount, status, reminder, notes, notification, confirmation in samples:
        rows.append(
            {
                "id": make_id(),
                "fecha": (monday + timedelta(days=day_offset)).isoformat(),
                "hora": hour,
                "cliente": client,
                "telefono": phone,
                "email": email,
                "servicio": service,
                "importe": amount,
                "estado": status,
                "recordatorio_enviado": reminder,
                "notas": notes,
                "duracion_minutos": duration,
                "fecha_notificacion": notification,
                "fecha_confirmacion": confirmation,
                "canal_recordatorio": "whatsapp_manual" if notification else "",
                "respuesta_cliente": "CONFIRMAR" if confirmation and status == "confirmada" else "",
            }
        )

    return pd.DataFrame(rows, columns=COLUMNS)


def ensure_data_file() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not DATA_PATH.exists() or DATA_PATH.stat().st_size == 0:
        create_sample_appointments().to_csv(DATA_PATH, index=False)


def load_appointments(settings: dict) -> pd.DataFrame:
    ensure_data_file()

    try:
        df = pd.read_csv(DATA_PATH, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        df = create_sample_appointments()
        save_appointments(df)

    for column in COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df = df[COLUMNS]
    if df.empty:
        df = create_sample_appointments()
        save_appointments(df)

    missing_ids = df["id"].astype(str).str.strip() == ""
    df.loc[missing_ids, "id"] = [make_id() for _ in range(missing_ids.sum())]
    df["fecha"] = df["fecha"].apply(normalize_date)
    df["hora"] = df["hora"].apply(normalize_time)
    df["importe"] = pd.to_numeric(df["importe"], errors="coerce").fillna(0.0)
    df["duracion_minutos"] = df["duracion_minutos"].apply(
        lambda value: safe_duration(value, settings["default_appointment_duration_minutes"])
    )
    df["estado"] = df["estado"].astype(str).str.lower()
    df["estado"] = df["estado"].where(df["estado"].isin(VALID_STATUSES), "pendiente")
    df["recordatorio_enviado"] = df["recordatorio_enviado"].astype(str).str.lower()
    df["recordatorio_enviado"] = df["recordatorio_enviado"].where(
        df["recordatorio_enviado"].isin(["si", "no"]),
        "no",
    )
    return df


def save_appointments(df: pd.DataFrame) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = df.copy()
    for column in COLUMNS:
        if column not in output.columns:
            output[column] = ""
    output = output[COLUMNS]
    output.to_csv(DATA_PATH, index=False)


def append_note(existing_notes: str, note: str) -> str:
    existing_notes = str(existing_notes).strip()
    if not existing_notes:
        return note
    if note in existing_notes:
        return existing_notes
    return f"{existing_notes}\n{note}"


def auto_cancel_unconfirmed(df: pd.DataFrame, settings: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    updated = df.copy()
    cancelled_indexes = []
    deadline_hours = settings["confirmation_deadline_hours_before"]
    current_time = datetime.now()

    for index, row in updated.iterrows():
        appointment_dt = parse_datetime_from_row(row)
        if appointment_dt is None:
            continue

        should_cancel = (
            str(row["estado"]).lower() == "pendiente"
            and str(row["recordatorio_enviado"]).lower() == "si"
            and appointment_dt > current_time
            and current_time >= appointment_dt - timedelta(hours=deadline_hours)
        )
        if not should_cancel:
            continue

        note = "Auto-cancelada por falta de confirmación antes del límite configurado."
        updated.at[index, "estado"] = "cancelada"
        updated.at[index, "notas"] = append_note(row.get("notas", ""), note)
        cancelled_indexes.append(index)

    return updated, updated.loc[cancelled_indexes].copy()


def validate_appointment(row: dict) -> list[str]:
    errors = []

    if not row.get("fecha"):
        errors.append("La fecha es obligatoria.")
    if not row.get("hora"):
        errors.append("La hora es obligatoria.")
    if not row.get("cliente", "").strip():
        errors.append("El cliente es obligatorio.")
    if not row.get("telefono", "").strip():
        errors.append("El telefono es obligatorio.")
    if not row.get("servicio", "").strip():
        errors.append("El servicio es obligatorio.")
    if row.get("importe", 0) < 0:
        errors.append("El importe no puede ser negativo.")
    if safe_duration(row.get("duracion_minutos", 0), 0) <= 0:
        errors.append("La duracion debe ser mayor que cero.")

    return errors


def clean_phone_number(phone: str) -> str:
    text = str(phone).strip()
    for character in [" ", "-", "+", "(", ")"]:
        text = text.replace(character, "")
    return text


def calculate_risk(row, df: pd.DataFrame) -> str:
    status = str(row.get("estado", "")).lower()
    phone = clean_phone_number(row.get("telefono", ""))

    if status in ["confirmada", "completada"]:
        return "bajo"

    had_previous_no_show = False
    if phone:
        phones = df["telefono"].astype(str).apply(clean_phone_number)
        same_phone_no_shows = df[
            (phones == phone)
            & (df["estado"].astype(str).str.lower() == "no-show")
            & (df["id"].astype(str) != str(row.get("id", "")))
        ].copy()

        row_date = parse_date(row.get("fecha", ""))
        if row_date:
            same_phone_no_shows["fecha_parsed"] = same_phone_no_shows["fecha"].apply(parse_date)
            same_phone_no_shows = same_phone_no_shows[
                same_phone_no_shows["fecha_parsed"].notna()
                & (same_phone_no_shows["fecha_parsed"] < row_date)
            ]

        had_previous_no_show = not same_phone_no_shows.empty

    if status == "pendiente" and (
        str(row.get("recordatorio_enviado", "")).lower() == "no" or had_previous_no_show
    ):
        return "alto"
    if had_previous_no_show:
        return "alto"
    if status == "pendiente":
        return "medio"
    return "bajo"


def add_risk_scores(df: pd.DataFrame) -> pd.DataFrame:
    scored = df.copy()
    if scored.empty:
        scored["riesgo_no_show"] = []
        return scored

    scored["riesgo_no_show"] = scored.apply(lambda row: calculate_risk(row, df), axis=1)
    return scored


def projected_monthly_lost_revenue(df: pd.DataFrame, lost_revenue: float) -> float:
    if df.empty or lost_revenue <= 0:
        return 0.0

    valid_dates = df["fecha"].apply(parse_date).dropna()
    if valid_dates.empty:
        return lost_revenue

    date_range_days = max((valid_dates.max() - valid_dates.min()).days + 1, 1)
    return lost_revenue / date_range_days * 30


def metric_money(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}"


def render_template(template: str, row, settings: dict) -> str:
    values = {
        "business_name": settings["business_name"],
        "cliente": row.get("cliente", ""),
        "fecha": row.get("fecha", ""),
        "hora": row.get("hora", ""),
        "servicio": row.get("servicio", ""),
    }
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return DEFAULT_SETTINGS["reminder_message_template"].format(**values)


def make_whatsapp_link(row, settings: dict) -> str:
    phone = clean_phone_number(row.get("telefono", ""))
    message = render_template(settings["reminder_message_template"], row, settings)
    return make_wa_me_link(phone, message)


def make_wa_me_link(phone: str, message: str) -> str:
    return f"https://wa.me/{clean_phone_number(phone)}?text={quote(message)}"


def send_whatsapp_message(phone: str, message: str, settings: dict) -> dict:
    provider = settings.get("whatsapp_provider", "manual")
    if provider == "manual":
        return {
            "sent": False,
            "mode": "manual",
            "link": make_wa_me_link(phone, message),
        }

    return {
        "sent": False,
        "mode": "not_implemented",
        "error": "Proveedor WhatsApp todavía no implementado",
    }


def week_days_for(reference_date: date) -> list[date]:
    monday = current_week_start(reference_date)
    return [monday + timedelta(days=offset) for offset in range(6)]


def time_slots() -> list[str]:
    start = datetime.combine(date.today(), time(OPENING_HOUR, 0))
    end = datetime.combine(date.today(), time(CLOSING_HOUR, 0))
    slots = []
    current = start
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=SLOT_MINUTES)
    return slots


def day_label(day: date) -> str:
    names = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]
    return f"{names[day.weekday()]} {day.strftime('%d/%m')}"


def status_style(row) -> tuple[str, str]:
    status = str(row.get("estado", "")).lower()
    reminder_sent = str(row.get("recordatorio_enviado", "")).lower() == "si"

    if status == "no-show":
        return "#7f1d1d", "#ffffff"
    if status == "cancelada":
        return "#d1d5db", "#111827"
    if status == "completada":
        return "#bfdbfe", "#1e3a8a"
    if status == "confirmada":
        return "#bbf7d0", "#14532d"
    if reminder_sent and status != "confirmada":
        return "#fecaca", "#7f1d1d"
    return "#fef08a", "#713f12"


def appointment_covers_slot(row, day: date, slot: str) -> bool:
    start_dt = parse_datetime_from_row(row)
    if start_dt is None or start_dt.date() != day:
        return False

    slot_hour, slot_minute = [int(part) for part in slot.split(":")]
    slot_dt = datetime.combine(day, time(slot_hour, slot_minute))
    end_dt = start_dt + timedelta(minutes=safe_duration(row.get("duracion_minutos"), 60))
    return start_dt <= slot_dt < end_dt


def slot_datetime(day: date, slot: str) -> datetime | None:
    try:
        slot_hour, slot_minute = [int(part) for part in slot.split(":")[:2]]
        return datetime.combine(day, time(slot_hour, slot_minute))
    except (TypeError, ValueError):
        return None


def slot_phase(row, day: date, slot: str) -> str:
    start_dt = parse_datetime_from_row(row)
    slot_dt = slot_datetime(day, slot)
    if start_dt is None or slot_dt is None:
        return ""

    end_dt = start_dt + timedelta(minutes=safe_duration(row.get("duracion_minutos"), 60))
    if slot_dt == start_dt and slot_dt + timedelta(minutes=SLOT_MINUTES) >= end_dt:
        return "single"
    if slot_dt == start_dt:
        return "start"
    if slot_dt + timedelta(minutes=SLOT_MINUTES) >= end_dt:
        return "end"

    return "middle"


def render_calendar_html(df: pd.DataFrame, week_days: list[date]) -> str:
    appointments_df = df.copy()
    slots = time_slots()
    headers = "".join(f"<th>{escape(day_label(day))}</th>" for day in week_days)
    rows = []

    for slot in slots:
        cells = [f"<td class='time-cell'>{slot}</td>"]
        for day in week_days:
            if appointments_df.empty:
                appointments = appointments_df
            else:
                appointments = appointments_df[
                    appointments_df.apply(
                        lambda row: appointment_covers_slot(row, day, slot),
                        axis=1,
                    )
                ].sort_values(["hora", "cliente", "servicio"])

            if appointments.empty:
                cells.append("<td class='calendar-cell empty-cell'></td>")
                continue

            appointment = appointments.iloc[0]
            row = appointment.to_dict()
            bg, fg = status_style(row)
            phase = slot_phase(row, day, slot)
            duration = safe_duration(row.get("duracion_minutos", 60))
            extra_count = len(appointments) - 1
            overlap = f"<span class='overlap'>+{extra_count}</span>" if extra_count else ""

            if phase in ["start", "single"]:
                content = (
                    "<div class='appointment-text'>"
                    f"<strong>{escape(str(row.get('cliente', '')))}</strong><br>"
                    f"{escape(str(row.get('servicio', '')))}<br>"
                    f"{escape(str(row.get('estado', '')))} · {duration} min"
                    f"{overlap}"
                    "</div>"
                )
            else:
                content = f"<span class='continuation'>{overlap}</span>"

            cells.append(
                "<td "
                f"class='calendar-cell occupied-cell appointment-{phase}' "
                f"style='background:{bg}; color:{fg}; border-color:{bg};'>"
                f"{content}</td>"
            )

        rows.append(f"<tr>{''.join(cells)}</tr>")

    return f"""
    <style>
        .calendar-wrap {{
            overflow-x: auto;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
        }}
        .calendar-table {{
            width: 100%;
            min-width: 1120px;
            border-collapse: collapse;
            table-layout: fixed;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        .calendar-table th {{
            position: sticky;
            top: 0;
            z-index: 1;
            background: #111827;
            color: #ffffff;
            padding: 8px;
            font-size: 13px;
            border: 1px solid #374151;
        }}
        .calendar-table td {{
            height: 42px;
            vertical-align: top;
            border: 1px solid #e5e7eb;
            background: #ffffff;
            padding: 0;
            font-size: 12px;
        }}
        .calendar-table .time-cell {{
            width: 64px;
            background: #f9fafb;
            color: #374151;
            font-weight: 700;
            text-align: center;
            vertical-align: middle;
        }}
        .calendar-cell {{
            position: relative;
            box-sizing: border-box;
        }}
        .empty-cell {{
            background: #ffffff;
        }}
        .occupied-cell {{
            border-left-width: 4px;
            border-right-width: 4px;
        }}
        .appointment-start {{
            border-top-width: 4px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }}
        .appointment-single {{
            border-width: 4px;
            border-radius: 6px;
        }}
        .appointment-middle {{
            border-top-color: transparent !important;
            border-bottom-color: transparent !important;
        }}
        .appointment-end {{
            border-bottom-width: 4px;
            border-bottom-left-radius: 6px;
            border-bottom-right-radius: 6px;
        }}
        .appointment-text {{
            padding: 6px 7px;
            line-height: 1.25;
            box-sizing: border-box;
            min-height: 100%;
        }}
        .continuation {{
            display: block;
            min-height: 100%;
            opacity: 0.35;
        }}
        .overlap {{
            position: absolute;
            right: 5px;
            bottom: 3px;
            font-weight: 700;
            font-size: 11px;
        }}
    </style>
    <div class="calendar-wrap">
        <table class="calendar-table">
            <thead><tr><th>Hora</th>{headers}</tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </div>
    """


def create_pending_appointment(
    df: pd.DataFrame,
    appointment_date: date,
    appointment_time: str,
    duration_minutes: int,
    cliente: str,
    telefono: str,
    email: str,
    servicio: str,
    importe: float,
    notas: str,
) -> bool:
    row = {
        "id": make_id(),
        "fecha": appointment_date.isoformat() if appointment_date else "",
        "hora": appointment_time,
        "cliente": cliente.strip(),
        "telefono": telefono.strip(),
        "email": email.strip(),
        "servicio": servicio.strip(),
        "importe": float(importe),
        "estado": "pendiente",
        "recordatorio_enviado": "no",
        "notas": notas.strip(),
        "duracion_minutos": int(duration_minutes),
        "fecha_notificacion": "",
        "fecha_confirmacion": "",
        "canal_recordatorio": "",
        "respuesta_cliente": "",
    }
    errors = validate_appointment(row)

    if errors:
        for error in errors:
            st.error(error)
        return False

    updated = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_appointments(updated)
    st.success("Cita creada correctamente.")
    return True


def calendar_tab(df: pd.DataFrame, settings: dict) -> None:
    st.subheader("Calendario")
    selected_week_date = st.date_input("Semana", value=date.today())
    week_days = week_days_for(selected_week_date)

    st.caption(
        f"Horario de 08:00 a 20:00 en bloques de 15 minutos. "
        f"Semana del {week_days[0].strftime('%d/%m/%Y')} al {week_days[-1].strftime('%d/%m/%Y')}."
    )

    col1, col2, col3, col4 = st.columns([1.4, 1, 1, 1])
    selected_day = col1.selectbox(
        "Dia",
        week_days,
        format_func=lambda value: f"{day_label(value)} ({value.isoformat()})",
    )
    selected_time = col2.selectbox("Hora de inicio", time_slots())
    duration = col3.number_input(
        "Duracion minutos",
        min_value=15,
        max_value=480,
        value=int(settings["default_appointment_duration_minutes"]),
        step=15,
    )
    if col4.button("Añadir cita en este hueco", type="primary"):
        st.session_state["show_calendar_form"] = True
        st.session_state["calendar_date"] = selected_day
        st.session_state["calendar_time"] = selected_time
        st.session_state["calendar_duration"] = int(duration)

    if st.session_state.get("show_calendar_form"):
        form_date = st.session_state.get("calendar_date", selected_day)
        form_time = st.session_state.get("calendar_time", selected_time)
        form_duration = st.session_state.get("calendar_duration", int(duration))

        with st.form("calendar_appointment_form", clear_on_submit=True):
            st.markdown(
                f"**Nueva cita:** {day_label(form_date)} a las {form_time} "
                f"({form_duration} minutos)"
            )
            cliente = st.text_input("Cliente")
            phone_col, email_col = st.columns(2)
            telefono = phone_col.text_input("Telefono")
            email = email_col.text_input("Email")
            servicio = st.text_input("Servicio")
            importe = st.number_input("Importe", min_value=0.0, step=1.0, format="%.2f")
            notas = st.text_area("Notas")
            submitted = st.form_submit_button("Guardar cita")

        if submitted:
            created = create_pending_appointment(
                df,
                form_date,
                form_time,
                form_duration,
                cliente,
                telefono,
                email,
                servicio,
                importe,
                notas,
            )
            if created:
                st.session_state["show_calendar_form"] = False
                st.rerun()

    st.markdown(render_calendar_html(df, week_days), unsafe_allow_html=True)


def statistics_tab(df: pd.DataFrame, settings: dict) -> None:
    st.subheader("Estadísticas")
    scored = add_risk_scores(df)
    total = len(df)
    expected_revenue = df.loc[
        ~df["estado"].isin(["cancelada", "no-show"]),
        "importe",
    ].sum()
    lost_revenue = df.loc[df["estado"] == "no-show", "importe"].sum()
    no_show_count = (df["estado"] == "no-show").sum()
    no_show_percentage = (no_show_count / total * 100) if total else 0
    appointments_at_risk = (scored["riesgo_no_show"] == "alto").sum() if not scored.empty else 0
    monthly_projection = projected_monthly_lost_revenue(df, lost_revenue)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total citas", total)
    col2.metric("Ingresos previstos", metric_money(expected_revenue, settings["currency"]))
    col3.metric("Perdido por no-shows", metric_money(lost_revenue, settings["currency"]))

    col4, col5, col6 = st.columns(3)
    col4.metric("% no-show", f"{no_show_percentage:.1f}%")
    col5.metric("Citas en riesgo", appointments_at_risk)
    col6.metric(
        "Perdida mensual estimada",
        metric_money(monthly_projection, settings["currency"]),
    )

    st.subheader("Resumen por estado")
    if df.empty:
        st.info("Todavia no hay citas registradas.")
    else:
        status_counts = df["estado"].value_counts().reindex(VALID_STATUSES, fill_value=0)
        st.bar_chart(status_counts)


def new_appointment_tab(df: pd.DataFrame, settings: dict) -> None:
    st.subheader("Nueva cita")

    with st.form("new_appointment_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        appointment_date = col1.date_input("Fecha")
        appointment_time = col2.selectbox("Hora", time_slots())
        duration = col3.number_input(
            "Duracion minutos",
            min_value=15,
            max_value=480,
            value=int(settings["default_appointment_duration_minutes"]),
            step=15,
        )

        cliente = st.text_input("Cliente")
        phone_col, email_col = st.columns(2)
        telefono = phone_col.text_input("Telefono")
        email = email_col.text_input("Email")
        servicio = st.text_input("Servicio")
        importe = st.number_input("Importe", min_value=0.0, step=1.0, format="%.2f")
        notas = st.text_area("Notas")
        submitted = st.form_submit_button("Crear cita")

    if submitted:
        created = create_pending_appointment(
            df,
            appointment_date,
            appointment_time,
            int(duration),
            cliente,
            telefono,
            email,
            servicio,
            importe,
            notas,
        )
        if created:
            st.rerun()


def read_uploaded_file(uploaded_file) -> pd.DataFrame | None:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file)
        if uploaded_file.name.lower().endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"No se pudo leer el archivo: {exc}")
        return None

    st.error("Formato no soportado. Sube un CSV o XLSX.")
    return None


def import_tab(df: pd.DataFrame, settings: dict) -> None:
    st.subheader("Importar citas")
    uploaded_file = st.file_uploader("Archivo CSV o XLSX", type=["csv", "xlsx", "xls"])

    if uploaded_file is None:
        st.info("Columnas requeridas: fecha, hora, cliente, telefono, servicio, importe.")
        return

    imported = read_uploaded_file(uploaded_file)
    if imported is None:
        return

    imported.columns = [str(column).strip().lower() for column in imported.columns]
    missing = [column for column in IMPORT_REQUIRED_COLUMNS if column not in imported.columns]
    if missing:
        st.error(f"Faltan columnas requeridas: {', '.join(missing)}.")
        return

    for column in IMPORT_OPTIONAL_COLUMNS:
        if column not in imported.columns:
            imported[column] = ""

    rows = []
    errors = []
    existing_ids = set(df["id"].astype(str))

    for number, row in imported.iterrows():
        appointment = {
            "id": make_id(),
            "fecha": normalize_date(row["fecha"]),
            "hora": normalize_time(row["hora"]),
            "cliente": str(row["cliente"]).strip(),
            "telefono": str(row["telefono"]).strip(),
            "email": str(row.get("email", "")).strip(),
            "servicio": str(row["servicio"]).strip(),
            "importe": pd.to_numeric(row["importe"], errors="coerce"),
            "estado": "pendiente",
            "recordatorio_enviado": "no",
            "notas": str(row.get("notas", "")).strip(),
            "duracion_minutos": safe_duration(
                row.get("duracion_minutos", ""),
                settings["default_appointment_duration_minutes"],
            ),
            "fecha_notificacion": "",
            "fecha_confirmacion": "",
            "canal_recordatorio": "",
            "respuesta_cliente": "",
        }

        while appointment["id"] in existing_ids:
            appointment["id"] = make_id()
        existing_ids.add(appointment["id"])

        if pd.isna(appointment["importe"]):
            appointment["importe"] = -1

        row_errors = validate_appointment(appointment)
        if row_errors:
            errors.append(f"Fila {number + 2}: {' '.join(row_errors)}")
        else:
            appointment["importe"] = float(appointment["importe"])
            rows.append(appointment)

    if errors:
        st.error("Hay errores en el archivo. Corrigelos y vuelve a intentarlo.")
        with st.expander("Ver errores"):
            for error in errors:
                st.write(error)
        return

    preview = pd.DataFrame(rows, columns=COLUMNS)
    st.dataframe(preview, use_container_width=True, hide_index=True)

    if st.button("Importar citas", type="primary"):
        updated = pd.concat([df, preview], ignore_index=True)
        save_appointments(updated)
        st.success(f"Se importaron {len(preview)} cita(s).")
        st.rerun()


def appointment_options(df: pd.DataFrame) -> dict:
    return {
        f"{row.id} | {row.fecha} {row.hora} - {row.cliente} ({row.telefono})": row.id
        for row in df.sort_values(["fecha", "hora"]).itertuples()
    }


def reminder_candidates(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    rows = []
    current_time = datetime.now()
    reminder_window = timedelta(hours=settings["reminder_hours_before"])

    for _, row in df.iterrows():
        appointment_dt = parse_datetime_from_row(row)
        if appointment_dt is None:
            continue

        if (
            str(row.get("estado", "")).lower() == "pendiente"
            and str(row.get("recordatorio_enviado", "")).lower() == "no"
            and appointment_dt > current_time
            and appointment_dt - current_time <= reminder_window
        ):
            rows.append(row)

    return pd.DataFrame(rows, columns=df.columns)


def pending_confirmations(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (df["estado"].astype(str).str.lower() == "pendiente")
        & (df["recordatorio_enviado"].astype(str).str.lower() == "si")
    ].copy()


def reminders_tab(df: pd.DataFrame, settings: dict) -> None:
    st.subheader("Recordatorios")
    candidates = reminder_candidates(df, settings)

    st.markdown("### Recordatorios por enviar")
    if candidates.empty:
        st.info("No hay recordatorios dentro de la ventana configurada.")
    else:
        st.dataframe(
            candidates[
                [
                    "id",
                    "fecha",
                    "hora",
                    "duracion_minutos",
                    "cliente",
                    "telefono",
                    "servicio",
                    "recordatorio_enviado",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        options = appointment_options(candidates)
        selected_label = st.selectbox("Selecciona appointment ID para enviar", list(options.keys()))
        appointment_id = options[selected_label]
        selected_row = candidates.loc[candidates["id"] == appointment_id].iloc[0]
        message = render_template(settings["reminder_message_template"], selected_row, settings)
        result = send_whatsapp_message(selected_row["telefono"], message, settings)

        st.text_area("Mensaje WhatsApp", value=message, height=120)
        if result["mode"] == "manual":
            if clean_phone_number(selected_row["telefono"]):
                st.link_button("Abrir enlace WhatsApp", result["link"])
            else:
                st.error("Esta cita no tiene un telefono valido para WhatsApp.")
        else:
            st.error(result["error"])

        if st.button("Marcar recordatorio enviado", type="primary"):
            df.loc[df["id"] == appointment_id, "recordatorio_enviado"] = "si"
            df.loc[df["id"] == appointment_id, "fecha_notificacion"] = now_iso()
            df.loc[df["id"] == appointment_id, "canal_recordatorio"] = "whatsapp_manual"
            save_appointments(df)
            st.success("Recordatorio marcado como enviado.")
            st.rerun()

    st.markdown("### Pendientes de confirmación")
    confirmations = pending_confirmations(df)
    if confirmations.empty:
        st.info("No hay citas pendientes de confirmacion.")
        return

    st.dataframe(
        confirmations[
            [
                "id",
                "fecha",
                "hora",
                "cliente",
                "telefono",
                "servicio",
                "fecha_notificacion",
                "canal_recordatorio",
                "respuesta_cliente",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    options = appointment_options(confirmations)
    selected_label = st.selectbox("Selecciona appointment ID pendiente", list(options.keys()))
    appointment_id = options[selected_label]

    col1, col2 = st.columns(2)
    if col1.button("Simular CONFIRMAR"):
        df.loc[df["id"] == appointment_id, "estado"] = "confirmada"
        df.loc[df["id"] == appointment_id, "fecha_confirmacion"] = now_iso()
        df.loc[df["id"] == appointment_id, "respuesta_cliente"] = "CONFIRMAR"
        save_appointments(df)
        st.success("Respuesta CONFIRMAR simulada. Cita confirmada.")
        st.rerun()

    if col2.button("Simular CANCELAR"):
        df.loc[df["id"] == appointment_id, "estado"] = "cancelada"
        df.loc[df["id"] == appointment_id, "fecha_confirmacion"] = now_iso()
        df.loc[df["id"] == appointment_id, "respuesta_cliente"] = "CANCELAR"
        save_appointments(df)
        st.success("Respuesta CANCELAR simulada. Cita cancelada.")
        st.rerun()


def settings_tab(settings: dict) -> None:
    st.subheader("Configuración")

    with st.form("settings_form"):
        business_name = st.text_input("business_name", value=settings["business_name"])
        business_whatsapp_number = st.text_input(
            "business_whatsapp_number",
            value=settings["business_whatsapp_number"],
        )
        currency = st.selectbox(
            "currency",
            CURRENCIES,
            index=CURRENCIES.index(settings["currency"]) if settings["currency"] in CURRENCIES else 0,
        )
        default_duration = st.number_input(
            "default_appointment_duration_minutes",
            min_value=15,
            max_value=480,
            value=int(settings["default_appointment_duration_minutes"]),
            step=15,
        )
        reminder_hours = st.number_input(
            "reminder_hours_before",
            min_value=0,
            max_value=720,
            value=int(settings["reminder_hours_before"]),
            step=1,
        )
        deadline = st.number_input(
            "confirmation_deadline_hours_before",
            min_value=0,
            max_value=168,
            value=int(settings["confirmation_deadline_hours_before"]),
            step=1,
        )
        template = st.text_area(
            "reminder_message_template",
            value=settings["reminder_message_template"],
            height=140,
            help="Variables disponibles: {business_name}, {cliente}, {fecha}, {hora}, {servicio}",
        )
        provider = st.selectbox(
            "whatsapp_provider",
            WHATSAPP_PROVIDERS,
            index=WHATSAPP_PROVIDERS.index(settings["whatsapp_provider"]),
        )
        api_token = st.text_input(
            "whatsapp_api_token",
            value=settings["whatsapp_api_token"],
            type="password",
        )
        sender_id = st.text_input("whatsapp_sender_id", value=settings["whatsapp_sender_id"])
        submitted = st.form_submit_button("Guardar configuración")

    if submitted:
        updated = {
            "business_name": business_name.strip() or DEFAULT_SETTINGS["business_name"],
            "business_whatsapp_number": business_whatsapp_number.strip(),
            "currency": currency,
            "default_appointment_duration_minutes": int(default_duration),
            "reminder_hours_before": int(reminder_hours),
            "confirmation_deadline_hours_before": int(deadline),
            "reminder_message_template": template.strip()
            or DEFAULT_SETTINGS["reminder_message_template"],
            "whatsapp_provider": provider,
            "whatsapp_api_token": api_token.strip(),
            "whatsapp_sender_id": sender_id.strip(),
        }
        save_settings(updated)
        st.success("Configuracion guardada.")
        st.rerun()


def show_auto_cancel_warning(cancelled: pd.DataFrame) -> None:
    if cancelled.empty:
        return

    st.warning(f"{len(cancelled)} cita(s) auto-cancelada(s) por falta de confirmacion.")
    st.dataframe(
        cancelled[["fecha", "hora", "cliente", "telefono", "servicio", "notas"]],
        use_container_width=True,
        hide_index=True,
    )


def main() -> None:
    st.set_page_config(page_title="No-Show Killer", page_icon=":calendar:", layout="wide")
    st.title("No-Show Killer")

    settings = load_settings()
    df = load_appointments(settings)
    save_appointments(df)
    df, auto_cancelled = auto_cancel_unconfirmed(df, settings)
    if not auto_cancelled.empty:
        save_appointments(df)

    show_auto_cancel_warning(auto_cancelled)

    calendario, recordatorios, nueva_cita, importar, estadisticas, configuracion = st.tabs(
        ["Calendario", "Recordatorios", "Nueva cita", "Importar", "Estadísticas", "Configuración"]
    )

    with calendario:
        calendar_tab(df, settings)

    with recordatorios:
        reminders_tab(df, settings)

    with nueva_cita:
        new_appointment_tab(df, settings)

    with importar:
        import_tab(df, settings)

    with estadisticas:
        statistics_tab(df, settings)

    with configuracion:
        settings_tab(settings)


if __name__ == "__main__":
    main()
