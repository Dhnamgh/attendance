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


# ===================== CẤU HÌNH HỆ THỐNG ĐỒNG BỘ =====================
GV_SHEET_KEY = st.secrets["GV_SHEET"]
SV_SHEET_KEY = st.secrets["SV_SHEET"]

# Tên sheet danh sách gốc (Cơ sở dữ liệu danh sách lớp)
STAFF_SHEET_NAME = st.secrets.get("STAFF_SHEET_NAME", "NhanSu") 
STUDENT_SHEET_NAME = "D26A"                                     # Đã ghim cố định lớp D26A của thầy
LOG_SHEET_NAME = st.secrets.get("LOG_SHEET_NAME", "Log")

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# Quy định khung giờ tiết học dùng chung (1 tiết = 50 phút, giải lao 15 phút sau tiết 3)
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

# Định dạng các cột trên file Google Sheet đồng bộ 100% theo đúng biểu mẫu nhật ký (Log) của thầy
LOG_COLUMNS = [
    "Ngày", "MSGV", "Họ và tên", "Đơn vị", "Bộ môn", 
    "CS", "Ca", "IN/OUT", "Giờ", "Timestamp", 
    "Số tiết", "Tiết từ", "Tiết đến", "Giờ bắt đầu phân công", "Giờ kết thúc phân công", "Vào muộn phút"
]

LOCATIONS = {
    "Cơ sở 1: 217 Hồng Bàng": {"code": "CS1", "lat": 10.754665, "lon": 106.663381, "radius": 100},
    "Cơ sở 2: 41-43 Đinh Tiên Hoàng": {"code": "CS2", "lat": 10.785434, "lon": 106.702667, "radius": 100}
}
LOCATION_BY_CODE = {v["code"]: k for k, v in LOCATIONS.items()}

st.set_page_config(page_title="Hệ thống điểm danh tích hợp", layout="wide", initial_sidebar_state="expanded")

# ===================== CSS GIAO DIỆN CHỮ TO RÕ THEO PHONG CÁCH CỦA THẦY =====================
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

# ===================== TIỆN ÍCH CHUNG =====================
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

# ===================== XÁC THỰC GPS ĐỊNH VỊ VỆ TINH =====================
def verify_gps_location(campus_code):
    campus_name = LOCATION_BY_CODE.get(campus_code, "Cơ sở 1: 217 Hồng Bàng")
    campus = LOCATIONS[campus_name]
    if streamlit_geolocation is None or geodesic is None:
        st.error("Thiếu thư viện định vị GPS.")
        return False
    loc = streamlit_geolocation()
    if not loc:
        st.warning("📡 Đang kết nối dữ liệu GPS... Vui lòng đồng ý cấp quyền vị trí trên trình duyệt thiết bị.")
        return False
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        st.warning("Thiết bị chưa phản hồi tọa độ GPS thực tế.")
        return False
    distance = geodesic((float(lat), float(lon)), (campus["lat"], campus["lon"])).meters
    if distance > campus["radius"]:
        st.error(f"❌ Ngoài phạm vi cho phép! Khoảng cách hiện tại của bạn: {round(distance,1)}m (> {campus['radius']}m)")
        return False
    return True

