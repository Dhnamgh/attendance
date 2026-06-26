# app.py
import os
import io
import re
import time
import base64
import urllib.parse
import unicodedata
import datetime

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image
import qrcode
import pandas as pd
import altair as alt

try:
    from streamlit_geolocation import streamlit_geolocation
except Exception:
    streamlit_geolocation = None

try:
    from geopy.distance import geodesic
except Exception:
    geodesic = None


# ===================== CẤU HÌNH =====================
MSGV_PREFIX = st.secrets.get("SESSION_PREFIX", "0607")
GV_SHEET_KEY = st.secrets["GV_SHEET"]
SV_SHEET_KEY = st.secrets["SV_SHEET"]
STAFF_SHEET_NAME = st.secrets.get("STAFF_SHEET_NAME", "NhanSu")
LOG_SHEET_NAME = st.secrets.get("LOG_SHEET_NAME", "Log")
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

LESSON_MINUTES = int(st.secrets.get("LESSON_MINUTES", 50))
BREAK_AFTER_LESSONS = int(st.secrets.get("BREAK_AFTER_LESSONS", 3))
BREAK_MINUTES = int(st.secrets.get("BREAK_MINUTES", 15))
LATE_THRESHOLD_MINUTES = int(st.secrets.get("LATE_THRESHOLD_MINUTES", 15))

LESSON_SCHEDULE = {
    1: ("07:00", "07:50"),
    2: ("07:50", "08:40"),
    3: ("08:40", "09:30"),
    4: ("09:45", "10:35"),
    5: ("10:35", "11:25"),
    7: ("13:00", "13:50"),
    8: ("13:50", "14:40"),
    9: ("14:40", "15:30"),
    10: ("15:45", "16:35"),
    11: ("16:35", "17:25"),
}
MORNING_LESSONS = [1, 2, 3, 4, 5]
AFTERNOON_LESSONS = [7, 8, 9, 10, 11]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

STAFF_COLUMNS = ["MSGV", "Họ và tên", "Đơn vị", "Bộ môn"]
LOG_COLUMNS = ["Ngày", "MSGV", "Họ và tên", "Đơn vị", "Bộ môn", "CS", "Ca", "Tiết từ", "Tiết đến", "Số tiết", "Giờ bắt đầu phân công", "Giờ kết thúc phân công", "Vào muộn phút", "IN/OUT", "Giờ", "Timestamp"]

LOCATIONS = {
    "Cơ sở 1: 217 Hồng Bàng": {
        "code": "CS1",
        "lat": 10.754665,
        "lon": 106.663381,
        "radius": 100,
        "address": "217 Hồng Bàng, Phường Chợ Lớn, TP.HCM",
    },
    "Cơ sở 2: 41-43 Đinh Tiên Hoàng": {
        "code": "CS2",
        "lat": 10.785434,
        "lon": 106.702667,
        "radius": 100,
        "address": "41-43 Đinh Tiên Hoàng, Phường Sài Gòn, TP.HCM",
    },
}
LOCATION_BY_CODE = {v["code"]: k for k, v in LOCATIONS.items()}

st.set_page_config(page_title="Hệ thống điểm danh tích hợp", layout="wide", initial_sidebar_state="expanded")

# ===================== CSS ĐÃ SỬA FONT 16 VÀ RESPONSIVE =====================
st.markdown("""
<style>
html, body, .stApp {
    color: #000000 !important;
    overflow-x: hidden !important;
}
.custom-title {
    font-family: "Times New Roman", Times, serif;
    font-size: 21px; 
    font-weight: bold;
    text-align: center;
    margin-bottom: 15px;
    color: #1E3A8A;
}
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
.stDeployButton {
    display: none !important;
    visibility: hidden !important;
}
h1, h2, h3 {
    font-weight: 900 !important;
}
label, p, span, div {
    color: #000000 !important;
}
input {
    font-weight: 700 !important;
    color: #000000 !important;
}
.stButton > button, div[data-testid="stButton"] > button {
    font-weight: 900 !important;
    white-space: normal !important;
    overflow: visible !important;
    text-align: center !important;
}
@media (max-width: 768px) {
    .block-container {
        width: 100% !important;
        max-width: 100% !important;
        padding-top: 0.8rem !important;
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
        padding-bottom: 8rem !important;
        box-sizing: border-box !important;
    }
    input {
        font-size: 1.05rem !important;
        min-height: 3rem !important;
    }
    .stButton, .stButton > button, div[data-testid="stButton"], div[data-testid="stButton"] > button {
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
    .stButton > button, div[data-testid="stButton"] > button {
        min-height: 3.4rem !important;
        font-size: 1.05rem !important;
        margin: .25rem 0 1rem 0 !important;
    }
}
</style>
<div class="custom-title">Hệ thống điểm danh</div>
""", unsafe_allow_html=True)


