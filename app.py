import streamlit as st
import time, datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

try:
    from streamlit_geolocation import streamlit_geolocation
except:
    streamlit_geolocation = None

from math import radians, sin, cos, sqrt, atan2

# ================= CONFIG =================
st.set_page_config(page_title="Attendance System", layout="wide")

GV_SHEET = st.secrets["GV_SHEET"]
SV_SHEET = st.secrets["SV_SHEET"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

LAT_CENTER = st.secrets.get("LAT_CENTER", 10.754665)
LON_CENTER = st.secrets.get("LON_CENTER", 106.663381)
RADIUS = st.secrets.get("RADIUS", 100)

# ================= CSS =================
st.markdown("""
<style>
.main {
    background-color: #f3f6f9;
}

/* HEADER */
.header {
    background-color: #1b5e8c;
    padding: 10px;
    color: white;
    display: flex;
    align-items: center;
}

.header img {
    height: 50px;
    margin-right: 15px;
}

/* SIDEBAR */
section[data-testid="stSidebar"] {
    background-color: #1b5e8c;
}

section[data-testid="stSidebar"] * {
    color: white !important;
    font-weight: bold;
}

/* CARD */
.card {
    background-color: white;
    padding: 20px;
    border-radius: 10px;
    box-shadow: 0px 2px 6px rgba(0,0,0,0.1);
}

/* FOOTER */
.footer {
    background-color: #1f2557;
    color: white;
    padding: 20px;
    margin-top: 40px;
}

</style>
""", unsafe_allow_html=True)

# ================= HEADER =================
st.markdown(f"""
<div class="header">
    <img src="https://raw.githubusercontent.com/dao-hong-nam/temp-assets/main/h.png">
    <h2>HỆ THỐNG ĐIỂM DANH</h2>
</div>
""", unsafe_allow_html=True)

# ================= GOOGLE =================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

@st.cache_resource
def client():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["google_service_account"]),
        scopes=SCOPES
    )
    return gspread.authorize(creds)

def sheet(key):
    return client().open_by_key(key).sheet1

@st.cache_data(ttl=5)
def load(key):
    return sheet(key).get_all_records()

def append(key, row):
    sheet(key).append_row(row)

# ================= GPS =================
def distance(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

def check_location():
    if not streamlit_geolocation:
        return True

    loc = streamlit_geolocation()
    if loc and loc.get("latitude"):
        d = distance(
            LAT_CENTER, LON_CENTER,
            loc["latitude"], loc["longitude"]
        )
        return d <= RADIUS
    return False

# ================= CARD TEMPLATE =================
def card(title, func):
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader(title)
    func()
    st.markdown("</div>", unsafe_allow_html=True)

# ================= VIEWS =================

def student_view():
    def content():
        mssv = st.text_input("MSSV", key="sv_mssv")
        name = st.text_input("Họ tên", key="sv_name")

        if st.button("Check-in", key="sv_in"):
            if not check_location():
                st.error("Ngoài khu vực")
                return
            append(SV_SHEET, ["IN", mssv, name, str(datetime.datetime.now())])
            st.success("Thành công")

        if st.button("Check-out", key="sv_out"):
            append(SV_SHEET, ["OUT", mssv, "", str(datetime.datetime.now())])
            st.success("Thành công")

    card("Điểm danh sinh viên", content)

def lecturer_view():
    def content():
        msgv = st.text_input("MSGV", key="gv_msgv")
        name = st.text_input("Họ tên", key="gv_name")

        if st.button("Check-in", key="gv_in"):
            if not check_location():
                st.error("Ngoài khu vực")
                return
            append(GV_SHEET, ["IN", msgv, name, str(datetime.datetime.now())])
            st.success("Thành công")

        if st.button("Check-out", key="gv_out"):
            append(GV_SHEET, ["OUT", msgv, "", str(datetime.datetime.now())])
            st.success("Thành công")

    card("Điểm danh giảng viên", content)

def admin_view():
    def content():
        pw = st.text_input("Mật khẩu", type="password", key="admin_pw")

        if pw == ADMIN_PASSWORD:
            st.write("Dữ liệu sinh viên")
            st.dataframe(pd.DataFrame(load(SV_SHEET)))

            st.write("Dữ liệu giảng viên")
            st.dataframe(pd.DataFrame(load(GV_SHEET)))
        else:
            st.warning("Chưa đăng nhập")

    card("Quản trị hệ thống", content)

# ================= SIDEBAR =================
menu = st.sidebar.radio(
    "",
    ["Giảng viên", "Sinh viên", "Quản trị"],
    key="menu_main"
)

# ================= MAIN =================
if menu == "Sinh viên":
    student_view()

elif menu == "Giảng viên":
    lecturer_view()

elif menu == "Quản trị":
    admin_view()

# ================= FOOTER =================
st.markdown("""
<div class="footer">
<b>ĐẠI HỌC Y DƯỢC TP. HỒ CHÍ MINH</b><br>
ĐC: 217 Hồng Bàng, TP.HCM<br>
ĐT: 028 3855 8411<br>
Email: hanhchinh@ump.edu.vn
</div>
""", unsafe_allow_html=True)
