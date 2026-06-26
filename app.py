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
STAFF_SHEET_NAME = st.secrets.get("STAFF_SHEET_NAME", "NhanSu")
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
STAFF_COLUMNS = ["MSGV", "Họ và tên", "Đơn vị", "Bộ môn"]
LOG_COLUMNS = ["Ngày", "MSGV", "Họ và tên", "Đơn vị", "Bộ môn", "CS", "Ca", "Tiết từ", "Tiết đến", "Số tiết", "Giờ bắt đầu phân công", "Giờ kết thúc phân công", "Vào muộn phút", "IN/OUT", "Giờ", "Timestamp"]

LOCATIONS = {
    "Cơ sở 1: 217 Hồng Bàng": {"code": "CS1", "lat": 10.754665, "lon": 106.663381, "radius": 100},
    "Cơ sở 2: 41-43 Đinh Tiên Hoàng": {"code": "CS2", "lat": 10.785434, "lon": 106.702667, "radius": 100}
}
LOCATION_BY_CODE = {v["code"]: k for k, v in LOCATIONS.items()}

# Thay thế bằng dòng chuẩn này:
st.set_page_config(page_title="Hệ thống điểm danh tích hợp", layout="wide", initial_sidebar_state="expanded")

# ===================== CSS ĐỒNG BỘ GIAO DIỆN CHỮ TO RÕ =====================
st.html(
    """
    <style>
    html, body, .stApp { color: #000000 !important; font-size: 18px !important; }
    .custom-title { font-family: "Times New Roman", Times, serif; font-size: 21px; font-weight: bold; text-align: center; margin-bottom: 15px; color: #1E3A8A; }
    h1, h2, h3 { font-weight: 900 !important; color: #000000 !important; }
    label, p, span, div { color: #000000 !important; }
    input { font-weight: 700 !important; color: #000000 !important; }
    .stButton > button { font-weight: 900 !important; min-height: 3.2rem !important; font-size: 1.05rem !important; }
    div[data-testid="stRadio"] > div { flex-direction: row !important; justify-content: center !important; gap: 30px; }
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

# ===================== LOGIC ĐIỂM DANH DÙNG CHUNG GẮN VỚI GPS VÀ TIẾT HỌC =====================
def find_user_by_code(sheet_key, code_input):
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
                "MÃ": raw_digits.zfill(8) if len(raw_digits) <= 8 else raw_digits,
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

def render_location_check(campus_code):
    campus_name = LOCATION_BY_CODE.get(campus_code, "Cơ sở 1: 217 Hồng Bàng")
    campus = LOCATIONS[campus_name]
    st.info(f"📍 Vị trí yêu cầu: {campus_name}")
    if streamlit_geolocation is None or geodesic is None:
        st.error("Ứng dụng thiếu thư viện GPS.")
        st.stop()
    loc = streamlit_geolocation()
    if not loc:
        st.warning("Đang kết nối vệ tinh GPS... Vui lòng đồng ý cấp quyền truy cập vị trí trên trình duyệt.")
        st.stop()
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        st.warning("Thiết bị chưa phản hồi tọa độ. Vui lòng thử lại.")
        st.stop()
    distance = geodesic((float(lat), float(lon)), (campus["lat"], campus["lon"])).meters
    if distance > campus["radius"]:
        st.error(f"❌ Ngoài bán kính cho phép! Khoảng cách hiện tại: {round(distance,1)}m (> {campus['radius']}m)")
        st.stop()
    st.success("✅ Vị trí hợp lệ. Đã xác thực trong phạm vi trường học.")

# ===================== LUỒNG ĐIỂM DANH ĐỒNG BỘ DÙNG CHUNG CHO CẢ GV VÀ SV =====================
def render_attendance_flow(user_type, sheet_key):
    qp = {k: v[0] if isinstance(v, list) else v for k, v in st.experimental_get_query_params().items()}
    campus_code = qp.get("coso", "CS1")
    
    st.title(f"Hệ thống điểm danh {user_type}")
    if now_vn().date().weekday() == 6:
        st.error("Hệ thống đóng cửa vào ngày Chủ Nhật.")
        st.stop()
        
    render_location_check(campus_code)
    shift = infer_shift()
    st.info(f"Khung buổi hiện tại: Ca {shift}")
    
    action_label = st.radio("Chọn nghiệp vụ điểm danh", ["Vào ca (Check-in)", "Ra ca (Check-out)"], horizontal=True, key=f"act_{user_type}")
    action = "IN" if "Vào" in action_label else "OUT"
    
    allowed = MORNING_LESSONS if shift == "Sáng" else AFTERNOON_LESSONS
    c1, c2 = st.columns(2)
    with c1: tiet_tu = st.number_input("Tiết bắt đầu", min_value=min(allowed), max_value=max(allowed), value=min(allowed), key=f"f_{user_type}")
    with c2: tiet_den = st.number_input("Tiết kết thúc", min_value=min(allowed), max_value=max(allowed), value=max(allowed), key=f"t_{user_type}")
    
    info_tiet = lesson_range_info(shift, tiet_tu, tiet_den)
    st.caption(f"Khung thời gian chuẩn: Tiết {info_tiet['lesson_from']} -> {info_tiet['lesson_to']} ({info_tiet['start_time']} - {info_tiet['end_time']}) | Tổng: {info_tiet['num_lessons']} tiết")
    
    label_text = f"Nhập 4 số cuối của MSGV" if user_type == "GV" else f"Nhập 4 số cuối của MSSV"
    code_suffix = st.text_input(label_text, max_chars=4, placeholder="Ví dụ: 1234", key=f"code_{user_type}")
    
    if st.button("Xác nhận ghi nhận lên hệ thống", type="primary", use_container_width=True, key=f"btn_{user_type}"):
        if len(code_suffix.strip()) != 4 or not code_suffix.isdigit():
            st.warning("Yêu cầu nhập chính xác 4 chữ số cuối mã số định danh.")
            st.stop()
            
        user_info = find_user_by_code(sheet_key, code_suffix)
        if not user_info: st.error(f"Không tìm thấy thông tin {user_type} tương ứng."); st.stop()
        if user_info.get("ambiguous"): st.error("Mã số cuối bị trùng lặp trên hệ thống danh sách, vui lòng báo Giáo vụ."); st.stop()
        
        user_code_full = user_info["MÃ"]
        lw = get_ws_by_title(sheet_key, LOG_SHEET_NAME, is_log=True)
        ensure_header(lw, LOG_COLUMNS)
        
        # Thuật toán tính số phút đi muộn so với mốc phân công
        start_t = datetime.datetime.strptime(info_tiet["start_time"], "%H:%M").time()
        start_dt = datetime.datetime.combine(now_vn().date(), start_t, tzinfo=VN_TZ)
        late_min = max(0, int((now_vn() - start_dt).total_seconds() // 60)) if action == "IN" else 0
        
        # Thực hiện đồng bộ append bản ghi
        _google_api_retry(lambda: lw.append_row([
            today_str(), user_code_full, user_info["Họ và tên"], user_info["Đơn vị"], user_info["Bộ môn"],
            campus_code, shift, info_tiet["lesson_from"], info_tiet["lesson_to"], info_tiet["num_lessons"],
            info_tiet["start_time"], info_tiet["end_time"], late_min if action == "IN" else "", action,
            now_vn().strftime("%H:%M:%S"), timestamp_str()
        ], value_input_option="USER_ENTERED"))
        
        st.success(f"🎉 Điểm danh {action_label} THÀNH CÔNG! {user_type}: {user_info['Họ và tên']} ({user_code_full})")

# ===================== MÀN HÌNH QUẢN TRỊ TRUNG TÂM TÍCH HỢP CHUNG =====================
def get_base_url():
    return st.secrets.get("WRAPPER_URL") or st.secrets.get("APP_BASE_URL") or "https://giangvien.streamlit.app"

def render_admin_dashboard_flow():
    with st.sidebar:
        st.header("🔒 Đăng nhập hệ thống")
        if st.session_state.get("admin_logged"):
            st.success("Hệ thống đã mở khóa")
            if st.button("Đăng xuất khỏi Admin"): st.session_state.clear(); st.rerun()
        else:
            pw = st.text_input("Mật khẩu quản trị", type="password")
            if st.button("Xác thực Đăng nhập", type="primary", use_container_width=True):
                if pw == st.secrets.get("ADMIN_PASSWORD", "admin"):
                    st.session_state["admin_logged"] = True
                    st.rerun()
                else: st.error("Mật khẩu không hợp lệ.")
                
    if not st.session_state.get("admin_logged"):
        st.error("Vui lòng nhập mật khẩu quản trị ở thanh công cụ bên trái để truy cập dữ liệu tổng hợp.")
        st.stop()
        
    with st.sidebar:
        st.markdown("---")
        st.markdown("**Báo cáo dữ liệu động**")
        # Điểm mấu chốt: Cho phép Admin chọn đối tượng cần cấu hình hoặc xem thống kê
        target_view = st.selectbox("Chọn phân hệ đối tượng:", ["Giảng viên", "Sinh viên"])
        active_sheet_key = GV_SHEET_KEY if target_view == "Giảng viên" else SV_SHEET_KEY
        param_flag = "gv=1" if target_view == "Giảng viên" else "sv=1"
        
        menu = st.radio("Mục quản lý:", ["Tạo QR cố định điểm danh", "Tra cứu thông tin", "Báo cáo thống kê tổng hợp"])
        
    # Chức năng 1: Tạo QR tĩnh theo Cơ sở cho đối tượng đang chọn
    if menu == "Tạo QR cố định điểm danh":
        st.subheader(f"Tạo mã QR phân hệ: {target_view}")
        campus_name = st.selectbox("Chọn vị trí cơ sở trường học", list(LOCATIONS.keys()))
        campus_code = LOCATIONS[campus_name]["code"]
        
        if st.button("Khởi tạo mã QR Code", type="primary", use_container_width=True):
            qr_data = f"{get_base_url()}/?{param_flag}&coso={urllib.parse.quote(campus_code)}"
            qr = qrcode.make(qr_data)
            buf = io.BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
            st.image(Image.open(buf), caption=f"Mã QR cố định ({target_view}) tại {campus_code}", width=360)
            st.code(qr_data)
            
    # Chức năng 2: Tra cứu thông tin danh sách
    elif menu == "Tra cứu thông tin":
        st.subheader(f"Tìm kiếm thông tin dữ liệu {target_view}")
        q = st.text_input("Nhập mã số (hoặc 4 số cuối) hoặc họ tên cần tra cứu:")
        if st.button("Thực hiện tìm kiếm", use_container_width=True):
            ws = get_ws_by_title(active_sheet_key, STAFF_SHEET_NAME)
            rows = _google_api_retry(lambda: ws.get_all_records(default_blank=""))
            res = [r for r in rows if q in safe_str(r.get("MSGV")) or norm_search(q) in norm_search(r.get("Họ và tên"))]
            if res: st.dataframe(pd.DataFrame(res), use_container_width=True)
            else: st.warning("Không tìm thấy kết quả phù hợp với từ khóa.")
            
    # Chức năng 3: Xem báo cáo bảng Log chi tiết
    elif menu == "Báo cáo thống kê tổng hợp":
        st.subheader(f"Bảng nhật ký lịch sử điểm danh (Log) - {target_view}")
        ws = get_ws_by_title(active_sheet_key, LOG_SHEET_NAME, is_log=True)
        data = _google_api_retry(lambda: ws.get_all_records(default_blank=""))
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
            
            # Vẽ biểu đồ tương tác nhanh số lượt log theo Ca học
            if "Ca" in df.columns:
                st.markdown("**Biểu đồ phân bố lượt điểm danh theo ca (Sáng/Chiều):**")
                chart_df = df.groupby("Ca").size().reset_index(name="Số lượt")
                chart = alt.Chart(chart_df).mark_bar().encode(x="Ca:N", y="Số lượt:Q", color="Ca:N").properties(height=300)
                st.altair_chart(chart, use_container_width=True)
        else:
            st.info(f"Hệ thống file dữ liệu Log của phân hệ {target_view} hiện tại trống.")

# ===================== ĐIỀU HƯỚNG VÀ PHÂN LUỒNG URL CHÍNH (ROUTING) =====================
# Thay thế bằng đoạn code chuẩn hóa mới này:
if "gv" in st.query_params and st.query_params["gv"] == "1":
    render_attendance_flow("GV", GV_SHEET_KEY)
elif "sv" in st.query_params and st.query_params["sv"] == "1":
    render_attendance_flow("SV", SV_SHEET_KEY)
else:
    render_admin_dashboard_flow()

# ===================== CHÂN TRANG BẢN QUYỀN ĐỒNG BỘ =====================
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