# ===================== TRA CỨU TÀI KHOẢN TỪ DANH SÁCH GỐC =====================
def find_user_by_code(user_type, sheet_key, code_input):
    target_sheet = STAFF_SHEET_NAME if user_type == "GV" else STUDENT_SHEET_NAME
    ws = get_ws_by_title(sheet_key, target_sheet)
    values = _google_api_retry(lambda: ws.get_all_values())
    if not values or len(values) < 2: return None
    headers = values[0]
    hn = [norm_header(h) for h in headers]
    
    msgv_i = hn.index("msgv") if "msgv" in hn else (hn.index("mssv") if "mssv" in hn else 0)
    name_i = hn.index("hovaten") if "hovaten" in hn else 1
    unit_i = hn.index("donvi") if "donvi" in hn else -1
    dept_i = hn.index("bomon") if "bomon" in hn else -1
    
    target = norm_digits(code_input)
    matches = []
    for row in values[1:]:
        raw_digits = norm_digits(row[msgv_i] if msgv_i < len(row) else "")
        if not raw_digits: continue
        if (len(target) == 4 and raw_digits.endswith(target)) or raw_digits == target:
            matches.append({
                "MÃ": raw_digits,
                "Họ và tên": row[name_i] if name_i < len(row) else "",
                "Đơn vị": row[unit_i] if (unit_i != -1 and unit_i < len(row)) else ("Khoa Khoa học cơ bản" if user_type == "SV" else "Chưa rõ"),
                "Bộ môn": row[dept_i] if (dept_i != -1 and dept_i < len(row)) else (f"Lớp {STUDENT_SHEET_NAME}" if user_type == "SV" else "Chưa rõ"),
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

# ===================== LUỒNG GIAO DIỆN ĐIỂM DANH ĐỒNG BỘ (GV & SV) =====================
def render_attendance_flow(user_type, sheet_key):
    campus_code = st.query_params.get("coso", "CS1")
    
    st.title(f"Hệ thống điểm danh {user_type}")
    if now_vn().date().weekday() == 6:
        st.error("Chủ nhật hệ thống không hỗ trợ ghi nhận điểm danh.")
        st.stop()
        
    if not verify_gps_location(campus_code): st.stop()
    
    shift = infer_shift()
    st.info(f"Khung buổi hiện hành: Ca {shift}")
    
    action_label = st.radio("Chọn nghiệp vụ điểm danh", ["Vào ca", "Ra ca"], horizontal=True, key=f"act_{user_type}")
    action = "IN" if action_label == "Vào ca" else "OUT"
    
    allowed = MORNING_LESSONS if shift == "Sáng" else AFTERNOON_LESSONS
    c1, c2 = st.columns(2)
    with c1: tiet_tu = st.number_input("Tiết bắt đầu", min_value=min(allowed), max_value=max(allowed), value=min(allowed), key=f"f_{user_type}")
    with c2: tiet_den = st.number_input("Tiết kết thúc", min_value=min(allowed), max_value=max(allowed), value=max(allowed), key=f"t_{user_type}")
    
    info_tiet = lesson_range_info(shift, tiet_tu, tiet_den)
    st.caption(f"Khung giờ chuẩn: Tiết {info_tiet['lesson_from']} -> {info_tiet['lesson_to']} ({info_tiet['start_time']} - {info_tiet['end_time']})")
    
    label_text = "Nhập 4 số cuối MSGV" if user_type == "GV" else "Nhập 4 số cuối MSSV"
    code_suffix = st.text_input(label_text, max_chars=4, placeholder="Ví dụ: 1234", key=f"code_{user_type}")
    
    if st.button("Xác nhận điểm danh", type="primary", use_container_width=True, key=f"btn_{user_type}"):
        if len(code_suffix.strip()) != 4 or not code_suffix.isdigit():
            st.warning("Yêu cầu nhập chính xác 4 chữ số cuối mã số định danh.")
            st.stop()
            
        user_info = find_user_by_code(user_type, sheet_key, code_suffix)
        if not user_info: st.error(f"Không tìm thấy dữ liệu {user_type} trên hệ thống danh sách gốc."); st.stop()
        if user_info.get("ambiguous"): st.error("Mã số trùng khớp nhiều người, vui lòng báo Giáo vụ."); st.stop()
        
        user_code_full = user_info["MÃ"]
        lw = get_ws_by_title(sheet_key, LOG_SHEET_NAME, is_log=True)
        ensure_header(lw, LOG_COLUMNS)
        
        start_t = datetime.datetime.strptime(info_tiet["start_time"], "%H:%M").time()
        start_dt = datetime.datetime.combine(now_vn().date(), start_t, tzinfo=VN_TZ)
        late_min = max(0, int((now_vn() - start_dt).total_seconds() // 60)) if action == "IN" else 0
        
        if action == "OUT":
            end_t = datetime.datetime.strptime(info_tiet["end_time"], "%H:%M").time()
            if now_vn().time() < end_t:
                st.error(f"❌ Chưa đến thời điểm ra ca! Khung giờ kết thúc quy định là {info_tiet['end_time']}.")
                st.stop()
                
        _google_api_retry(lambda: lw.append_row([
            today_str(), user_code_full, user_info["Họ và tên"], user_info["Đơn vị"], user_info["Bộ môn"],
            campus_code, shift, action, now_vn().strftime("%H:%M:%S"), timestamp_str(),
            info_tiet["num_lessons"], info_tiet["lesson_from"], info_tiet["lesson_to"],
            info_tiet["start_time"], info_tiet["end_time"], late_min if action == "IN" else ""
        ], value_input_option="USER_ENTERED"))
        
        st.success(f"🎉 Điểm danh thành công! {user_type}: {user_info['Họ và tên']} ({user_code_full})")

# ===================== GIAO DIỆN QUẢN TRỊ TRUNG TÂM ADMIN FULL TÍNH NĂNG =====================
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
    today = now_vn().date()
    start = today.replace(day=1)
    if today.month == 12: end = today.replace(year=today.year+1, month=1, day=1) - datetime.timedelta(days=1)
    else: end = today.replace(month=today.month+1, day=1) - datetime.timedelta(days=1)
    return df[(df["Ngày_dt"] >= start) & (df["Ngày_dt"] <= end)].copy(), f"tháng hiện hành ({start.strftime('%m/%Y')})"

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

def render_admin_dashboard_flow():
    with st.sidebar:
        st.header("🔒 Đăng nhập Admin")
        if admin_unlocked():
            st.success("Đã đăng nhập thành công")
            if st.button("Đăng xuất Admin"): st.session_state.clear(); st.rerun()
        else:
            pw = st.text_input("Mật khẩu quản trị", type="password")
            if st.button("Xác nhận đăng nhập", type="primary", use_container_width=True):
                if pw == get_admin_pw():
                    st.session_state["admin_unlocked"] = True
                    st.rerun()
                else: st.warning("Sai mật khẩu.")
                
    if not admin_unlocked():
        st.error("Vui lòng đăng nhập mật khẩu quản trị ở sidebar bên trái để truy cập.")
        st.stop()
        
    with st.sidebar:
        st.markdown("---")
        target_view = st.selectbox("Chọn phân hệ đối tượng báo cáo:", ["Giảng viên", "Sinh viên"])
        active_sheet_key = GV_SHEET_KEY if target_view == "Giảng viên" else SV_SHEET_KEY
        target_sheet = STAFF_SHEET_NAME if target_view == "Giảng viên" else STUDENT_SHEET_NAME
        param_flag = "gv=1" if target_view == "Giảng viên" else "sv=1"
        
        menu = st.radio(
            "Chọn mục quản lý:",
            ["Tạo QR cố định theo Cơ sở", "Dashboard tổng hợp", "Tìm kiếm thông tin", "Thống kê điểm danh"],
            index=0
        )

    if menu == "Tạo QR cố định theo Cơ sở":
        st.subheader(f"Tạo QR Code điểm danh cố định — Phân hệ {target_view}")
        campus_name = st.selectbox("Chọn vị trí cơ sở trường học", list(LOCATIONS.keys()))
        campus_code = LOCATIONS[campus_name]["code"]
        
        # ĐƯỢC CẢI TIẾN: Thay vì dùng hàm get_base_url(), bốc trực tiếp URL thực tế mà Admin đang mở trên trình duyệt
        try:
            current_url = st.to_url() if hasattr(st, "to_url") else ""
            if "localhost" in current_url or not current_url:
                base_url = get_base_url().strip("/")
            else:
                base_url = current_url.split("?")[0].strip("/")
        except Exception:
            base_url = get_base_url().strip("/")

        if st.button("Khởi tạo mã QR", type="primary", use_container_width=True):
            qr_data = f"{base_url}/?{param_flag}&coso={urllib.parse.quote(campus_code)}"
            qr = qrcode.make(qr_data)
            buf = io.BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
            st.image(Image.open(buf), caption=f"Mã QR cố định ({target_view}) tại {campus_code}", width=380)
            st.code(qr_data)
            
    elif menu == "Dashboard tổng hợp":
        st.subheader(f"Dashboard tổng hợp biểu đồ — Phân hệ {target_view}")
        df = prepare_log_dataframe(active_sheet_key)
        if df.empty: st.info("Chưa có nhật ký điểm danh."); return
        mode = st.radio("Phạm vi dashboard", ["Theo ngày", "Theo tuần hiện hành", "Theo tháng hiện hành"], horizontal=True, key="db_m")
        filtered, scope = current_period_filter(df, mode)
        if not filtered.empty:
            dept = filtered.groupby("Bộ môn - Đơn vị", dropna=False).size().reset_index(name="Số lượt log")
            chart = alt.Chart(dept).mark_bar().encode(x=alt.X("Bộ môn - Đơn vị:N", sort="-y"), y="Số lượt log:Q", color="Bộ môn - Đơn vị:N").properties(height=340)
            st.altair_chart(chart, use_container_width=True)

    elif menu == "Tìm kiếm thông tin":
        st.subheader(f"Tra cứu thông tin danh sách gốc ({target_sheet}) — Phân hệ {target_view}")
        q = st.text_input("Nhập 4 số cuối, đầy đủ mã số hoặc họ tên:")
        if st.button("Bắt đầu tìm kiếm", use_container_width=True):
            ws = get_ws_by_title(active_sheet_key, target_sheet)
            rows = get_all_records_by_header(ws)
            if rows:
                col_code = list(rows[0].keys())[0]
                if q.isdigit(): rows = [r for r in rows if norm_digits(r.get(col_code)).endswith(q) or norm_digits(r.get(col_code)) == q]
                else: rows = [r for r in rows if norm_search(q) in norm_search(r.get("Họ và tên"))]
                if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True)
                else: st.warning("Không tìm thấy kết quả phù hợp.")
            else: st.info("Bảng danh sách trống.")

    elif menu == "Thống kê điểm danh":
        st.subheader(f"Thống kê điểm danh & Phân tích vi phạm — Phân hệ {target_view}")
        df = prepare_log_dataframe(active_sheet_key)
        if df.empty: st.info("Chưa có nhật ký dữ liệu."); return
        mode = st.radio("Phạm vi thống kê", ["Theo ngày", "Theo tuần hiện hành", "Theo tháng hiện hành"], horizontal=True, key="st_m")
        selected = None
        if mode == "Theo ngày":
            valid_dates = sorted([d for d in df["Ngày_chuẩn"].dropna().astype(str).unique() if d])
            default_idx = valid_dates.index(today_str()) if today_str() in valid_dates else len(valid_dates) - 1
            selected = st.selectbox("Chọn ngày hiển thị", valid_dates, index=default_idx if valid_dates else 0)
        
        filtered, scope = current_period_filter(df, mode, selected)
        dash = compute_dashboard(filtered)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Tổng có mặt", dash["Tổng số người"])
        c2.metric("Đang trong ca", dash["Đang trong ca"])
        c3.metric("Đã ra ca", dash["Đã ra ca"])
        c4.metric("Vào muộn (>15p)", dash["Vào muộn"])
        c5.metric("Tổng tiết phân công", dash["Tổng tiết"])

        if not filtered.empty:
            st.write("### 1. Chi tiết Nhật ký Log ghi nhận")
            st.dataframe(filtered.drop(columns=["Ngày_dt"], errors="ignore"), use_container_width=True)
            summary = summarize_hours(filtered.to_dict("records"))
            if not summary.empty:
                st.write("### 2. Bảng tổng hợp tổng số giờ có mặt")
                st.dataframe(summary, use_container_width=True)
                st.write("### 3. Báo cáo các trường hợp vi phạm giờ quy định")
                v_rep = build_violation_report(summary)
                if v_rep.empty: st.success("Ghi nhận: Không có vi phạm trong phạm vi lọc.")
                else: st.dataframe(v_rep, use_container_width=True)

# ===================== PHÂN LUỒNG URL CHÍNH (ĐỒNG BỘ ĐỊA CHỈ THỰC TẾ) =====================
# Sử dụng phương thức kiểm tra gián tiếp chuỗi thô từ query_params để ép luồng chạy chính xác
query_keys = [str(k).lower() for k in st.query_params.keys()]

if "gv" in query_keys:
    render_attendance_flow("GV", GV_SHEET_KEY)
elif "sv" in query_keys:
    render_attendance_flow("SV", SV_SHEET_KEY)
else:
    render_admin_dashboard_flow()

# ===================== FOOTER CHÂN TRANG BẢN QUYỀN ĐỒNG BỘ CỦA THẦY =====================
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
