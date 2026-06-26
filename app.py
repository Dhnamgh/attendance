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

# ✅ LẤY TỪ SECRETS (KHÔNG HARD-CODE)
GV_SHEET = st.secrets["GV_SHEET"]
SV_SHEET = st.secrets["SV_SHEET"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

LAT_CENTER = st.secrets.get("LAT_CENTER", 10.754665)
LON_CENTER = st.secrets.get("LON_CENTER", 106.663381)
RADIUS = st.secrets.get("RADIUS", 100)

QR_TTL = 30

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
        st.warning("Không có module GPS")
        return False

    loc = streamlit_geolocation()

    if loc and loc.get("latitude"):
        d = distance(
            LAT_CENTER, LON_CENTER,
            loc["latitude"], loc["longitude"]
        )
        return d <= RADIUS

    st.warning("Không lấy được vị trí")
    return False

# ================= TOKEN =================
def token():
    return int(time.time() // QR_TTL)

# ================= CHECK-IN =================
def checkin(sheet_id, id_value, name):

    data = load(sheet_id)
    df = pd.DataFrame(data)

    if id_value not in df.iloc[:, 0].astype(str).values:
        st.error("Không tồn tại trong danh sách")
        return

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    append(sheet_id, ["LOG", id_value, name, "IN", now])

    st.success("Check-in thành công")

def checkout(sheet_id, id_value):

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    append(sheet_id, ["LOG", id_value, "", "OUT", now])

    st.success("Check-out thành công")

# ================= STUDENT =================
def student_view():

    st.subheader("Sinh viên")

    mssv = st.text_input("MSSV")
    name = st.text_input("Họ tên")

    if st.button("Check-in"):
        if not check_location():
            st.error("Ngoài khu vực cho phép")
            return
        checkin(SV_SHEET, mssv, name)

    if st.button("Check-out"):
        checkout(SV_SHEET, mssv)

# ================= LECTURER =================
def lecturer_view():

    st.subheader("Giảng viên")

    msgv = st.text_input("MSGV")
    name = st.text_input("Họ tên")

    if st.button("Check-in"):
        if not check_location():
            st.error("Ngoài khu vực cho phép")
            return
        checkin(GV_SHEET, msgv, name)

    if st.button("Check-out"):
        checkout(GV_SHEET, msgv)

# ================= QR =================
def qr_view():

    import qrcode, io
    from PIL import Image

    st.subheader("QR và Link")

    role = st.selectbox("Loại", ["SV", "GV"])
    placeholder = st.empty()

    while True:
        t = token()
        url = f"?role={role}&t={t}"

        qr = qrcode.make(url)

        buf = io.BytesIO()
        qr.save(buf)
        buf.seek(0)

        placeholder.image(Image.open(buf), width=250)
        st.caption(url)

        time.sleep(1)

# ================= ADMIN =================
def admin_view():

    pw = st.text_input("Mật khẩu", type="password")

    if pw != ADMIN_PASSWORD:
        return

    st.success("Đã đăng nhập")

    st.write("Dữ liệu Sinh viên")
    st.dataframe(pd.DataFrame(load(SV_SHEET)))

    st.write("Dữ liệu Giảng viên")
    st.dataframe(pd.DataFrame(load(GV_SHEET)))

# ================= MAIN =================

tab1, tab2, tab3, tab4 = st.tabs([
    "Sinh viên",
    "Giảng viên",
    "QR",
    "Quản trị"
])

with tab1:
    student_view()

with tab2:
    lecturer_view()

with tab3:
    qr_view()

with tab4:
    admin_view()