# ===================== TIỆN ÍCH LOGIC TIẾT / GIỜ =====================
def now_vn():
    return datetime.datetime.now(VN_TZ)

def today_date():
    return now_vn().date()

def today_str():
    return today_date().strftime("%d/%m/%Y")

def today_iso():
    return today_date().strftime("%Y-%m-%d")

def normalize_date_value(value):
    s = str(value or "").strip()
    if not s: return ""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    return s

def parse_date_value(value):
    s = normalize_date_value(value)
    if not s: return None
    try: return datetime.datetime.strptime(s, "%d/%m/%Y").date()
    except Exception: return None

def current_week_range():
    today = today_date()
    start = today - datetime.timedelta(days=today.weekday())
    end = start + datetime.timedelta(days=6)
    return start, end

def current_month_range():
    today = today_date()
    start = today.replace(day=1)
    if today.month == 12:
        end = today.replace(year=today.year + 1, month=1, day=1) - datetime.timedelta(days=1)
    else:
        end = today.replace(month=today.month + 1, day=1) - datetime.timedelta(days=1)
    return start, end

def group_bo_mon_don_vi(row):
    bo_mon = safe_str(row.get("Bộ môn"))
    don_vi = safe_str(row.get("Đơn vị"))
    return bo_mon if bo_mon else (don_vi if don_vi else "Chưa xác định")

def log_sort_key(row):
    ts = safe_str(row.get("Timestamp"))
    if ts:
        try: return datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except Exception: pass
    d = parse_date_value(row.get("Ngày")) or today_date()
    t = parse_time_value(row.get("Giờ")) or datetime.time(0, 0, 0)
    return datetime.datetime.combine(d, t)

def latest_open_in_log(logs, shift):
    ordered = sorted([r for r in logs if safe_str(r.get("Ca")) == shift], key=log_sort_key)
    open_in = None
    for r in ordered:
        action = safe_str(r.get("IN/OUT")).upper()
        if action == "IN": open_in = r
        elif action == "OUT" and open_in is not None: open_in = None
    return open_in

def parse_time_value(value):
    s = str(value or "").strip()
    if not s: return None
    m = re.search(r"(\d{1,2}:\d{2}:\d{2})", s)
    if not m: return None
    try: return datetime.datetime.strptime(m.group(1), "%H:%M:%S").time()
    except Exception: return None

def time_hhmm_to_time(s):
    return datetime.datetime.strptime(str(s), "%H:%M").time()

def time_hhmm_to_minutes(s):
    t = time_hhmm_to_time(s)
    return t.hour * 60 + t.minute

def assigned_lessons_for_shift(shift):
    return MORNING_LESSONS if shift == "Sáng" else AFTERNOON_LESSONS

def lesson_range_info(shift, lesson_from, lesson_to):
    allowed = assigned_lessons_for_shift(shift)
    lesson_from, lesson_to = int(lesson_from), int(lesson_to)
    if lesson_from not in allowed: lesson_from = allowed[0]
    if lesson_to not in allowed: lesson_to = allowed[-1]
    if lesson_to < lesson_from: lesson_to = lesson_from
    selected = [x for x in allowed if lesson_from <= x <= lesson_to]
    start_time = LESSON_SCHEDULE[selected[0]][0]
    end_time = LESSON_SCHEDULE[selected[-1]][1]
    return {
        "lesson_from": selected[0], "lesson_to": selected[-1],
        "num_lessons": len(selected), "start_time": start_time, "end_time": end_time,
        "required_minutes": time_hhmm_to_minutes(end_time) - time_hhmm_to_minutes(start_time),
    }

