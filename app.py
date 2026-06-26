# app.py
import os
import io
import re
import time
import base64
import urllib.parse
import unicodedata
import datetime
from difflib import get_close_matches

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


# ===================== CẤU HÌNH CƠ SỞ ĐỒNG BỘ =====================
MSGV_PREFIX = st.secrets.get("SESSION_PREFIX", "0607")
GV_SHEET_KEY = st.secrets["GV_SHEET"]
SV_SHEET_KEY = st.secrets["SV_SHEET"]
STAFF_SHEET_NAME = st.secrets.get("STAFF_SHEET_NAME", "NhanSu")
LOG_SHEET_NAME = st.secrets.get("LOG_SHEET_NAME", "Log")

# Cấu hình Phân hệ Sinh viên lớp cố định từ mainsv.py
WORKSHEET_NAME = "D25C"                                     
QR_SLOT_SECONDS = 30          
UNLOCK_TTL = 120              
MSSV_PREFIX = st.secrets.get("SESSION_PREFIX", "51125")  

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

LESSON_MINUTES = int(st.secrets.get("LESSON_MINUTES", 50))
BREAK_AFTER_LESSONS = int(st.secrets.get("BREAK_AFTER_LESSONS", 3))
BREAK_MINUTES = int(st.secrets.get("BREAK_MINUTES", 15))
LATE_THRESHOLD_MINUTES = int(st.secrets.get("LATE_THRESHOLD_MINUTES", 15))

LESSON_SCHEDULE = {
    1: ("07:00", "07:50"), 2: ("07:50", "08:40"), 3: ("08:40", "09:30"),
    4: ("09:45", "10:35"), 5: ("10:35", "11:25"), 7: ("13:00", "13:50"),
    8: ("13:50", "14:40"), 9: ("14:40", "15:30"), 10: ("15:45", "16:35"), 11: ("16:35", "17:25"),
}
MORNING_LESSONS = [1, 2, 3, 4, 5]
AFTERNOON_LESSONS = [7, 8, 9, 10, 11]

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
STAFF_COLUMNS = ["MSGV", "Họ và tên", "Đơn vị", "Bộ môn"]
LOG_COLUMNS = ["Ngày", "MSGV", "Họ và tên", "Đơn vị", "Bộ môn", "CS", "Ca", "Tiết từ", "Tiết đến", "Số tiết", "Giờ bắt đầu phân công", "Giờ kết thúc phân công", "Vào muộn phút", "IN/OUT", "Giờ", "Timestamp"]

LOCATIONS = {
    "Cơ sở 1: 217 Hồng Bàng": {"code": "CS1", "lat": 10.754665, "lon": 106.663381, "radius": 100},
    "Cơ sở 2: 41-43 Đinh Tiên Hoàng": {"code": "CS2", "lat": 10.785434, "lon": 106.702667, "radius": 100}
}
LOCATION_BY_CODE = {v["code"]: k for k, v in LOCATIONS.items()}

st.set_page_config(page_title="Hệ thống điểm danh tích hợp", layout="wide", initial_sidebar_state="expanded")

# ===================== CSS CHỮ TO RÕ THEO PHONG CÁCH CỦA THẦY =====================
st.html(
    """
    <style>
    html, body, .stApp { color: #000000 !important; font-size: 18px !important; }
    .custom-title { font-family: "Times New Roman", Times, serif; font-size: 21px; font-weight: bold; text-align: center; margin-bottom: 15px; color: #1E3A8A; }
    h1, h2, h3 { font-weight: 900 !important; color: #000000 !important; }
    label, p, span, div { color: #000000 !important; }
    input { font-weight: 700 !important; color: #000000 !important; }
    .stButton > button { font-weight: 900 !important; min-height: 3.2rem !important; }
    </style>
    <div class="custom-title">Hệ thống điểm danh</div>
    """
)

