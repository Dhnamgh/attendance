import streamlit as st
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from streamlit_geolocation import streamlit_geolocation
from math import radians, sin, cos, sqrt, atan2

st.set_page_config(layout="centered")

GV_LOG = st.secrets["GV_SHEET"]
SV_LOG = st.secrets["SV_SHEET"]
GV_DATA = st.secrets["GV_DATA"]
SV_DATA = st.secrets["SV_DATA"]

LAT_CENTER = st.secrets["LAT_CENTER"]
LON_CENTER = st.secrets["LON_CENTER"]
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

def sheet(k):
    return client().open_by_key(k).sheet1

def load(k):
    return pd.DataFrame(sheet(k).get_all_records())

def append(k,row):
    sheet(k).append_row(row)

# ================= TIME =================
def now():
    return datetime.datetime.now(VN_TZ)

def today():
    return now().strftime("%d/%m/%Y")

def now_hms():
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
    11:("16:35","17:25"),
}

def calc_lessons(ca, f, t):
    allowed = range(1,6) if ca=="Sáng" else [7,8,9,10,11]
    arr = [x for x in allowed if f<=x<=t]
    return arr, LESSON[arr[0]][0], LESSON[arr[-1]][1]

def to_min(t):
    h,m = map(int, t.split(":"))
    return h*60+m

def late(start):
    return max(0, now().hour*60+now().minute - to_min(start))

def required_time(n):
    base = n*50
    if n>3:
        base+=15
    return base

def can_out(checkin_time, need):
    t = datetime.datetime.strptime(checkin_time,"%H:%M:%S").time()
    dt = datetime.datetime.combine(now().date(), t, VN_TZ)
    return (now()-dt).total_seconds()/60 >= need

# ================= GPS =================
def check_gps():
    loc = streamlit_geolocation()

    if not loc or not loc.get("latitude"):
        st.error("Không lấy được GPS")
        return False

    lat = loc["latitude"]
    lon = loc["longitude"]

    dlat = radians(lat - LAT_CENTER)
    dlon = radians(lon - LON_CENTER)

    a = sin(dlat/2)**2 + cos(radians(LAT_CENTER))*cos(radians(lat))*sin(dlon/2)**2
    d = 2 * 6371000 * atan2(sqrt(a), sqrt(1-a))

    if d > RADIUS:
        st.error("Ngoài khu vực")
        return False

    return True

# ================= CHECK DATA =================
def exists(code, DATA, col):
    df = load(DATA)
    return code in df[col].astype(str).values

# ================= CORE =================
def do_checkin(LOG, DATA, code, col, ca, f, t):

    if not check_gps():
        return

    if not exists(code, DATA, col):
        st.error("Không tồn tại")
        return

    arr,s,e = calc_lessons(ca,f,t)
    late_min = late(s)

    append(LOG, [
        today(), code, ca,
        f,t,len(arr),
        s,e,
        late_min,
        "IN",
        now_hms()
    ])

    st.success(f"Đã vào ca - muộn {late_min} phút")

def do_checkout(LOG, code, col):

    df = load(LOG)

    last = df[
        (df[col]==code) &
        (df["IN/OUT"]=="IN")
    ]

    if last.empty:
        st.error("Chưa check-in")
        return

    last = last.iloc[-1]

    need = required_time(int(last["Số tiết"]))

    if not can_out(last["Giờ"], need):
        st.error("Chưa đủ thời gian")
        return

    append(LOG, [
        today(), code,
        "", "", "", "", "", "", "",
        "OUT", now_hms()
    ])

    st.success("Ra ca thành công")

# ================= UI CHUNG =================
def render(label, LOG, DATA, col):

    code = st.text_input(label)

    ca = st.selectbox("Ca", ["Sáng","Chiều"])

    c1,c2 = st.columns(2)
    with c1:
        f = st.number_input("Tiết bắt đầu",1,11,1)
    with c2:
        t = st.number_input("Tiết kết thúc",1,11,3)

    arr,s,e = calc_lessons(ca,f,t)

    st.info(f"{arr} | {s} - {e}")

    col1,col2 = st.columns(2)

    with col1:
        if st.button("Check-in", use_container_width=True):
            do_checkin(LOG, DATA, code, col, ca, f, t)

    with col2:
        if st.button("Check-out", use_container_width=True):
            do_checkout(LOG, code, col)

# ================= MAIN =================
st.title("Hệ thống điểm danh")
st.image("h.png", width=150)

menu = st.radio("", ["Giảng viên","Sinh viên","Quản trị"])

if menu == "Giảng viên":
    st.subheader("Điểm danh giảng viên")
    render("MSGV", GV_LOG, GV_DATA, "MSGV")

elif menu == "Sinh viên":
    st.subheader("Điểm danh sinh viên")
    render("MSSV", SV_LOG, SV_DATA, "MSSV")

else:
    st.subheader("Quản trị")

    pw = st.text_input("Mật khẩu", type="password")

    if pw == ADMIN_PASSWORD:
        df_gv = load(GV_LOG)
        df_sv = load(SV_LOG)

        st.write("Giảng viên")
        if not df_gv.empty:
            st.line_chart(df_gv.groupby("Ngày").size())

        st.write("Sinh viên")
        if not df_sv.empty:
            st.line_chart(df_sv.groupby("Ngày").size())