def late_minutes_against_assigned_start(assigned_start):
    start_t = time_hhmm_to_time(assigned_start)
    start_dt = datetime.datetime.combine(today_date(), start_t, tzinfo=VN_TZ)
    diff = int((now_vn() - start_dt).total_seconds() // 60)
    return max(0, diff)

def academic_year_range(ref_date=None):
    if ref_date is None: ref_date = today_date()
    start_year = ref_date.year if ref_date >= datetime.date(ref_date.year, 7, 1) else ref_date.year - 1
    return datetime.date(start_year, 7, 1), datetime.date(start_year + 1, 8, 31)

def time_str(): return now_vn().strftime("%H:%M:%S")
def timestamp_str(): return now_vn().strftime("%Y-%m-%d %H:%M:%S")
def infer_shift(): return "Sáng" if now_vn().hour < 12 else "Chiều"

def get_query_params():
    if hasattr(st, "query_params"): return dict(st.query_params)
    raw = st.experimental_get_query_params()
    return {k: (v[0] if isinstance(v, list) and v else v) for k, v in raw.items()}

def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", s)

def norm_search(s: str) -> str: return " ".join(strip_accents(s).lower().split())
def norm_header(s: str) -> str: return norm_search(s).replace(" ", "")
def norm_sheet_name(name: str) -> str: return re.sub(r"\s+", "", str(name or "")).lower()
def norm_digits(value) -> str: return re.sub(r"\D", "", str(value or ""))
def safe_str(value) -> str: return str(value or "").strip()

def _google_api_retry(callable_fn, retries=3, delay=1.2):
    last_error = None
    for attempt in range(retries):
        try: return callable_fn()
        except Exception as e:
            last_error = e
            if not any(code in str(e) for code in ["[500]", "[503]", "[429]", "Internal error", "Quota", "timeout"]): raise
            time.sleep(delay * (attempt + 1))
    raise last_error

def get_base_url():
    return st.secrets.get("WRAPPER_URL") or st.secrets.get("APP_BASE_URL") or "https://giangvien.streamlit.app"

def get_admin_pw():
    return st.secrets.get("ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD")

def admin_unlocked(): return bool(st.session_state.get("admin_unlocked"))

def render_admin_auth():
    with st.sidebar:
        st.header("Quản trị")
        if admin_unlocked():
            st.success("Đã đăng nhập quản trị")
            if st.button("Đăng xuất"):
                st.session_state.clear()
                st.rerun()
        else:
            pw = st.text_input("Mật khẩu quản trị", type="password")
            if st.button("Đăng nhập", type="primary", use_container_width=True):
                if get_admin_pw() and pw == get_admin_pw():
                    st.session_state["admin_unlocked"] = True
                    st.rerun()
                else: st.warning("Sai mật khẩu.")

# ===================== KẾT NỐI GOOGLE SHEETS =====================
@st.cache_resource
def get_gspread_client():
    cred = dict(st.secrets["google_service_account"])
    pk = cred.get("private_key", "").replace("\\n", "\n").replace("\r\n", "\n")
    cred["private_key"] = pk
    creds = Credentials.from_service_account_info(cred, scopes=SCOPES)
    return gspread.authorize(creds)

def get_spreadsheet(sheet_key):
    return _google_api_retry(lambda: get_gspread_client().open_by_key(sheet_key))

def get_or_create_ws(sheet_key, title, rows=1000, cols=20):
    ss = get_spreadsheet(sheet_key)
    wanted = norm_sheet_name(title)
    for ws in _google_api_retry(lambda: ss.worksheets()):
        if norm_sheet_name(ws.title) == wanted: return ws
    return _google_api_retry(lambda: ss.add_worksheet(title=title, rows=rows, cols=cols))

def ensure_header(ws, headers):
    current = _google_api_retry(lambda: ws.row_values(1))
    if not current:
        _google_api_retry(lambda: ws.update("A1", [headers]))
        return headers
    merged = current[:]
    changed = False
    for h in headers:
        if h not in merged: merged.append(h); changed = True
    if changed: _google_api_retry(lambda: ws.update("1:1", [merged]))
    return _google_api_retry(lambda: ws.row_values(1))

def staff_ws(sheet_key):
    ws = get_or_create_ws(sheet_key, STAFF_SHEET_NAME, rows=300, cols=10)
    ensure_header(ws, STAFF_COLUMNS)
    return ws

def log_ws(sheet_key):
    ws = get_or_create_ws(sheet_key, LOG_SHEET_NAME, rows=5000, cols=12)
    ensure_header(ws, LOG_COLUMNS)
    return ws

def get_all_records_by_header(ws):
    values = _google_api_retry(lambda: ws.get_all_values())
    if not values: return []
    headers = values[0]
    out = []
    for row in values[1:]:
        item = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
        if any(str(v).strip() for v in item.values()): out.append(item)
    return out

def find_user_by_code(sheet_key, code_input, label_type):
    ws = staff_ws(sheet_key)
    values = _google_api_retry(lambda: ws.get_all_values())
    if not values or len(values) < 2: return None

    headers, target = values[0], norm_digits(code_input)
    hn = [norm_header(h) for h in headers]
    
    msgv_i = hn.index("msgv") if "msgv" in hn else 0
    name_i = hn.index("hovaten") if "hovaten" in hn else 1
    unit_i = hn.index("donvi") if "donvi" in hn else 2
    dept_i = hn.index("bomon") if "bomon" in hn else 3

    matches = []
    for row in values[1:]:
        raw_digits = norm_digits(row[msgv_i] if msgv_i < len(row) else "")
        if not raw_digits: continue
        if (len(target) == 4 and raw_digits.endswith(target)) or raw_digits == target:
            matches.append({
                "MSGV": raw_digits.zfill(8) if len(raw_digits) <= 8 else raw_digits,
                "Họ và tên": row[name_i] if name_i < len(row) else "",
                "Đơn vị": row[unit_i] if unit_i < len(row) else "",
                "Bộ môn": row[dept_i] if dept_i < len(row) else "",
            })
    if len(matches) == 1: return matches[0]
    if len(matches) > 1: return {"ambiguous": True, "matches": matches}
    return None

def logs_for_user_today(sheet_key, code_full):
    target, result = norm_digits(code_full), []
    for r in get_all_records_by_header(log_ws(sheet_key)):
        row_date = normalize_date_value(r.get("Ngày"))
        row_msgv = norm_digits(r.get("MSGV"))
        if row_msgv and row_date == today_str() and (row_msgv == target or row_msgv.zfill(len(target)) == target):
            result.append(r)
    return result

def append_log(sheet_key, row):
    ws = log_ws(sheet_key)
    headers = ensure_header(ws, LOG_COLUMNS)
    values = [row.get(h, "") for h in headers]
    for attempt in range(5):
        try: return ws.append_row(values, value_input_option="USER_ENTERED")
        except Exception: time.sleep(0.7 * (attempt + 1))

def summarize_hours(records):
    if not records: return pd.DataFrame()
    df = pd.DataFrame(records)
    for c in LOG_COLUMNS:
        if c not in df.columns: df[c] = ""
    rows = []
    for keys, g in df.groupby(["Ngày", "MSGV", "Họ và tên", "Đơn vị", "Bộ môn", "Ca"], dropna=False):
        ngay, msgv, hoten, donvi, bomon, ca = keys
        ins = g[g["IN/OUT"] == "IN"]["Giờ"].tolist()
        outs = g[g["IN/OUT"] == "OUT"]["Giờ"].tolist()
        vao, ra = min(ins) if ins else "", max(outs) if outs else ""
        hours = ""
        if vao and ra:
            try:
                sec = (datetime.datetime.strptime(ra, "%H:%M:%S") - datetime.datetime.strptime(vao, "%H:%M:%S")).total_seconds()
                hours = round(sec / 3600, 2) if sec >= 0 else ""
            except Exception: pass
        rows.append({
            "Ngày": ngay, "MSGV": msgv, "Họ và tên": hoten, "Đơn vị": donvi, "Bộ môn": bomon, "Ca": ca,
            "Vào ca": vao, "Ra ca": ra, "Giờ có mặt": hours, "Cơ sở": ", ".join(sorted(set(g["CS"].astype(str)))),
        })
    return pd.DataFrame(rows)

# ===================== GPS VERIFICATION =====================
def render_location_check(campus_code):
    campus_name = LOCATION_BY_CODE.get(campus_code)
    if not campus_name:
        st.error("Cơ sở điểm danh không hợp lệ.")
        st.stop()
    campus = LOCATIONS[campus_name]
    st.info(f"Cơ sở: {campus_name}")
    if streamlit_geolocation is None or geodesic is None:
        st.error("Ứng dụng chưa cài đủ thư viện kiểm tra vị trí.")
        st.stop()
    st.caption("Cho phép truy cập vị trí để xác thực điểm danh.")
    loc = streamlit_geolocation()
    if not loc:
        st.warning("Chưa nhận được vị trí. Vui lòng bật định vị và cho phép truy cập vị trí.")
        st.stop()
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        st.warning("Không lấy được tọa độ GPS từ thiết bị. Vui lòng thử lại.")
        st.stop()
    distance = geodesic((float(lat), float(lon)), (campus["lat"], campus["lon"])).meters
    if distance > campus["radius"]:
        st.error(f"Bạn đang ngoài phạm vi điểm danh của {campus_name}.")
        st.stop()
    st.success("Vị trí hợp lệ. Có thể tiếp tục điểm danh.")

# ===================== GIAO DIỆN ĐIỂM DANH (GV & SV) =====================
def render_user_attendance(user_type, sheet_key):
    qp = get_query_params()
    campus_code = qp.get("coso", "CS1")
    
    st.subheader(f"Phân hệ Điểm danh {user_type}")
    if today_date().weekday() == 6:
        st.error("Chủ nhật không mở điểm danh.")
        st.stop()

    st.info(f"Ngày: {today_str()}")
    render_location_check(campus_code)

    shift = infer_shift()
    st.info(f"Ca hiện tại: {shift}")

    action_label = st.radio("Chọn loại điểm danh", ["Vào ca", "Ra ca"], horizontal=True, key=f"act_{user_type}")
    action = "IN" if action_label == "Vào ca" else "OUT"

    lessons_allowed = assigned_lessons_for_shift(shift)
    col_from, col_to = st.columns(2)
    with col_from:
        tiet_tu = st.number_input("Tiết dạy từ", min_value=min(lessons_allowed), max_value=max(lessons_allowed), value=min(lessons_allowed), step=1, key=f"f_{user_type}")
    with col_to:
        tiet_den = st.number_input("Đến tiết", min_value=min(lessons_allowed), max_value=max(lessons_allowed), value=min(lessons_allowed), step=1, key=f"t_{user_type}")

    info_tiet = lesson_range_info(shift, tiet_tu, tiet_den)
    st.caption(f"Phân công: tiết {info_tiet['lesson_from']} đến tiết {info_tiet['lesson_to']} ({info_tiet['num_lessons']} tiết), từ {info_tiet['start_time']} đến {info_tiet['end_time']}.")

    label_input = "4 số cuối MSGV" if user_type == "GV" else "4 số cuối MSSV"
    msgv_suffix = st.text_input(label_input, placeholder="VD: 1234", max_chars=4, key=f"inp_{user_type}")

    if st.button("Xác nhận điểm danh", type="primary", use_container_width=True, key=f"btn_{user_type}"):
        if not msgv_suffix.strip().isdigit() or len(msgv_suffix.strip()) != 4:
            st.warning(f"Vui lòng nhập đúng 4 số cuối Mã định danh.")
            st.stop()

        msgv_full = msgv_suffix.strip()
        staff = find_user_by_code(sheet_key, msgv_full, user_type)

        if not staff:
            st.error(f"Không tìm thấy dữ liệu có 4 số cuối {msgv_full}.")
            st.stop()
        if staff.get("ambiguous"):
            st.error("Mã số bị trùng với nhiều người dùng. Vui lòng liên hệ quản trị.")
            st.stop()

        msgv_full = staff.get("MSGV", msgv_full)
        current_logs = logs_for_user_today(sheet_key, msgv_full)
        open_in = latest_open_in_log(current_logs, shift)

        if action == "IN":
            session_key = f"open_{today_str()}_{msgv_full}_{shift}_{user_type}"
            if st.session_state.get(session_key) or open_in is not None:
                st.info(f"Mã số {msgv_full} đã vào ca {shift} và chưa ra ca.")
                st.stop()
            late_min = late_minutes_against_assigned_start(info_tiet["start_time"])
            if late_min > 0:
                st.warning(f"Bạn vào ca muộn {late_min} phút so với giờ phân công.")

        if action == "OUT":
            session_key = f"close_{today_str()}_{msgv_full}_{shift}_{len(current_logs)}_{user_type}"
            if st.session_state.get(session_key):
                st.info(f"Mã số {msgv_full} đã ra ca {shift}. Hệ thống không ghi trùng.")
                st.stop()
            if open_in is None:
                st.warning(f"Chưa có dữ liệu vào ca buổi {shift}. Vui lòng điểm danh vào trước.")
                st.stop()

            assigned_end = safe_str(open_in.get("Giờ kết thúc phân công")) or info_tiet["end_time"]
            if (now_vn().hour * 60 + now_vn().minute) < time_hhmm_to_minutes(assigned_end):
                st.warning(f"Chưa đến thời điểm ra ca theo tiết được phân công (Kết thúc lúc: {assigned_end}).")
                st.stop()

        t = time_str()
        append_log(sheet_key, {
            "Ngày": today_str(), "MSGV": msgv_full, "Họ và tên": staff.get("Họ và tên", ""),
            "Đơn vị": staff.get("Đơn vị", ""), "Bộ môn": staff.get("Bộ môn", ""), "CS": campus_code, "Ca": shift,
            "Tiết từ": info_tiet["lesson_from"], "Tiết đến": info_tiet["lesson_to"], "Số tiết": info_tiet["num_lessons"],
            "Giờ bắt đầu phân công": info_tiet["start_time"], "Giờ kết thúc phân công": info_tiet["end_time"],
            "Vào muộn phút": late_minutes_against_assigned_start(info_tiet["start_time"]) if action == "IN" else "",
            "IN/OUT": action, "Giờ": t, "Timestamp": timestamp_str(),
        })

        if action == "IN": st.session_state[f"open_{today_str()}_{msgv_full}_{shift}_{user_type}"] = True
        else:
            st.session_state[f"open_{today_str()}_{msgv_full}_{shift}_{user_type}"] = False
            st.session_state[session_key] = True

        st.success(f"{action_label} thành công!")
        st.write(f"Mã số: **{msgv_full}** | Đối tượng: **{user_type}** | Giờ: **{t}**")

# ===================== CÁC TAB QUẢN TRỊ GỐC CỦA THẦY =====================
def render_tab_qr():
    st.subheader("Tạo QR cố định theo cơ sở")
    target_type = st.radio("Tạo QR cho đối tượng:", ["Giảng viên", "Sinh viên"], horizontal=True)
    param_type = "gv=1" if target_type == "Giảng viên" else "sv=1"
    
    campus_name = st.selectbox("Chọn cơ sở", list(LOCATIONS.keys()))
    campus_code = LOCATIONS[campus_name]["code"]

    if st.button("Tạo QR cố định", type="primary", use_container_width=True):
        qr_data = f"{get_base_url()}/?{param_type}&coso={urllib.parse.quote(campus_code)}"
        qr = qrcode.make(qr_data)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)
        st.image(Image.open(buf), caption=f"QR {target_type} tại {campus_code}", width=380)
        st.code(qr_data)

