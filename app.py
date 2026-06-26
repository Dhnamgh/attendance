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


# ===================== CẤU HÌNH HỆ THỐNG TÍCH HỢP =====================
# Cấu hình Phân hệ Giảng viên (GV)
GV_SHEET_KEY = st.secrets["GV_SHEET"]
STAFF_SHEET_NAME = st.secrets.get("STAFF_SHEET_NAME", "NhanSu")
LOG_SHEET_NAME = st.secrets.get("LOG_SHEET_NAME", "Log")

# Cấu hình Phân hệ Sinh viên (SV) - Giữ nguyên từ mainsv.py
SV_SHEET_KEY = st.secrets["SV_SHEET"]
WORKSHEET_NAME = "D25C"                                     
QR_SLOT_SECONDS = 30          
UNLOCK_TTL = 120              
MSSV_PREFIX = st.secrets.get("SESSION_PREFIX", "51125")  

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# Quy định khung giờ tiết dạy Giảng viên
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

# ===================== CSS ĐỒNG BỘ GIAO DIỆN CHỮ TO RÕ CỦA THẦY =====================
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

# ===================== TIỆN ÍCH LOGIC TỪ MAINSV & APP GỐC =====================
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

# ===================== TOKENS QR ĐỘNG (30S THEO MAINSV.PY) =====================
def current_slot(step=QR_SLOT_SECONDS): return int(time.time() // step)
def token_valid(t_str: str, step=QR_SLOT_SECONDS) -> bool:
    if not t_str or not str(t_str).isdigit(): return False
    return abs(int(t_str) - current_slot(step=step)) <= 1

# ===================== VỊ TRÍ GPS DÙNG CHUNG CẢ GV VÀ SV =====================
def verify_gps_location(campus_code):
    campus_name = LOCATION_BY_CODE.get(campus_code, "Cơ sở 1: 217 Hồng Bàng")
    campus = LOCATIONS[campus_name]
    if streamlit_geolocation is None or geodesic is None:
        st.error("Ứng dụng thiếu thư viện xác thực GPS.")
        return False
        
    loc = streamlit_geolocation()
    if not loc:
        st.warning("📡 Đang quét tọa độ GPS vệ tinh... Vui lòng đồng ý cấp quyền vị trí cho trình duyệt.")
        return False
        
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        st.warning("Không nhận được phản hồi GPS từ thiết bị.")
        return False
        
    distance = geodesic((float(lat), float(lon)), (campus["lat"], campus["lon"])).meters
    if distance > campus["radius"]:
        st.error(f"❌ Ngoài bán kính cho phép! Khoảng cách hiện tại của bạn: {round(distance,1)}m (> {campus['radius']}m tại {campus_name})")
        return False
    return True

# ===================== TRA CỨU GIẢNG VIÊN CƠ SỞ =====================
def find_staff_by_msgv(msgv_input):
    ws = get_ws_by_title(GV_SHEET_KEY, STAFF_SHEET_NAME)
    values = _google_api_retry(lambda: ws.get_all_values())
    if not values or len(values) < 2: return None
    headers = values[0]
    hn = [norm_header(h) for h in headers]
    msgv_i = hn.index("msgv") if "msgv" in hn else 0
    name_i = hn.index("hovaten") if "hovaten" in hn else 1
    unit_i = hn.index("donvi") if "donvi" in hn else 2
    dept_i = hn.index("bomon") if "bomon" in hn else 3
    
    target = norm_digits(msgv_input)
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

# ===================== MÀN HÌNH 1: GIẢNG VIÊN ĐIỂM DANH (?gv=1) =====================
def render_gv_attendance_flow():
    qp = st.query_params
    campus_code = qp.get("coso", "CS1")
    
    st.title("👨‍🏫 Điểm danh Giảng viên")
    if now_vn().date().weekday() == 6:
        st.error("Chủ nhật không hỗ trợ điểm danh đứng lớp.")
        st.stop()
        
    gps_ok = verify_gps_location(campus_code)
    if not gps_ok: st.stop()
    
    shift = infer_shift()
    st.info(f"Ca hiện tại: Buổi {shift}")
    
    action_label = st.radio("Chọn hình thức", ["Vào ca", "Ra ca"], horizontal=True)
    action = "IN" if action_label == "Vào ca" else "OUT"
    
    allowed = MORNING_LESSONS if shift == "Sáng" else AFTERNOON_LESSONS
    c1, c2 = st.columns(2)
    with c1: tiet_tu = st.number_input("Từ tiết", min_value=min(allowed), max_value=max(allowed), value=min(allowed))
    with c2: tiet_den = st.number_input("Đến tiết", min_value=min(allowed), max_value=max(allowed), value=max(allowed))
    
    info_tiet = lesson_range_info(shift, tiet_tu, tiet_den)
    st.caption(f"Khung giờ chuẩn: Tiết {info_tiet['lesson_from']} - {info_tiet['lesson_to']} ({info_tiet['start_time']} - {info_tiet['end_time']})")
    
    msgv_suffix = st.text_input("Nhập 4 số cuối MSGV", max_chars=4, placeholder="Ví dụ: 1234")
    
    if st.button("Xác nhận điểm danh Giảng viên", type="primary", use_container_width=True):
        if len(msgv_suffix.strip()) != 4 or not msgv_suffix.isdigit():
            st.warning("Vui lòng nhập đúng 4 chữ số cuối MSGV.")
            st.stop()
            
        staff = find_staff_by_msgv(msgv_suffix)
        if not staff: st.error("Không tìm thấy Giảng viên trong danh sách."); st.stop()
        if staff.get("ambiguous"): st.error("Bị trùng 4 số cuối, hãy liên hệ Admin."); st.stop()
        
        msgv_full = staff["MSGV"]
        lw = get_ws_by_title(GV_SHEET_KEY, LOG_SHEET_NAME, is_log=True)
        
        start_t = datetime.datetime.strptime(info_tiet["start_time"], "%H:%M").time()
        start_dt = datetime.datetime.combine(now_vn().date(), start_t, tzinfo=VN_TZ)
        late_min = max(0, int((now_vn() - start_dt).total_seconds() // 60)) if action == "IN" else 0
        
        _google_api_retry(lambda: lw.append_row([
            today_str(), msgv_full, staff["Họ và tên"], staff["Đơn vị"], staff["Bộ môn"],
            campus_code, shift, info_tiet["lesson_from"], info_tiet["lesson_to"], info_tiet["num_lessons"],
            info_tiet["start_time"], info_tiet["end_time"], late_min if action == "IN" else "", action,
            now_vn().strftime("%H:%M:%S"), timestamp_str()
        ], value_input_option="USER_ENTERED"))
        
        st.success(f"🎉 Ghi nhận {action_label} thành công cho Giảng viên: {staff['Họ và tên']} ({msgv_full})")

# ===================== MÀN HÌNH 2: SINH VIÊN ĐIỂM DANH QR ĐỘNG + GPS (?sv=1) =====================
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
    campus_code = qp.get("coso", "CS1")  # Mặc định lấy cơ sở quét
    
    st.title("🎓 Điểm danh Sinh viên")
    st.info(f"Bạn đang thực hiện điểm danh cho: **{buoi_sv}**")
    
    # 1. TÍCH HỢP ĐỊNH VỊ GPS Y HỆT CỦA GV
    gps_ok = verify_gps_location(campus_code)
    if not gps_ok: st.stop()
    
    lock_key = f"sv_lock_{buoi_sv}"
    if st.session_state.get(lock_key):
        st.success("✅ Bạn đã thực hiện điểm danh thành công trên thiết bị này.")
        st.stop()
        
    # 2. KIỂM TRA MÃ TOKEN ĐỘNG 30S ĐỂ CHỐNG GIAN LẬN LINK (Từ mainsv.py)
    unlock_key = f"session_active_{buoi_sv}"
    if not st.session_state.get(unlock_key):
        if not token_valid(token_qr, step=QR_SLOT_SECONDS):
            st.error("⏳ Mã QR đã hết hạn. Vui lòng quét mã QR mới đang trình chiếu trên bảng lớp học.")
            st.stop()
        st.session_state[unlock_key] = time.time()
    else:
        if time.time() - st.session_state[unlock_key] > UNLOCK_TTL:
            st.error("❌ Phiên làm việc quá hạn (120s). Vui lòng quét lại mã QR mới.")
            st.stop()
            
    mssv_suffix = st.text_input("Nhập **4 số cuối** MSSV", max_chars=4, placeholder="VD: 1234")
    hoten = st.text_input("Nhập đầy đủ Họ và Tên sinh viên (Có dấu)")
    
    if mssv_suffix.strip().isdigit():
        st.caption(f"Mã MSSV hệ thống đối chiếu: **{MSSV_PREFIX}{mssv_suffix.strip().zfill(4)}**")
        
    if st.button("✅ Xác nhận điểm danh Sinh viên", type="primary", use_container_width=True):
        if not mssv_suffix.strip().isdigit() or len(mssv_suffix.strip()) != 4 or not hoten.strip():
            st.warning("⚠️ Vui lòng điền đầy đủ và chính xác thông tin yêu cầu.")
            st.stop()
            
        full_mssv = f"{MSSV_PREFIX}{mssv_suffix.strip().zfill(4)}"
        sheet = get_ws_by_title(SV_SHEET_KEY, WORKSHEET_NAME)
        
        # Đọc dữ liệu ghi trực tiếp lên danh sách lớp giống app sv cũ
        records = _google_api_retry(lambda: sheet.get_all_records(default_blank=""))
        target_row = None
        for idx, r in enumerate(records, start=2):
            if norm_digits(r.get("MSSV", "")) == norm_digits(full_mssv):
                target_row = idx
                break
                
        if not target_row:
            st.error(f"❌ Không tìm thấy mã sinh viên {full_mssv} trong danh sách lớp {WORKSHEET_NAME}.")
            st.stop()
            
        # So khớp họ tên
        headers = _google_api_retry(lambda: sheet.row_values(1))
        hn = [norm_header(h) for h in headers]
        name_col = (hn.index("hovaten") + 1) if "hovaten" in hn else 2
        hoten_sheet = sheet.cell(target_row, name_col).value
        
        if normalize_name(hoten_sheet or "") != normalize_name(hoten):
            st.error("❌ Họ tên không khớp với dữ liệu gốc của Mã số sinh viên này.")
            st.stop()
            
        # Tìm cột Buổi học để tích dấu và ghi thời gian thực
        buoi_col = (hn.index(norm_header(buoi_sv)) + 1) if norm_header(buoi_sv) in hn else 4
        time_col = find_or_create_time_col(sheet, buoi_col, buoi_sv)
        
        # Ghi đè trực tiếp ô dữ liệu như file mainsv.py cũ của thầy
        _google_api_retry(lambda: sheet.update_cell(target_row, buoi_col, "✅"))
        _google_api_retry(lambda: sheet.update_cell(target_row, time_col, timestamp_str()))
        
        st.session_state[lock_key] = True
        st.success(f"🎉 Điểm danh thành công! Sinh viên: {hoten_sheet} ({full_mssv})")
        st.rerun()

# ===================== MÀN HÌNH 3: TRANG QUẢN TRỊ TRUNG TÂM =====================
def get_base_url():
    return st.secrets.get("WRAPPER_URL") or st.secrets.get("APP_BASE_URL") or "https://giangvien.streamlit.app"

def render_admin_dashboard_flow():
    with st.sidebar:
        st.header("🔒 Quản trị")
        if st.session_state.get("admin_logged"):
            st.success("Hệ thống đã kết nối")
            if st.button("Đăng xuất Admin"): st.session_state.clear(); st.rerun()
        else:
            pw = st.text_input("Mật khẩu hệ thống", type="password")
            if st.button("Đăng nhập Hệ thống", type="primary", use_container_width=True):
                if pw == st.secrets.get("ADMIN_PASSWORD", "admin"):
                    st.session_state["admin_logged"] = True
                    st.rerun()
                else: st.error("Mật khẩu không chính xác.")
                
    if not st.session_state.get("admin_logged"):
        st.error("🔒 Vui lòng mở rộng thanh công cụ bên trái và đăng nhập mật khẩu quản trị để tiếp tục.")
        st.stop()
        
    with st.sidebar:
        st.markdown("---")
        menu = st.radio("Chức năng quản lý:", ["👨‍🏫 Giảng viên (QR cố định)", "🎓 Sinh viên (QR động 30s)", "📊 Xem dữ liệu bảng điểm"])
        
    # --- CHỨC NĂNG 1: TẠO QR CỐ ĐỊNH CHO GIẢNG VIÊN ---
    if menu == "👨‍🏫 Giảng viên (QR cố định)":
        st.subheader("Tạo mã QR cố định theo cơ sở cho Giảng viên")
        campus_name = st.selectbox("Chọn cơ sở trường học", list(LOCATIONS.keys()))
        campus_code = LOCATIONS[campus_name]["code"]
        
        if st.button("Khởi tạo mã QR GV", type="primary", use_container_width=True):
            qr_data = f"{get_base_url()}/?gv=1&coso={urllib.parse.quote(campus_code)}"
            qr = qrcode.make(qr_data)
            buf = io.BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
            st.image(Image.open(buf), caption=f"Mã QR cố định Giảng viên tại {campus_code}", width=360)
            st.code(qr_data)
            
    # --- CHỨC NĂNG 2: TRÌNH CHIẾU QR ĐỘNG 30S CHO SINH VIÊN (Từ mainsv.py gốc) ---
    elif menu == "🎓 Sinh viên (QR động 30s)":
        st.subheader(f"📸 Trình chiếu Mã QR Điểm danh Động lớp {WORKSHEET_NAME}")
        buoi = st.selectbox("Chọn phiên học buổi số mấy", ["Buổi 1", "Buổi 2", "Buổi 3", "Buổi 4", "Buổi 5", "Buổi 6"])
        campus_name = st.selectbox("Lớp đang học tại cơ sở nào? (Để ép GPS SV)", list(LOCATIONS.keys()))
        campus_code = LOCATIONS[campus_name]["code"]
        auto = st.toggle("Tự động xoay vòng Token mã hóa chống gian lận (30 giây)", value=True)
        
        if st.button("Bắt đầu trình chiếu QR lớp học", type="primary", use_container_width=True):
            qr_slot = st.empty()
            timer_slot = st.empty()
            while True:
                slot = current_slot()
                # Link SV bóc tách kèm biến cơ sở để bắt GPS đồng bộ
                qr_data = f"{get_base_url()}/?sv=1&buoi={urllib.parse.quote(buoi)}&t={slot}&coso={campus_code}"
                
                qr = qrcode.make(qr_data)
                buf = io.BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
                qr_slot.image(Image.open(buf), caption=f"📱 Sinh viên ngồi tại lớp quét mã QR đang chiếu này", width=360)
                
                remain = QR_SLOT_SECONDS - (int(time.time()) % QR_SLOT_SECONDS)
                timer_slot.markdown(f"⏳ **Mã QR tự động đổi sau:** `{remain} giây`  •  **Phiên:** `{buoi}`  •  **Ép định vị:** `{campus_code}`")
                if not auto: break
                time.sleep(1)
                
    # --- CHỨC NĂNG 3: XEM BẢNG TỔNG HỢP ---
    elif menu == "📊 Xem dữ liệu bảng điểm":
        target_view = st.radio("Chọn tập dữ liệu hiển thị:", ["Nhật ký Log Giảng viên", "Bảng điểm danh Sinh viên lớp D25C"], horizontal=True)
        if "Giảng viên" in target_view:
            ws = get_ws_by_title(GV_SHEET_KEY, LOG_SHEET_NAME, is_log=True)
            data = _google_api_retry(lambda: ws.get_all_records(default_blank=""))
            if data: st.dataframe(pd.DataFrame(data), use_container_width=True)
            else: st.info("Nhật ký điểm danh GV trống.")
        else:
            ws = get_ws_by_title(SV_SHEET_KEY, WORKSHEET_NAME)
            data = _google_api_retry(lambda: ws.get_all_records(default_blank=""))
            if data: st.dataframe(pd.DataFrame(data), use_container_width=True)
            else: st.info("Bảng dữ liệu lớp học SV trống.")

# ===================== ĐIỀU HƯỚNG ROUTING CHÍNH (STREAMLIT MỚI) =====================
if "gv" in st.query_params and st.query_params["gv"] == "1":
    render_gv_attendance_flow()
elif "sv" in st.query_params and st.query_params["sv"] == "1":
    render_sv_attendance_flow()
else:
    render_admin_dashboard_flow()

# ===================== CHÂN TRANG BẢN QUYỀN ĐỒNG BỘ CỦA THẦY =====================
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