# ===================== XỬ LÝ LOGIC CHUNG =====================
def now_vn(): return datetime.datetime.now(VN_TZ)
def today_str(): return now_vn().strftime("%d/%m/%Y")
def timestamp_str(): return now_vn().strftime("%Y-%m-%d %H:%M:%S")
def infer_shift(): return "Sáng" if now_vn().hour < 12 else "Chiều"
def safe_str(value): return str(value or "").strip()
def norm_digits(value): return re.sub(r"\D", "", str(value or ""))
def normalize_name(name: str): return " ".join(w.capitalize() for w in (name or "").strip().split())
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", s)
def norm_search(s: str) -> str: return " ".join(strip_accents(s).lower().split())
def norm_header(s: str) -> str: return norm_search(s).replace(" ", "")
def normalize_date_value(value):
    s = safe_str(value)
    if not s: return ""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m: return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m: return f"{int(m.group(3)):02d}/{int(m.group(2)):02d}/{m.group(1)}"
    return s
def parse_date_value(value):
    s = normalize_date_value(value)
    if not s: return None
    try: return datetime.datetime.strptime(s, "%d/%m/%Y").date()
    except Exception: return None
def attendance_flag(val) -> bool: return safe_str(val) != ""

def _google_api_retry(callable_fn, retries=3, delay=1.2):
    for attempt in range(retries):
        try: return callable_fn()
        except Exception:
            if attempt == retries - 1: raise
            time.sleep(delay * (attempt + 1))

# ===================== KẾT NỐI GOOGLE SHEETS =====================
@st.cache_resource
def get_gspread_client():
    cred = dict(st.secrets["google_service_account"])
    cred["private_key"] = cred.get("private_key", "").replace("\\n", "\n").replace("\r\n", "\n")
    creds = Credentials.from_service_account_info(cred, scopes=SCOPES)
    return gspread.authorize(creds)

def get_spreadsheet(sheet_key):
    return _google_api_retry(lambda: get_gspread_client().open_by_key(sheet_key))

def get_ws_by_title(sheet_key, title, is_log=False):
    ss = get_spreadsheet(sheet_key)
    wanted = norm_search(title).replace(" ", "")
    for ws in _google_api_retry(lambda: ss.worksheets()):
        if norm_search(ws.title).replace(" ", "") == wanted: return ws
    if is_log:
        return _google_api_retry(lambda: ss.add_worksheet(title=title, rows=5000, cols=16))
    return _google_api_retry(lambda: ss.sheet1)

def ensure_header(ws, headers):
    current = _google_api_retry(lambda: ws.row_values(1))
    if not current: _google_api_retry(lambda: ws.update("A1", [headers]))

