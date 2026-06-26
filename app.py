import streamlit as st
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from streamlit_geolocation import streamlit_geolocation
from math import radians, sin, cos, sqrt, atan2

st.set_page_config(layout="centered")

# ===== TÙY CHỈNH FONT CHỮ TIÊU ĐỀ (Times New Roman, Cỡ 16px) =====
st.markdown(
    """
    <style>
    .custom-title {
        font-family: "Times New Roman", Times, serif;
        font-size: 20px; /* Tương đương cỡ 16pt của Word để không bị tràn dòng */
        font-weight: bold;
        text-align: center;
        margin-bottom: 20px;
    }
    /* Gom hàng radio chọn GV/SV gọn hơn */
    div[data-testid="stRadio"] > div {
        flex-direction: row;
        justify-content: center;
    }
    </style>
    <div class="custom-title">Hệ thống điểm danh</div>
    """,
    unsafe_html=True
)

# ===== CHỈ DÙNG 2 SHEET =====
try:
    GV_SHEET = st.secrets["GV_SHEET"]
    SV_SHEET = st.secrets["SV_SHEET"]
except Exception:
    st.error("Chưa cấu hình GV_SHEET hoặc SV_SHEET trong Streamlit Secrets!")

# ===== CẤU HÌNH VỊ TRÍ TÂM =====
LAT_CENTER = 10.754665
LON_CENTER = 106.663381
RADIUS = 100

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# ================= GOOGLE SPREADSHEETS =================
@st.cache_resource
def client():
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["google_service_account"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Lỗi kết nối Google Service Account: {e}")
        return None

def get_sheet(key):
    c = client()
    if c:
        return c.open_by_key(key).sheet1
    return None

def append_row(key, row):
    sheet = get_sheet(key)
    if sheet:
        sheet.append_row(row)
    else:
        raise Exception("Không thể kết nối tới Google Sheet.")

@st.cache_data(ttl=3)
def load_df(key):
    sheet = get_sheet(key)
    if sheet:
        return pd.DataFrame(sheet.get_all_records())
    return pd.DataFrame()

# ================= TIME LOGIC =================
def now():
    return datetime.datetime.now(VN_TZ)

def today():
    return now().strftime("%d/%m/%Y")

def now_str():
    return now().strftime("%H:%M:%S")

# ================= LESSON CONFIG =================
LESSON = {
    1:("07:00","07:50"),
    2:("07:50","08:40"),
    3:("08:40","09:30"),
    4:("09:45","10:35"),
    5:("10:35","11:25"),
    7:("13:00","13:50"),
    8:("13:50","14:40"),
    9:("14:40","15:30"),
    10:("15:45","16:35"),
    11:("16:35","17:25")
}

def calc_lessons(ca, f, t):
    allowed = range(1, 6) if ca == "Sáng" else range(7, 12)
    arr = [x for x in allowed if f <= x <= t]
    if not arr:
        default_idx = 1 if ca == "Sáng" else 7
        return [default_idx], LESSON[default_idx][0], LESSON[default_idx][1]
    return arr, LESSON[arr[0]][0], LESSON[arr[-1]][1]

def to_min(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m

def calc_late(start_time_str):
    current_minutes = now().hour * 60 + now().minute
    start_minutes = to_min(start_time_str)
    return max(0, current_minutes - start_minutes)

def required_time(n):
    total = n * 50
    if n > 3:
        total += 15
    return total

def can_checkout(start_time, need):
    t = datetime.datetime.strptime(start_time, "%H:%M:%S").time()
    dt = datetime.datetime.combine(now().date(), t, VN_TZ)
    worked = (now() - dt).total_seconds() / 60
    return worked >= need

# ================= GPS GEOLOCATION =================
def check_gps(loc):
    if not loc or not loc.get("latitude"):
        st.error("Không lấy được GPS. Hãy chắc chắn thầy đã cấp quyền vị trí cho trình duyệt.")
        return False

    lat = loc["latitude"]
    lon = loc["longitude"]

    dlat = radians(lat - LAT_CENTER)
    dlon = radians(lon - LON_CENTER)

    a = sin(dlat/2)**2 + cos(radians(LAT_CENTER))*cos(radians(lat))*sin(dlon/2)**2
    d = 2 * 6371000 * atan2(sqrt(a), sqrt(1-a))

    if d > RADIUS:
        st.error(f"Ngoài khu vực điểm danh! Khoảng cách hiện tại: {round(d, 1)}m (Yêu cầu < {RADIUS}m)")
        return False
    return True

# ================= LOGIC ĐIỂM DANH CHUNG =================
def checkin(sheet_key, code, ca, f, t, loc):
    if not code.strip():
        st.error("Vui lòng nhập Mã số định danh!")
        return

    if not check_gps(loc):
        return

    arr, s, e = calc_lessons(ca, f, t)
    late = calc_late(s)

    try:
        append_row(sheet_key, [
            today(), code, ca,
            f, t, len(arr),
            s, e,
            late,
            "IN",
            now_str()
        ])
        st.success(f"🎉 Check-in thành công! Mã: {code} | Ca: {ca} | Đi muộn: {late} phút.")
    except Exception as err:
        st.error(f"Ghi dữ liệu thất bại: {err}")


def checkout(sheet_key, code):
    if not code.strip():
        st.error("Vui lòng nhập Mã số định danh!")
        return

    try:
        df = load_df(sheet_key)
        if df.empty:
            st.error("Không thể đọc dữ liệu hoặc Sheet chưa có dữ liệu nào!")
            return

        col_target = df.columns[1] 

        last = df[
            (df[col_target].astype(str) == str(code)) &
            (df["IN/OUT"] == "IN")
        ]

        if last.empty:
            st.error(f"Không tìm thấy dữ liệu Check-in hợp lệ hôm nay cho mã: {code}")
            return

        last = last.iloc[-1]
        need = required_time(int(last["Số tiết"]))

        if not can_checkout(last["Giờ"], need):
            st.error(f"Chưa đủ thời gian! Thời gian yêu cầu tối thiểu là {need} phút.")
            return

        append_row(sheet_key, [
            today(), code,
            "", "", "", "", "", "", "",
            "OUT",
            now_str()
        ])
        st.success(f"🚀 Check-out thành công cho mã: {code}.")
    except Exception as err:
        st.error(f"Lỗi hệ thống khi ra ca: {err}")

# ================= FORM HIỂN THỊ ĐIỂM DANH =================
def render(user_type, sheet_key):
    # Lấy vị trí GPS độc lập theo Tab để không bị xung đột bộ đệm
    loc = streamlit_geolocation(key=f"gps_{user_type}")

    label_text = "Mã số Giảng viên (MSGV)" if user_type == "GV" else "Mã số Sinh viên (MSSV)"
    code = st.text_input(label_text, value="", key=f"code_{user_type}")

    # Tự động chọn Ca Sáng/Chiều dựa theo mốc giờ thực tế trên thiết bị
    current_hour = now().hour
    suggested_index = 0 if current_hour < 12 else 1
    ca = st.selectbox("Ca làm việc", ["Sáng", "Chiều"], index=suggested_index, key=f"ca_{user_type}")

    c1, c2 = st.columns(2)
    with c1:
        default_f = 1 if ca == "Sáng" else 7
        f = st.number_input("Tiết bắt đầu", 1, 11, default_f, key=f"f_{user_type}")
    with c2:
        default_t = 3 if ca == "Sáng" else 9
        t = st.number_input("Tiết kết thúc", 1, 11, default_t, key=f"t_{user_type}")

    arr, s, e = calc_lessons(ca, f, t)
    st.caption(f"📋 Khung giờ dự kiến: Tiết học {arr} ({s} - {e})")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Điểm danh VÀO (Check-in)", use_container_width=True, key=f"btn_in_{user_type}"):
            checkin(sheet_key, code, ca, f, t, loc)

    with col2:
        if st.button("Điểm danh RA (Check-out)", use_container_width=True, key=f"btn_out_{user_type}"):
            checkout(sheet_key, code)

# ================= MAIN APP =================
# Gom nút bấm Giảng viên và Sinh viên lên cùng 1 hàng bằng tham số horizontal=True
menu = st.radio("", ["Giảng viên", "Sinh viên"], horizontal=True)

if menu == "Giảng viên":
    st.subheader("Trang dành cho Giảng viên")
    render("GV", GV_SHEET)
else:
    st.subheader("Trang dành cho Sinh viên")
    render("SV", SV_SHEET)