def render_tab_search(sheet_key):
    st.subheader("Tìm kiếm thông tin")
    q = st.text_input("Nhập 4 số cuối, đầy đủ mã số hoặc họ tên")
    if st.button("Tìm kiếm", use_container_width=True):
        rows = get_all_records_by_header(staff_ws(sheet_key))
        if q.isdigit():
            rows = [r for r in rows if norm_digits(r.get("MSGV")).endswith(q) or norm_digits(r.get("MSGV")) == q]
        else:
            rows = [r for r in rows if norm_search(q) in norm_search(r.get("Họ và tên"))]
        if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else: st.warning("Không tìm thấy kết quả phù hợp.")

def prepare_log_dataframe(sheet_key):
    logs = get_all_records_by_header(log_ws(sheet_key))
    if not logs: return pd.DataFrame()
    df = pd.DataFrame(logs)
    for c in LOG_COLUMNS:
        if c not in df.columns: df[c] = ""
    df["Ngày_chuẩn"] = df["Ngày"].apply(normalize_date_value)
    df["Ngày_dt"] = df["Ngày"].apply(parse_date_value)
    df["Bộ môn - Đơn vị"] = df.apply(group_bo_mon_don_vi, axis=1)
    df["Vào muộn phút"] = pd.to_numeric(df["Vào muộn phút"], errors="coerce").fillna(0)
    df["Số tiết"] = pd.to_numeric(df["Số tiết"], errors="coerce").fillna(0)
    return df

