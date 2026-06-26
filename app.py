import streamlit as st
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from math import radians, sin, cos, sqrt, atan2

try:
    from streamlit_geolocation import streamlit_geolocation
except:
    streamlit_geolocation = None

st.set_page_config(layout="wide")

GV_SHEET = st.secrets["GV_SHEET"]
SV_SHEET = st.secrets["SV_SHEET"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

LAT_CENTER = st.secrets.get("LAT_CENTER", 10.754665)
LON_CENTER = st.secrets.get("LON_CENTER", 106.663381)
RADIUS = st.secrets.get("RADIUS", 100)

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# ================= UI =================
st.markdown("""
<style>
.block-container {padding:0!important;}
header[data-testid="stHeader"]{display:none}

/* HEADER */
.header-bar {
    height:70px;
    background:#2c6b95;
    display:flex;
    align-items:center;
    justify-content:center;
    position:relative;
}
.header-title {
    color:white;
    font-size:28px;
    font-weight:600;
}
.header-logo {
    position:absolute;
    left:20px;
    height:55px;
}

/* SIDEBAR */
section[data-testid="stSidebar"] {
    background:#2c6b95 !important;
    width:230px;
}
section[data-testid="stSidebar"] * {
    color:white;
    font-size:16px !important;
    font-weight:500;
}

/* CONTENT */
.main-container {
    margin-left:40px;
    margin-right:40px;
}
.card {
    margin-top:20px;
    background:white;
    padding:25px;
    border-radius:6px;
}

/* INPUT */
input, div[data-baseweb="select"] {
    font-size:15px !important;
}

/* BUTTON */
button[kind="secondary"] {
    min-width:120px;
}

/* FOOTER */
.footer {
    background:#2b2f65;
    color:white;
    padding:25px;
    margin-top:40px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-bar">
    <img src="h.png" class="header-logo">
    <div class="header-title">HỆ THỐNG ĐIỂM DANH</div>
</div>
""", unsafe_allow_html=True)

# ================= GOOGLE =================
@st.cache_resource
def client():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["google_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

def sheet(key):
    return client().open_by_key(key).sheet1

@st.cache_data(ttl=10)
def load(key):
    return pd.DataFrame(sheet(key).get_all_records())

def append(key, row):
    sheet(key).append_row(row)

# ================= GPS =================
def check_location():
    if not streamlit_geolocation:
        return True
    loc = streamlit_geolocation()
    if loc and loc.get("latitude"):
        dlat = radians(loc["latitude"] - LAT_CENTER)
        dlon = radians(loc["longitude"] - LON_CENTER)
        a = sin(dlat/2)**2 + cos(radians(LAT_CENTER))*cos(radians(loc["latitude"]))*sin(dlon/2)**2
        d = 2 * 6371000 * atan2(sqrt(a), sqrt(1-a))
        return d <= RADIUS
    return False

# ================= TIME =================
def now():
    return datetime.datetime.now(VN_TZ)

def today():
    return now().strftime("%d/%m/%Y")

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

def lesson_calc(shift,f,t):
    allowed = range(1,6) if shift=="Sáng" else [7,8,9,10,11]
    arr=[x for x in allowed if f<=x<=t]
    return arr, LESSON[arr[0]][0], LESSON[arr[-1]][1]

# ================= MENU =================
menu = st.sidebar.radio("",["Giảng viên","Sinh viên","Quản trị"])

st.markdown("<div class='main-container'>", unsafe_allow_html=True)

# ================= GIẢNG VIÊN =================
if menu=="Giảng viên":
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Điểm danh giảng viên")

    msgv = st.text_input("MSGV")
    name = st.text_input("Họ tên")
    ca = st.selectbox("Ca",["Sáng","Chiều"])
    f = st.number_input("Tiết bắt đầu",1,11,1)
    t = st.number_input("Tiết kết thúc",1,11,3)

    arr,start,end = lesson_calc(ca,f,t)
    st.info(f"{arr} | {start} - {end}")

    if st.button("Check-in"):
        append(GV_SHEET,[today(),msgv,name,ca,f,t,len(arr),start,end,"IN",now().strftime("%H:%M:%S")])
        st.success("Thành công")

    if st.button("Check-out"):
        append(GV_SHEET,[today(),msgv,name,ca,"","","","","","OUT",now().strftime("%H:%M:%S")])
        st.success("Thành công")

    st.markdown("</div>", unsafe_allow_html=True)

# ================= SINH VIÊN =================
elif menu=="Sinh viên":
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Điểm danh sinh viên")

    mssv = st.text_input("MSSV")
    name = st.text_input("Họ tên")
    ca = st.selectbox("Ca",["Sáng","Chiều"])
    f = st.number_input("Tiết bắt đầu",1,11,1)
    t = st.number_input("Tiết kết thúc",1,11,3)

    arr,start,end = lesson_calc(ca,f,t)
    st.info(f"{arr} | {start} - {end}")

    if st.button("Check-in SV"):
        append(SV_SHEET,[today(),mssv,name,ca,f,t,len(arr),start,end,"IN",now().strftime("%H:%M:%S")])
        st.success("Thành công")

    if st.button("Check-out SV"):
        append(SV_SHEET,[today(),mssv,name,ca,"","","","","","OUT",now().strftime("%H:%M:%S")])
        st.success("Thành công")

    st.markdown("</div>", unsafe_allow_html=True)

# ================= QUẢN TRỊ =================
else:
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Quản trị hệ thống")

    pw = st.text_input("Mật khẩu",type="password")

    if pw==ADMIN_PASSWORD:

        df_gv = load(GV_SHEET)
        df_sv = load(SV_SHEET)

        st.write("Thống kê GV")
        if not df_gv.empty:
            st.line_chart(df_gv.groupby("Ngày").size())
            st.dataframe(df_gv)

        st.write("Thống kê SV")
        if not df_sv.empty:
            st.line_chart(df_sv.groupby("Ngày").size())
            st.dataframe(df_sv)

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ================= FOOTER =================
st.markdown("""
<div class="footer">
ĐẠI HỌC Y DƯỢC TP. HỒ CHÍ MINH<br>
ĐC: 217 Hồng Bàng, TP.HCM<br>
ĐT: 028 3855 8411<br>
Email: hanhchinh@ump.edu.vn
</div>
""", unsafe_allow_html=True)
