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

# ================= CSS NHẸ (KHÔNG PHÁ) =================
st.markdown("""
<style>

/* chỉ style màu, không override position */
section[data-testid="stSidebar"] {
    background: #2c6b95;
}
section[data-testid="stSidebar"] * {
    color: white;
}

/* title */
.main-title {
    font-size:26px;
    font-weight:600;
    text-align:center;
    margin-bottom:20px;
}

/* card */
.card {
    background:white;
    padding:20px;
    border-radius:10px;
    margin-top:20px;
}

/* mobile */
@media (max-width:768px){
    .main-title {font-size:20px;}
}

</style>
""", unsafe_allow_html=True)

# ================= HEADER =================
st.markdown("<div class='main-title'>HỆ THỐNG ĐIỂM DANH</div>", unsafe_allow_html=True)

# ================= SIDEBAR =================

# ✅ CÁI NÀY LÀ ĐOẠN QUYẾT ĐỊNH LOGO
st.sidebar.image("h.png", use_container_width=True)

menu = st.sidebar.radio(
    "",
    ["Giảng viên","Sinh viên","Quản trị"]
)

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

# ================= LESSON =================
LESSON = {
    1:("07:00","07:50"),2:("07:50","08:40"),
    3:("08:40","09:30"),4:("09:45","10:35"),
    5:("10:35","11:25"),7:("13:00","13:50"),
    8:("13:50","14:40"),9:("14:40","15:30"),
    10:("15:45","16:35"),11:("16:35","17:25")
}

def calc(shift,f,t):
    allowed = range(1,6) if shift=="Sáng" else [7,8,9,10,11]
    arr=[x for x in allowed if f<=x<=t]
    return arr, LESSON[arr[0]][0], LESSON[arr[-1]][1]

# ================= GIẢNG VIÊN =================
if menu=="Giảng viên":
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Điểm danh giảng viên")

    msgv = st.text_input("MSGV")
    name = st.text_input("Họ tên")
    ca = st.selectbox("Ca",["Sáng","Chiều"])
    f = st.number_input("Tiết bắt đầu",1,11,1)
    t = st.number_input("Tiết kết thúc",1,11,3)

    arr,s,e = calc(ca,f,t)
    st.info(f"{arr} | {s} - {e}")

    if st.button("Check-in"):
        append(GV_SHEET,[today(),msgv,name,ca,f,t,len(arr),s,e,"IN",now().strftime("%H:%M:%S")])

    if st.button("Check-out"):
        append(GV_SHEET,[today(),msgv,name,ca,"","","","","","OUT",now().strftime("%H:%M:%S")])

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

    arr,s,e = calc(ca,f,t)
    st.info(f"{arr} | {s} - {e}")

    if st.button("Check-in SV"):
        append(SV_SHEET,[today(),mssv,name,ca,f,t,len(arr),s,e,"IN",now().strftime("%H:%M:%S")])

    if st.button("Check-out SV"):
        append(SV_SHEET,[today(),mssv,name,ca,"","","","","","OUT",now().strftime("%H:%M:%S")])

    st.markdown("</div>", unsafe_allow_html=True)

# ================= ADMIN =================
else:
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    st.subheader("Quản trị")

    pw = st.text_input("Mật khẩu", type="password")

    if pw == ADMIN_PASSWORD:

        df_gv = load(GV_SHEET)
        df_sv = load(SV_SHEET)

        st.write("Giảng viên")
        if not df_gv.empty:
            st.line_chart(df_gv.groupby("Ngày").size())

        st.write("Sinh viên")
        if not df_sv.empty:
            st.line_chart(df_sv.groupby("Ngày").size())

    st.markdown("</div>", unsafe_allow_html=True)

# ================= FOOTER =================
st.markdown("""
<hr>
<p style='text-align:center;font-size:13px'>
Đại học Y Dược TP.HCM - 217 Hồng Bàng
</p>
""", unsafe_allow_html=True)
