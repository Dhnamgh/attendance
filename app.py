import streamlit as st
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from streamlit_geolocation import streamlit_geolocation
from math import radians, sin, cos, sqrt, atan2

st.set_page_config(layout="centered")

# ===== CHỈ DÙNG 2 SHEET =====
GV_SHEET = st.secrets["GV_SHEET"]
SV_SHEET = st.secrets["SV_SHEET"]

# ===== CẤU HÌNH VỊ TRÍ =====
LAT_CENTER = 10.754665
LON_CENTER = 106.663381
RADIUS = 100

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# ================= GOOGLE =================
@st.cache_resource
def client():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["google_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

def get_sheet(key):
    return client().open_by_key(key).sheet1

def append_row(key, row):
    get_sheet(key).append_row(row)

@st.cache_data(ttl=5)
def load_df(key):
    return pd.DataFrame(get_sheet(key).get_all_records())

# ================= TIME =================
def now():
    return datetime.datetime.now(VN_TZ)

def today():
    return now().strftime("%d/%m/%Y")

def now_str():
    return now().strftime("%H:%M:%S")

# ================= LESSON =================
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
    allowed = range(1,6) if ca == "Sáng" else [7,8,9,10,11]
    arr = [x for x in allowed if f <= x <= t]
    if not arr:
        return [f], LESSON[f][0], LESSON[f][1]
    return arr, LESSON[arr[0]][0], LESSON[arr[-1]][1]

def to_min(t):
    h, m = map(int, t.split(":"))
    return h*60 + m

def calc_late(start):
    return max(0, now().hour*60 + now().minute - to_min(start))

def required_time(n):
    total = n*50
    if n > 3:
        total += 15
    return total

def can_checkout(start_time, need):
    t = datetime.datetime.strptime(start_time,"%H:%M:%S").time()
    dt = datetime.datetime.combine(now().date(), t, VN_TZ)
    worked = (now() - dt).total_seconds() / 60
    return worked >= need

# ================= GPS =================
def check_gps(loc):
    if not loc or not loc.get("latitude"):
        st.error("Không lấy được dữ liệu GPS. Vui lòng bật vị trí trên thiết bị và thử lại!")
        return False

    lat = loc["latitude"]
    lon = loc["longitude"]

    dlat = radians(lat - LAT_CENTER)
    dlon = radians(lon - LON_CENTER)

    a = sin(dlat/2)**2 + cos(radians(LAT_CENTER))*cos(radians(lat))*sin(dlon/2)**2
    d = 2 * 6371000 * atan2(sqrt(a), sqrt(1-a))

    if d > RADIUS:
        st.error(f"Bạn đang ở ngoài khu vực điểm danh (Cách tâm: {round(d, 1)}m)")
        return False

    return True

# ================= LOGIC CHUNG =================
def checkin(sheet_key, code, ca, f, t, loc):
    if not code.strip():
        st.error("Vui lòng nhập Mã số!")
        return

    if not check_gps(loc):
        return

    arr, s, e = calc_lessons(ca, f, t)
    late = calc_late(s)

    append_row(sheet_key, [
        today(), code, ca,
        f, t, len(arr),
        s, e,
        late,
        "IN",
        now_str()
    ])

    st.success(f"Đã vào ca - muộn {late} phút")


def checkout(sheet_key, code, col_name):
    if not code.strip():
        st.error("Vui lòng nhập Mã số!")
        return

    df = load_df(sheet_key)

    last = df[
        (df[col_name] == code) &
        (df["IN/OUT"] == "IN")
    ]

    if last.empty:
        st.error("Không tìm thấy dữ liệu Check-in trước đó!")
        return

    last = last.iloc[-1]

    need = required_time(int(last["Số tiết"]))

    if not can_checkout(last["Giờ"], need):
        st.error("Chưa đủ thời gian làm việc để ra ca!")
        return

    append_row(sheet_key, [
        today(), code,
        "", "", "", "", "", "", "",
        "OUT",
        now_str()
    ])

    st.success("Ra ca thành công")

# ================= FORM =================
def render(label, sheet_key):
    # Đặt widget lấy vị trí ở đầu form
    loc = streamlit_geolocation()

    code = st.text_input(label, value="")

    ca = st.selectbox("Ca", ["Sáng", "Chiều"])

    c1, c2 = st.columns(2)
    with c1:
        f = st.number_input("Tiết bắt đầu", 1, 11, 1)
    with c2:
        t = st.number_input("Tiết kết thúc", 1, 11, 3)

    arr, s, e = calc_lessons(ca, f, t)
    st.info(f"Tiết học: {arr} | Thời gian: {s} - {e}")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Check-in", use_container_width=True):
            checkin(sheet_key, code, ca, f, t, loc)

    with col2:
        if st.button("Check-out", use_container_width=True):
            checkout(sheet_key, code, label)

# ================= MAIN =================
st.title("Hệ thống điểm danh")

menu = st.radio("", ["Giảng viên", "Sinh viên"])

if menu == "Giảng viên":
    st.subheader("Điểm danh giảng viên")
    render("MSGV", GV_SHEET)
else:
    st.subheader("Điểm danh sinh viên")
    render("MSSV", SV_SHEET)