# ===================== TOKENS QR ĐỘNG =====================
def current_slot(step=QR_SLOT_SECONDS): return int(time.time() // step)
def token_valid(t_str: str, step=QR_SLOT_SECONDS) -> bool:
    if not t_str: return False
    try: return abs(int(str(t_str).strip()) - current_slot(step=step)) <= 1
    except Exception: return False

# ===================== XÁC THỰC GPS =====================
def verify_gps_location(campus_code):
    campus_name = LOCATION_BY_CODE.get(campus_code, "Cơ sở 1: 217 Hồng Bàng")
    campus = LOCATIONS[campus_name]
    if streamlit_geolocation is None or geodesic is None:
        st.error("Thiếu thư viện định vị GPS.")
        return False
    loc = streamlit_geolocation()
    if not loc:
        st.warning("📡 Đang lấy vị trí GPS từ thiết bị... Vui lòng đồng ý cấp quyền truy cập vị trí trên trình duyệt.")
        return False
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        st.warning("Thiết bị không phản hồi tọa độ GPS.")
        return False
    distance = geodesic((float(lat), float(lon)), (campus["lat"], campus["lon"])).meters
    if distance > campus["radius"]:
        st.error(f"❌ Ngoài phạm vi cho phép! Bạn cách tâm cơ sở {round(distance,1)}m (> {campus['radius']}m)")
        return False
    return True

# ===================== NGHIỆP VỤ GIẢNG VIÊN =====================
def find_staff_by_msgv(sheet_key, code_input):
    ws = get_ws_by_title(sheet_key, STAFF_SHEET_NAME)
    values = _google_api_retry(lambda: ws.get_all_values())
    if not values or len(values) < 2: return None
    headers = values[0]
    hn = [norm_header(h) for h in headers]
    msgv_i = hn.index("msgv") if "msgv" in hn else 0
    name_i = hn.index("hovaten") if "hovaten" in hn else 1
    unit_i = hn.index("donvi") if "donvi" in hn else 2
    dept_i = hn.index("bomon") if "bomon" in hn else 3
    
    target = norm_digits(code_input)
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

def lesson_range_info(shift, lesson_from, lesson_to):
    allowed = MORNING_LESSONS if shift == "Sáng" else AFTERNOON_LESSONS
    lf, lt = int(lesson_from), int(lesson_to)
    if lf not in allowed: lf = allowed[0]
    if lt not in allowed: lt = allowed[-1]
    if lt < lf: lt = lf
    selected = [x for x in allowed if lf <= x <= lt]
    return {
        "lesson_from": selected[0], "lesson_to": selected[-1], "num_lessons": len(selected),
        "start_time": LESSON_SCHEDULE[selected[0]][0], "end_time": LESSON_SCHEDULE[selected[-1]][1]
    }

# ===================== MÀN HÌNH 1: GV ĐIỂM DANH (?gv=1) =====================
def render_gv_attendance_flow():
    campus_code = st.query_params.get("coso", "CS1")
    st.title("👨‍🏫 Điểm danh Giảng viên")
    if now_vn().date().weekday() == 6:
        st.error("Chủ nhật không hỗ trợ điểm danh.")
        st.stop()
        
    if not verify_gps_location(campus_code): st.stop()
    shift = infer_shift()
    st.info(f"Ca hiện tại: Buổi {shift}")
    
    action_label = st.radio("Chọn hình thức", ["Vào ca", "Ra ca"], horizontal=True)
    action = "IN" if action_label == "Vào ca" else "OUT"
    
    allowed = MORNING_LESSONS if shift == "Sáng" else AFTERNOON_LESSONS
    c1, c2 = st.columns(2)
    with c1: tiet_tu = st.number_input("Từ tiết", min_value=min(allowed), max_value=max(allowed), value=min(allowed))
    with c2: tiet_den = st.number_input("Đến tiết", min_value=min(allowed), max_value=max(allowed), value=max(allowed))
    
    info_tiet = lesson_range_info(shift, tiet_tu, tiet_den)
    st.caption(f"Khung giờ: Tiết {info_tiet['lesson_from']}-{info_tiet['lesson_to']} ({info_tiet['start_time']}-{info_tiet['end_time']})")
    
    msgv_suffix = st.text_input("Nhập 4 số cuối MSGV", max_chars=4, placeholder="VD: 1234")
    
    if st.button("Xác nhận điểm danh Giảng viên", type="primary", use_container_width=True):
        if len(msgv_suffix.strip()) != 4 or not msgv_suffix.isdigit():
            st.warning("Vui lòng nhập đúng 4 chữ số cuối MSGV.")
            st.stop()
            
        staff = find_staff_by_msgv(GV_SHEET_KEY, msgv_suffix)
        if not staff: st.error("Không tìm thấy Giảng viên."); st.stop()
        if staff.get("ambiguous"): st.error("Mã số trùng lặp, liên hệ Admin."); st.stop()
        
        msgv_full = staff["MSGV"]
        lw = get_ws_by_title(GV_SHEET_KEY, LOG_SHEET_NAME, is_log=True)
        ensure_header(lw, LOG_COLUMNS)
        
        start_t = datetime.datetime.strptime(info_tiet["start_time"], "%H:%M").time()
        start_dt = datetime.datetime.combine(now_vn().date(), start_t, tzinfo=VN_TZ)
        late_min = max(0, int((now_vn() - start_dt).total_seconds() // 60)) if action == "IN" else 0
        
        _google_api_retry(lambda: lw.append_row([
            today_str(), msgv_full, staff["Họ và tên"], staff["Đơn vị"], staff["Bộ môn"],
            campus_code, shift, info_tiet["lesson_from"], info_tiet["lesson_to"], info_tiet["num_lessons"],
            info_tiet["start_time"], info_tiet["end_time"], late_min if action == "IN" else "", action,
            now_vn().strftime("%H:%M:%S"), timestamp_str()
        ], value_input_option="USER_ENTERED"))
        st.success(f"🎉 Điểm danh {action_label} thành công: {staff['Họ và tên']} ({msgv_full})")

# ===================== MÀN HÌNH 2: SV ĐIỂM DANH QR ĐỘNG + GPS (?sv=1) =====================
def find_or_create_time_col(sheet, buoi_col: int, buoi_header: str) -> int:
    headers = _google_api_retry(lambda: sheet.row_values(1))
    nxt = buoi_col + 1
    if nxt <= len(headers) and "thời gian" in (headers[nxt-1] or "").lower(): return nxt
    _google_api_retry(lambda: sheet.update_cell(1, nxt, f"Thời gian {buoi_header}"))
    return nxt

def render_sv_attendance_flow():
    qp = st.query_params
    buoi_sv = qp.get("buoi", "Buổi 1")
    token_qr = qp.get("t", "")
    campus_code = qp.get("coso", "CS1")
    
    st.title("🎓 Điểm danh Sinh viên lớp D25C")
    st.info(f"Phiên học ghi nhận: **{buoi_sv}**")
    
    if not verify_gps_location(campus_code): st.stop()
    
    lock_key = f"sv_lock_{buoi_sv}"
    if st.session_state.get(lock_key):
        st.success("✅ Bạn đã điểm danh thành công trên thiết bị này.")
        st.stop()
        
    unlock_key = f"sv_active_{buoi_sv}"
    if not st.session_state.get(unlock_key):
        if not token_valid(token_qr, step=QR_SLOT_SECONDS):
            st.error("⏳ Mã QR đã hết hạn. Vui lòng quét lại mã mới đang hiển thị trên bảng.")
            st.stop()
        st.session_state[unlock_key] = time.time()
    else:
        if time.time() - st.session_state[unlock_key] > UNLOCK_TTL:
            st.error("❌ Phiên làm việc quá hạn. Vui lòng quét lại mã mới.")
            st.stop()
            
    mssv_suffix = st.text_input("Nhập 4 số cuối MSSV", max_chars=4, placeholder="VD: 1234")
    hoten = st.text_input("Nhập đầy đủ Họ và Tên sinh viên (Có dấu)")
    
    if mssv_suffix.strip().isdigit():
        st.caption(f"MSSV đối chiếu: **{MSSV_PREFIX}{mssv_suffix.strip().zfill(4)}**")
        
    if st.button("✅ Xác nhận điểm danh Sinh viên", type="primary", use_container_width=True):
        if not mssv_suffix.strip().isdigit() or len(mssv_suffix.strip()) != 4 or not hoten.strip():
            st.warning("Vui lòng điền đầy đủ thông tin.")
            st.stop()
            
        full_mssv = f"{MSSV_PREFIX}{mssv_suffix.strip().zfill(4)}"
        sheet = get_ws_by_title(SV_SHEET_KEY, WORKSHEET_NAME)
        
        records = _google_api_retry(lambda: sheet.get_all_records(default_blank=""))
        target_row = None
        for idx, r in enumerate(records, start=2):
            if norm_digits(r.get("MSSV", "")) == norm_digits(full_mssv):
                target_row = idx
                break
                
        if not target_row:
            st.error(f"❌ Không tìm thấy mã MSSV {full_mssv} trong danh sách lớp.")
            st.stop()
            
        headers = _google_api_retry(lambda: sheet.row_values(1))
        hn = [norm_header(h) for h in headers]
        name_col = (hn.index("hovaten") + 1) if "hovaten" in hn else 2
        hoten_sheet = sheet.cell(target_row, name_col).value
        
        if normalize_name(hoten_sheet or "") != normalize_name(hoten):
            st.error("❌ Họ tên không khớp với dữ liệu gốc của mã số này.")
            st.stop()
            
        buoi_col = (hn.index(norm_header(buoi_sv)) + 1) if norm_header(buoi_sv) in hn else 4
        time_col = find_or_create_time_col(sheet, buoi_col, buoi_sv)
        
        _google_api_retry(lambda: sheet.update_cell(target_row, buoi_col, "✅"))
        _google_api_retry(lambda: sheet.update_cell(target_row, time_col, timestamp_str()))
        
        st.session_state[lock_key] = True
        st.success(f"🎉 Điểm danh thành công sinh viên: {hoten_sheet} ({full_mssv})")
        st.rerun()

# ===================== MÀN HÌNH 3: QUẢN TRỊ TRUNG TÂM GỐC =====================
def get_base_url():
    return st.secrets.get("WRAPPER_URL") or st.secrets.get("APP_BASE_URL") or "https://giangvien.streamlit.app"

def get_admin_pw(): return st.secrets.get("ADMIN_PASSWORD", "admin")
def admin_unlocked(): return bool(st.session_state.get("admin_unlocked"))

def get_all_records_by_header(ws):
    values = _google_api_retry(lambda: ws.get_all_values())
    if not values: return []
    headers = values[0]
    out = []
    for row in values[1:]:
        item = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
        if any(str(v).strip() for v in item.values()): out.append(item)
    return out

def group_bo_mon_don_vi(row):
    bo_mon = safe_str(row.get("Bộ môn"))
    don_vi = safe_str(row.get("Đơn vị"))
    return bo_mon if bo_mon else (don_vi if don_vi else "Chưa xác định")

def prepare_log_dataframe(sheet_key):
    ws = get_ws_by_title(sheet_key, LOG_SHEET_NAME, is_log=True)
    logs = get_all_records_by_header(ws)
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
        today = now_vn().date()
        start = today - datetime.timedelta(days=today.weekday())
        end = start + datetime.timedelta(days=6)
        return df[(df["Ngày_dt"] >= start) & (df["Ngày_dt"] <= end)].copy(), f"tuần ({start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')})"
    if mode == "Theo tháng hiện hành":
        today = now_vn().date()
        start = today.replace(day=1)
        if today.month == 12: end = today.replace(year=today.year+1, month=1, day=1) - datetime.timedelta(days=1)
        else: end = today.replace(month=today.month+1, day=1) - datetime.timedelta(days=1)
        return df[(df["Ngày_dt"] >= start) & (df["Days_dt"] <= end)].copy(), f"tháng hiện hành ({start.strftime('%m/%Y')})"
    # Năm học
    today = now_vn().date()
    s_yr = today.year if today >= datetime.date(today.year, 7, 1) else today.year - 1
    start, end = datetime.date(s_yr, 7, 1), datetime.date(s_yr + 1, 8, 31)
    return df[(df["Keep_dt"] >= start) & (df["Ngày_dt"] <= end)].copy(), f"năm học ({start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')})"

def compute_dashboard(filtered):
    if filtered.empty: return {"Tổng số người": 0, "Đang trong ca": 0, "Đã ra ca": 0, "Vào muộn": 0, "Tổng tiết": 0}
    total_p = filtered["MSGV"].nunique()
    out_count = int((filtered["IN/OUT"].astype(str).str.upper() == "OUT").sum())
    in_df = filtered[filtered["IN/OUT"].astype(str).str.upper() == "IN"].copy()
    late_count = int((pd.to_numeric(in_df.get("Vào muộn phút", pd.Series(dtype=float)), errors="coerce").fillna(0) > LATE_THRESHOLD_MINUTES).sum())
    total_lessons = int(pd.to_numeric(in_df.get("Số tiết", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    open_count = 0
    for (msgv, ca), g in filtered.groupby(["MSGV", "Ca"], dropna=False):
        if (g["IN/OUT"].astype(str).str.upper() == "IN").sum() > (g["IN/OUT"].astype(str).str.upper() == "OUT").sum(): open_count += 1
    return {"Tổng số người": int(total_p), "Đang trong ca": int(open_count), "Đã ra ca": out_count, "Vào muộn": late_count, "Tổng tiết": total_lessons}

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

# --- KHU VỰC RENDER GIAO DIỆN ADMIN CHÍNH ---
def render_admin_dashboard_flow():
    with st.sidebar:
        st.header("🔒 Đăng nhập Admin")
        if admin_unlocked():
            st.success("Đã đăng nhập quản trị")
            if st.button("Đăng xuất Admin"): st.session_state.clear(); st.rerun()
        else:
            pw = st.text_input("Mật khẩu quản trị", type="password")
            if st.button("Xác nhận đăng nhập", type="primary", use_container_width=True):
                if pw == get_admin_pw():
                    st.session_state["admin_unlocked"] = True
                    st.rerun()
                else: st.warning("Sai mật khẩu.")
                
    if not admin_unlocked():
        st.error("Vui lòng đăng nhập quản trị ở thanh điều hướng bên trái để sử dụng các chức năng quản lý.")
        st.stop()
        
    with st.sidebar:
        st.markdown("---")
        st.markdown("**Phân hệ quản lý**")
        target_view = st.selectbox("Đối tượng xem báo cáo:", ["Giảng viên", "Sinh viên"])
        active_sheet_key = GV_SHEET_KEY if target_view == "Giảng viên" else SV_SHEET_KEY
        
        menu = st.radio(
            "Chọn mục quản lý:",
            ["Tạo QR cố định (GV)", "Sinh viên (QR động 30s)", "Dashboard tổng hợp", "Tìm kiếm thông tin", "Thống kê điểm danh"],
            index=0
        )

    # 1. Tạo QR cố định cho GV
    if menu == "Tạo QR cố định (GV)":
        st.subheader("Tạo QR cố định theo cơ sở cho Giảng viên")
        campus_name = st.selectbox("Chọn cơ sở", list(LOCATIONS.keys()))
        campus_code = LOCATIONS[campus_name]["code"]
        if st.button("Tạo QR cố định", type="primary", use_container_width=True):
            qr_data = f"{get_base_url()}/?gv=1&coso={urllib.parse.quote(campus_code)}"
            qr = qrcode.make(qr_data)
            buf = io.BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
            st.image(Image.open(buf), caption=f"QR Giảng viên tại {campus_code}", width=380)
            st.code(qr_data)
            
    # 2. Tạo QR động 30s cho Sinh viên (Nguyên bản của thầy từ mainsv.py)
    elif menu == "Sinh viên (QR động 30s)":
        st.subheader(f"📸 Trình chiếu Mã QR Điểm danh Động lớp {WORKSHEET_NAME}")
        buoi = st.selectbox("Chọn buổi học", ["Buổi 1", "Buổi 2", "Buổi 3", "Buổi 4", "Buổi 5", "Buổi 6"])
        campus_name = st.selectbox("Lớp đang học tại cơ sở nào? (Để ép GPS SV)", list(LOCATIONS.keys()))
        campus_code = LOCATIONS[campus_name]["code"]
        auto = st.toggle("Tự đổi QR mỗi 30 giây", value=True)
        
        if st.button("Bắt đầu trình chiếu QR lớp học", type="primary", use_container_width=True):
            qr_slot = st.empty()
            timer_slot = st.empty()
            while True:
                slot = current_slot()
                qr_data = f"{get_base_url()}/?sv=1&buoi={urllib.parse.quote(buoi)}&t={slot}&coso={campus_code}"
                qr = qrcode.make(qr_data)
                buf = io.BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
                qr_slot.image(Image.open(buf), caption="📱 Sinh viên ngồi tại lớp quét mã QR đang chiếu này", width=360)
                remain = QR_SLOT_SECONDS - (int(time.time()) % QR_SLOT_SECONDS)
                timer_slot.markdown(f"⏳ **Mã QR tự động đổi sau:** `{remain} giây`  •  **Phiên:** `{buoi}`  •  **Ép định vị:** `{campus_code}`")
                if not auto: break
                time.sleep(1)

    # 3. Dashboard tổng hợp đồ họa
    elif menu == "Dashboard tổng hợp":
        st.subheader(f"Dashboard tổng hợp - {target_view}")
        df = prepare_log_dataframe(active_sheet_key)
        if df.empty: st.info("Chưa có nhật ký điểm danh."); return
        mode = st.radio("Phạm vi dashboard", ["Theo ngày", "Theo tuần hiện hành", "Theo tháng hiện hành"], horizontal=True, key="db_m")
        filtered, scope = current_period_filter(df, mode)
        if not filtered.empty:
            dept = filtered.groupby("Bộ môn - Đơn vị", dropna=False).size().reset_index(name="Số lượt log")
            chart = alt.Chart(dept).mark_bar().encode(x=alt.X("Bộ môn - Đơn vị:N", sort="-y"), y="Số lượt log:Q", color="Bộ môn - Đơn vị:N").properties(height=340)
            st.altair_chart(chart, use_container_width=True)

    # 4. Tra cứu tìm kiếm
    elif menu == "Tìm kiếm thông tin":
        st.subheader(f"Tìm kiếm thông tin {target_view}")
        q = st.text_input("Nhập 4 số cuối, đầy đủ mã số hoặc họ tên")
        if st.button("Tìm kiếm", use_container_width=True):
            ws = get_ws_by_title(active_sheet_key, STAFF_SHEET_NAME)
            rows = get_all_records_by_header(ws)
            if q.isdigit(): rows = [r for r in rows if norm_digits(r.get("MSGV")).endswith(q) or norm_digits(r.get("MSGV")) == q]
            else: rows = [r for r in rows if norm_search(q) in norm_search(r.get("Họ và tên"))]
            if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True)
            else: st.warning("Không tìm thấy kết quả phù hợp.")

    # 5. Thống kê chi tiết & báo cáo vi phạm
    elif menu == "Thống kê điểm danh":
        st.subheader(f"Thống kê điểm danh chi tiết - {target_view}")
        df = prepare_log_dataframe(active_sheet_key)
        if df.empty: st.info("Chưa có dữ liệu."); return
        mode = st.radio("Phạm vi thống kê", ["Theo ngày", "Theo tuần hiện hành", "Theo tháng hiện hành"], horizontal=True, key="st_m")
        selected = None
        if mode == "Theo ngày":
            valid_dates = sorted([d for d in df["Ngày_chuẩn"].dropna().astype(str).unique() if d])
            default_idx = valid_dates.index(today_str()) if today_str() in valid_dates else len(valid_dates) - 1
            selected = st.selectbox("Chọn ngày", valid_dates, index=default_idx if valid_dates else 0)
        
        filtered, scope = current_period_filter(df, mode, selected)
        dash = compute_dashboard(filtered)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Tổng có log", dash["Tổng số người"])
        c2.metric("Đang trong ca", dash["Đang trong ca"])
        c3.metric("Đã ra ca", dash["Đã ra ca"])
        c4.metric("Vào muộn (>15p)", dash["Vào muộn"])
        c5.metric("Tổng tiết dạy", dash["Tổng tiết"])

        if not filtered.empty:
            st.write("### Nhật ký danh sách Log")
            st.dataframe(filtered.drop(columns=["Ngày_dt"], errors="ignore"), use_container_width=True)
            summary = summarize_hours(filtered.to_dict("records"))
            if not summary.empty:
                st.write("### Bảng tổng hợp giờ có mặt thực tế")
                st.dataframe(summary, use_container_width=True)
                st.write("### Báo cáo vi phạm quy định giờ giấc")
                v_rep = build_violation_report(summary)
                if v_rep.empty: st.success("Không phát hiện vi phạm.")
                else: st.dataframe(v_rep, use_container_width=True)

# ===================== PHÂN LUỒNG URL CHÍNH (ROUTING CHUẨN) =====================
# Sửa lỗi so khớp kiểu dữ liệu chuỗi thô của query_params bằng cách đưa về hàm ép kiểu chuỗi
if "gv" in st.query_params and str(st.query_params["gv"]) == "1":
    render_gv_attendance_flow()
elif "sv" in st.query_params and str(st.query_params["sv"]) == "1":
    render_sv_attendance_flow()
else:
    render_admin_dashboard_flow()

# ===================== FOOTER CHÂN TRANG BẢN QUYỀN =====================
st.markdown(
    """
    <style>
    .footer-dhn { position: fixed; left: 0; right: 0; bottom: 0; padding: 6px; background: #F3F4F6; 
                 color: #374151; font-size: 13px; text-align: center; z-index: 9999; border-top: 1px solid #E5E7EB; }
    </style>
    <div class="footer-dhn">Copyright © 2026 Bản quyền thuộc về <strong>TS. Đào Hồng Nam - Đại học Y Dược Thành phố Hồ Chí Minh</strong></div>
    """,
    unsafe_allow_html=True
)