def current_period_filter(df, mode, selected_date=None):
    if mode == "Theo ngày":
        valid_dates = sorted([d for d in df["Ngày_chuẩn"].dropna().astype(str).unique() if d])
        if selected_date is None:
            selected_date = today_str() if today_str() in valid_dates else (valid_dates[-1] if valid_dates else today_str())
        return df[df["Ngày_chuẩn"] == selected_date].copy(), f"ngày {selected_date}"
    if mode == "Theo tuần hiện hành":
        start, end = current_week_range()
        return df[(df["Ngày_dt"] >= start) & (df["Ngày_dt"] <= end)].copy(), f"tuần ({start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')})"
    if mode == "Theo tháng hiện hành":
        start, end = current_month_range()
        return df[(df["Ngày_dt"] >= start) & (df["Ngày_dt"] <= end)].copy(), f"tháng hiện hành ({start.strftime('%m/%Y')})"
    start, end = academic_year_range()
    return df[(df["Ngày_dt"] >= start) & (df["Ngày_dt"] <= end)].copy(), f"năm học ({start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')})"

def compute_dashboard(filtered):
    if filtered.empty: return {"Tổng GV có log": 0, "Đang trong ca": 0, "Đã ra ca": 0, "Vào muộn > 15 phút": 0, "Tổng tiết phân công": 0}
    total_gv = filtered["MSGV"].nunique()
    out_count = int((filtered["IN/OUT"].astype(str).str.upper() == "OUT").sum())
    in_df = filtered[filtered["IN/OUT"].astype(str).str.upper() == "IN"].copy()
    late_count = int((pd.to_numeric(in_df.get("Vào muộn phút", pd.Series(dtype=float)), errors="coerce").fillna(0) > LATE_THRESHOLD_MINUTES).sum())
    total_lessons = int(pd.to_numeric(in_df.get("Số tiết", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    open_count = 0
    for (msgv, ca), g in filtered.groupby(["MSGV", "Ca"], dropna=False):
        if (g["IN/OUT"].astype(str).str.upper() == "IN").sum() > (g["IN/OUT"].astype(str).str.upper() == "OUT").sum(): open_count += 1
    return {"Tổng GV có log": int(total_gv), "Đang trong ca": int(open_count), "Đã ra ca": out_count, "Vào muộn > 15 phút": late_count, "Tổng tiết phân công": total_lessons}

def build_violation_report(summary):
    rows = []
    if summary is None or summary.empty: return pd.DataFrame()
    for _, r in summary.iterrows():
        row = r.to_dict()
        late = float(pd.to_numeric(pd.Series([r.get("Vào muộn phút", 0)]), errors="coerce").fillna(0).iloc[0])
        if not safe_str(r.get("Vào ca")): rows.append({**row, "Loại vi phạm": "Không vào ca"})
        if safe_str(r.get("Vào ca")) and not safe_str(r.get("Ra ca")): rows.append({**row, "Loại vi phạm": "Không ra ca"})
        if late > LATE_THRESHOLD_MINUTES: rows.append({**row, "Loại vi phạm": f"Vào ca muộn > {LATE_THRESHOLD_MINUTES} phút"})
    return pd.DataFrame(rows)

def render_tab_stats(sheet_key, data_label):
    st.subheader(f"Thống kê điểm danh - {data_label}")
    df = prepare_log_dataframe(sheet_key)
    if df.empty: st.info("Chưa có dữ liệu."); return
    mode = st.radio(f"Chọn phạm vi thống kê ({data_label})", ["Theo ngày", "Theo tuần hiện hành", "Theo tháng hiện hành", "Theo năm học hiện hành"], horizontal=True, key=f"mode_st_{data_label}")
    selected = None
    if mode == "Theo ngày":
        valid_dates = sorted([d for d in df["Ngày_chuẩn"].dropna().astype(str).unique() if d])
        default_idx = valid_dates.index(today_str()) if today_str() in valid_dates else len(valid_dates) - 1
        selected = st.selectbox("Chọn ngày thống kê", valid_dates, index=default_idx if valid_dates else 0, key=f"sel_date_{data_label}")
    
    filtered, title_scope = current_period_filter(df, mode, selected)
    dash = compute_dashboard(filtered)
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Tổng Số Người", dash["Tổng GV có log"])
    c2.metric("Đang trong ca", dash["Đang trong ca"])
    c3.metric("Đã ra ca", dash["Đã ra ca"])
    c4.metric("Vào muộn", dash["Vào muộn > 15 phút"])
    c5.metric("Tổng tiết", dash["Tổng tiết phân công"])

    if not filtered.empty:
        st.dataframe(filtered.drop(columns=["Ngày_dt"], errors="ignore"), use_container_width=True)
        summary = summarize_hours(filtered.to_dict("records"))
        if not summary.empty:
            summary["Bộ môn - Đơn vị"] = summary.apply(group_bo_mon_don_vi, axis=1)
            st.subheader("Bảng tổng hợp chi tiết")
            st.dataframe(summary, use_container_width=True)

def render_tab_dashboard(sheet_key, data_label):
    st.subheader(f"Dashboard tổng hợp - {data_label}")
    df = prepare_log_dataframe(sheet_key)
    if df.empty: st.info("Chưa có dữ liệu điểm danh."); return
    mode = st.radio("Phạm vi dashboard", ["Theo ngày", "Theo tuần hiện hành", "Theo tháng hiện hành", "Theo năm học hiện hành"], horizontal=True, key=f"dash_mode_{data_label}")
    selected = None
    if mode == "Theo ngày":
        valid_dates = sorted([d for d in df["Ngày_chuẩn"].dropna().astype(str).unique() if d])
        default_idx = valid_dates.index(today_str()) if today_str() in valid_dates else len(valid_dates) - 1
        selected = st.selectbox("Chọn ngày hiển thị", valid_dates, index=default_idx if valid_dates else 0, key=f"dash_date_{data_label}")
    
    filtered, title_scope = current_period_filter(df, mode, selected)
    if not filtered.empty:
        dept = filtered.groupby("Bộ môn - Đơn vị", dropna=False).size().reset_index(name="Số lượt log")
        chart = alt.Chart(dept).mark_bar().encode(x=alt.X("Bộ môn - Đơn vị:N", sort="-y"), y="Số lượt log:Q", color="Bộ môn - Đơn vị:N").properties(height=340)
        st.altair_chart(chart, use_container_width=True)

# ===================== ĐIỀU HƯỚNG VÀ PHÂN LUỒNG CHÍNH =====================
qp = get_query_params()

# LUỒNG 1: QUÉT MÃ QR GIẢNG VIÊN (?gv=1)
if qp.get("gv") == "1":
    render_user_attendance("GV", GV_SHEET_KEY)
    st.stop()

# LUỒNG 2: QUÉT MÃ QR SINH VIÊN (?sv=1)
elif qp.get("sv") == "1":
    render_user_attendance("SV", SV_SHEET_KEY)
    st.stop()

# LUỒNG 3: TRANG QUẢN TRỊ TRUNG TÂM (KHÔNG THAM SỐ)
else:
    render_admin_auth()
    st.title("Hệ thống quản lý điểm danh QR tích hợp")

    if not admin_unlocked():
        st.error("Vui lòng đăng nhập quản trị ở thanh điều hướng bên trái để sử dụng hệ thống.")
        st.stop()

    with st.sidebar:
        st.markdown("---")
        st.markdown("**Phân hệ quản lý**")
        target_view = st.selectbox("Đối tượng xem báo cáo:", ["Giảng viên", "Sinh viên"])
        active_sheet_key = GV_SHEET_KEY if target_view == "Giảng viên" else "SV_SHEET_KEY"
        active_sheet_key = GV_SHEET_KEY if target_view == "Giảng viên" else SV_SHEET_KEY

        menu = st.radio(
            "Chọn mục thống kê",
            ["Tạo QR cố định", "Dashboard tổng hợp", "Tìm kiếm thông tin", "Thống kê điểm danh"],
            index=0
        )

    if menu == "Tạo QR cố định":
        render_tab_qr()
    elif menu == "Dashboard tổng hợp":
        render_tab_dashboard(active_sheet_key, target_view)
    elif menu == "Tìm kiếm thông tin":
        render_tab_search(active_sheet_key)
    elif menu == "Thống kê điểm danh":
        render_tab_stats(active_sheet_key, target_view)
