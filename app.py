import streamlit as st
import time, datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import qrcode, io
from PIL import Image

# ================= CONFIG =================
st.set_page_config(page_title="Attendance System", layout="wide")

QR_TTL = 30
SESSION_TTL = 120

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_KEY = st.secrets["SHEET_KEY"]

# ================= GOOGLE =================
@st.cache_resource
def client():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["google_service_account"]),
        scopes=SCOPES
    )
    return gspread.authorize(creds)

def sheet(name):
    return client().open_by_key(SHEET_KEY).worksheet(name)

@st.cache_data(ttl=5)
def load(name):
    return sheet(name).get_all_records()

def append(name, row):
    sheet(name).append_row(row)

# ================= TOKEN =================
def token():
    return int(time.time() // QR_TTL)

def valid(t):
    try:
        return abs(int(t) - token()) <= 1
    except:
        return False

# ================= STUDENT =================
def student_view():
    qp = st.query_params

    if qp.get("sv") != "1":
        st.info("Quét mã hoặc mở link để điểm danh")
        return

    class_id = qp.get("class", "D25C")
    session = qp.get("session", "Buổi 1")
    t = qp.get("t")

    st.title(f"🎓 {class_id} - {session}")

    key = f"{class_id}_{session}"
    now = time.time()

    if key not in st.session_state:
        if not valid(t):
            st.error("Link điểm danh đã hết hạn")
            return
        st.session_state[key] = now
    else:
        if now - st.session_state[key] > SESSION_TTL:
            st.warning("Hết phiên, vui lòng mở link mới")
            return

    mssv = st.text_input("MSSV")
    name = st.text_input("Họ tên")

    if st.button("✅ Check-in"):

        students = pd.DataFrame(load("STUDENTS"))
        logs = pd.DataFrame(load("LOG"))

        if mssv not in students["MSSV"].astype(str).values:
            st.error("MSSV không tồn tại")
            return

        if not logs.empty:
            dup = logs[
                (logs["MSSV"] == mssv) &
                (logs["Session"] == session)
            ]
            if not dup.empty:
                st.warning("Đã điểm danh rồi")
                return

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        append("LOG", [
            now_str, mssv, name, class_id, session, "IN"
        ])

        st.success("✅ Điểm danh thành công")

# ================= QR =================
def qr_view():
    st.subheader("📸 Tạo QR / Link điểm danh")

    class_id = st.selectbox("Class", ["D25C"])
    session = st.selectbox("Session", [f"Buổi {i}" for i in range(1,7)])

    placeholder = st.empty()

    while True:
        t = token()

        base_url = st.secrets.get("APP_URL", "")
        url = f"{base_url}/?sv=1&class={class_id}&session={session}&t={t}"

        qr = qrcode.make(url)
        buf = io.BytesIO()
        qr.save(buf)
        buf.seek(0)

        placeholder.image(Image.open(buf), width=250)

        st.caption(url)
        time.sleep(1)

# ================= DASHBOARD =================
def dashboard():
    st.subheader("📊 Dashboard")

    df = pd.DataFrame(load("LOG"))

    if df.empty:
        st.info("Chưa có dữ liệu")
        return

    st.metric("Tổng lượt điểm danh", len(df))

    st.bar_chart(df.groupby("Session").size())

# ================= MAIN =================
tab1, tab2, tab3 = st.tabs([
    "🎓 Sinh viên",
    "📸 QR",
    "📊 Dashboard"
])

with tab1:
    student_view()

with tab2:
    qr_view()

with tab3:
    dashboard()
