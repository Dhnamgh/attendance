import streamlit as st
import datetime, time
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from math import radians, sin, cos, sqrt, atan2

try:
    from streamlit_geolocation import streamlit_geolocation
except:
    streamlit_geolocation = None

# ================= CONFIG =================
st.set_page_config(layout="wide")

GV_SHEET = st.secrets["GV_SHEET"]
SV_SHEET = st.secrets["SV_SHEET"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

LAT_CENTER = st.secrets.get("LAT_CENTER", 10.754665)
LON_CENTER = st.secrets.get("LON_CENTER", 106.663381)
RADIUS = st.secrets.get("RADIUS", 100)

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# ================= CSS =================
st.markdown("""
<style>

.block-container {
    padding:0 !important;
}
header[data-testid="stHeader"] {display:none;}

/* HEADER */
.header-bar {
    height:70px;
    background:#2c6b95;
    display:flex;
    align-items:center;
    justify-content:center;
    position:relative;
}
.logo {
    position:absolute;
    left:20px;
    height:45px;
}
.title {
    color:white;
    font-size:26px;
    font-weight:600;
}

/* SIDEBAR */
section[data-testid="stSidebar"] {
    background:#2c6b95;
}
section[data-testid="stSidebar"] * {
    color:white;
}

/* CONTENT */
.container {
    max-width:1100px;
    margin:auto;
    padding:25px;
}
.card {
    background:white;
    padding:20px;
    border-radius:8px;
    box-shadow:0 2px 8px rgba(0,0,0,0.1);
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

# ================= HEADER =================
st.markdown("""
<div class="header-bar">
    <img src="h.png" class="logo">
    <div class="title">HỆ THỐNG ĐIỂM DANH</div>
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

def lesson_info(shift, f, t):
    arr = [x for x in (range(1,6) if shift=="Sáng" else [7,8,9,10,11]) if f<=x<=t]
    return arr, LESSON[arr[0]][0], LESSON[arr[-1]][1]

def late(start):
    h,m = map(int,start.split(":"))
    return max(0, now().hour*60+now().minute - (h*60+m))

def req_minutes(n):
    return n*50 + (15 if n>3 else 0)

# ================= UI =================
menu = st.sidebar.radio("",["Giảng viên","Sinh viên","Quản trị"])

st.markdown("<div class='container'>", unsafe_allow_html=True)

# ================= GV =================
if menu=="Giảng viên":
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Điểm danh giảng viên")

    msgv = st.text_input("MSGV", key="gv_msgv")
    name = st.text_input("Họ tên", key="gv_name")
    shift = st.selectbox("Ca",["Sáng","Chiều"])
    f = st.number_input("Tiết bắt đầu",1,11,1)
    t = st.number_input("Tiết kết thúc",1,11,3)

    arr,start,end = lesson_info(shift,f,t)
    st.info(f"{arr} | {start} - {end}")

    if st.button("Check-in"):
        if not check_location():
            st.error("Sai vị trí")
        else:
            append(GV_SHEET,[
                today(),msgv,name,shift,
                f,t,len(arr),start,end,
                late(start),"IN",now().strftime("%H:%M:%S")
            ])
            st.success("Đã check-in")

    if st.button("Check-out"):
        df = load(GV_SHEET)
        last = df[(df["MSGV"]==msgv)&(df["IN/OUT"]=="IN")]
        if not last.empty:
            last = last.iloc[-1]
            if (now()-datetime.datetime.strptime(last["Giờ"],"%H:%M:%S").replace(
                year=now().year,month=now().month,day=now().day
            )).total_seconds()/60 >= req_minutes(int(last["Số tiết"])):
                append(GV_SHEET,[today(),msgv,name,"","","","","","","","OUT",now().strftime("%H:%M:%S")])
                st.success("Ra ca")
            else:
                st.error("Chưa đủ thời gian")

    st.markdown("</div>", unsafe_allow_html=True)

# ================= SV =================
elif menu=="Sinh viên":
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Điểm danh sinh viên")

    mssv = st.text_input("MSSV")
    name = st.text_input("Họ tên")

    if st.button("Check-in SV"):
        append(SV_SHEET,[today(),mssv,name,"IN",now().strftime("%H:%M:%S")])
        st.success("Đã vào")

    if st.button("Check-out SV"):
        append(SV_SHEET,[today(),mssv,name,"OUT",now().strftime("%H:%M:%S")])
        st.success("Đã ra")

    st.markdown("</div>", unsafe_allow_html=True)

# ================= ADMIN =================
else:
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Quản trị hệ thống")

    pw = st.text_input("Mật khẩu",type="password")

    if pw==ADMIN_PASSWORD:

        df_gv = load(GV_SHEET)
        df_sv = load(SV_SHEET)

        st.write("Thống kê tổng")
        col1,col2=st.columns(2)
        col1.metric("GV",len(df_gv))
        col2.metric("SV",len(df_sv))

        if not df_gv.empty:
            st.write("GV theo ngày")
            st.line_chart(df_gv.groupby("Ngày").size())

        if not df_sv.empty:
            st.write("SV theo ngày")
            st.line_chart(df_sv.groupby("Ngày").size())

        st.dataframe(df_gv)

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
