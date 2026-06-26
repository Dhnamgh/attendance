import streamlit as st
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ================= CONFIG =================
st.set_page_config(layout="wide")

GV_SHEET = st.secrets["GV_SHEET"]
SV_SHEET = st.secrets["SV_SHEET"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# ================= CSS =================
st.markdown("""
<style>

/* RESET */
.block-container {padding:0!important;}
header[data-testid="stHeader"]{display:none}

/* HEADER */
.header {
    position:fixed;
    top:0;
    left:0;
    right:0;
    height:70px;
    background:#2c6b95;
    display:flex;
    align-items:center;
    justify-content:center;
    z-index:999;
}
.header img {
    position:absolute;
    left:15px;
    height:50px;
}
.header-title {
    color:white;
    font-size:24px;
    font-weight:600;
}

/* SIDEBAR */
section[data-testid="stSidebar"]{
    background:#2c6b95!important;
    width:220px!important;
}
section[data-testid="stSidebar"] *{
    color:white!important;
    font-size:17px!important;
}

/* CONTENT */
.main-space{
    margin-top:80px;
    max-width:1000px;
    margin-left:auto;
    margin-right:auto;
    padding:15px;
}

/* CARD */
.card{
    background:white;
    padding:18px;
    border-radius:8px;
    margin-bottom:20px;
}

/* INPUT */
input,select{
    font-size:16px!important;
}

/* BUTTON */
button{
    font-size:16px!important;
    margin-top:10px;
}

/* FOOTER FIXED */
.footer{
    position:fixed;
    bottom:0;
    left:0;
    right:0;
    background:#2b2f65;
    color:white;
    padding:12px;
    text-align:center;
    font-size:13px;
}

/* MOBILE */
@media (max-width:768px){
    .header-title{font-size:18px}
    .main-space{padding:10px}
    section[data-testid="stSidebar"]{width:160px!important}
}

</style>
""", unsafe_allow_html=True)

# ================= HEADER =================
st.markdown("""
<div class="header">
    <img src="h.png">
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

def load(key):
    return pd.DataFrame(sheet(key).get_all_records())

def append(key,row):
    sheet(key).append_row(row)

# ================= TIME =================
def now():
    return datetime.datetime.now(VN_TZ)

def today():
    return now().strftime("%d/%m/%Y")

# ================= LESSON =================
LESSON = {
    1:("07:00","07:50"),2:("07:50","08:40"),
    3:("08:40","09:30"),4:("09:45","10:35"),
    5:("10:35","11:25"),7:("13:00","13:50"),
    8:("13:50","14:40"),9:("14:40","15:30"),
    10:("15:45","16:35"),11:("16:35","17:25")
}

def lesson_calc(shift,f,t):
    allowed = range(1,6) if shift=="Sáng" else [7,8,9,10,11]
    arr=[x for x in allowed if f<=x<=t]
    return arr, LESSON[arr[0]][0], LESSON[arr[-1]][1]

# ================= MENU =================
menu = st.sidebar.radio(
    "",
    ["Giảng viên","Sinh viên","Quản trị"],
    key="menu"
)

# ================= CONTENT =================
st.markdown("<div class='main-space'>", unsafe_allow_html=True)

# ================= GV =================
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
        st.success("Đã vào ca")

    if st.button("Check-out"):
        append(GV_SHEET,[today(),msgv,name,ca,"","","","","","OUT",now().strftime("%H:%M:%S")])
        st.success("Đã ra ca")

    st.markdown("</div>", unsafe_allow_html=True)

# ================= SV =================
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
        st.success("Đã vào")

    if st.button("Check-out SV"):
        append(SV_SHEET,[today(),mssv,name,ca,"","","","","","OUT",now().strftime("%H:%M:%S")])
        st.success("Đã ra")

    st.markdown("</div>", unsafe_allow_html=True)

# ================= ADMIN =================
else:
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Quản trị hệ thống")

    pw = st.text_input("Mật khẩu",type="password")

    if pw == ADMIN_PASSWORD:
        df_gv = load(GV_SHEET)
        df_sv = load(SV_SHEET)

        st.write("Thống kê giảng viên")
        if not df_gv.empty:
            st.line_chart(df_gv.groupby("Ngày").size())
            st.dataframe(df_gv)

        st.write("Thống kê sinh viên")
        if not df_sv.empty:
            st.line_chart(df_sv.groupby("Ngày").size())
            st.dataframe(df_sv)

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ================= FOOTER =================
st.markdown("""
<div class="footer">
ĐẠI HỌC Y DƯỢC TP. HỒ CHÍ MINH - 217 Hồng Bàng - Phone: 028 3855 8411
</div>
""", unsafe_allow_html=True)
