import streamlit as st
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ================= CONFIG =================
st.set_page_config(page_title="Attendance", layout="centered")

GV_SHEET = st.secrets["GV_SHEET"]
SV_SHEET = st.secrets["SV_SHEET"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

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

@st.cache_data(ttl=10)
def load(k):
    return pd.DataFrame(sheet(k).get_all_records())

def append(k, row):
    sheet(k).append_row(row)

# ================= TIME =================
def now():
    return datetime.datetime.now(VN_TZ)

def today():
    return now().strftime("%d/%m/%Y")

# ================= LESSON ENGINE =================
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

def calc_lessons(shift, start, end):
    if shift == "Sáng":
        allowed = range(1,6)
    else:
        allowed = [7,8,9,10,11]

    arr = [x for x in allowed if start <= x <= end]
    s = LESSON[arr[0]][0]
    e = LESSON[arr[-1]][1]

    return arr, s, e

# ================= UI =================
st.title("Hệ thống điểm danh")

# ✅ logo đặt đúng cách (an toàn)
st.image("h.png", width=220)

menu = st.sidebar.radio(
    "Chọn chức năng",
    ["Giảng viên", "Sinh viên", "Quản trị"]
)

# ================= FORM DÙNG CHUNG =================
def attendance_form(role, sheet_name):

    if role == "Giảng viên":
        code = st.text_input("MSGV")
    else:
        code = st.text_input("MSSV")

    name = st.text_input("Họ tên")

    shift = st.selectbox("Ca", ["Sáng", "Chiều"])

    c1, c2 = st.columns(2)
    with c1:
        start = st.number_input("Tiết bắt đầu", 1, 11, 1)
    with c2:
        end = st.number_input("Tiết kết thúc", 1, 11, 3)

    arr, s, e = calc_lessons(shift, start, end)

    st.info(f"{arr} | {s} - {e}")

    col1, col2 = st.columns(2)

    # ===== CHECK-IN =====
    with col1:
        if st.button("Check-in", use_container_width=True):
            append(sheet_name, [
                today(), code, name, shift,
                start, end, len(arr),
                s, e,
                "IN",
                now().strftime("%H:%M:%S")
            ])
            st.success("Đã check-in")

    # ===== CHECK-OUT =====
    with col2:
        if st.button("Check-out", use_container_width=True):
            append(sheet_name, [
                today(), code, name, shift,
                "", "", "", "", "",
                "OUT",
                now().strftime("%H:%M:%S")
            ])
            st.success("Đã check-out")

# ================= GIẢNG VIÊN =================
if menu == "Giảng viên":
    st.subheader("Điểm danh giảng viên")
    attendance_form("Giảng viên", GV_SHEET)

# ================= SINH VIÊN =================
elif menu == "Sinh viên":
    st.subheader("Điểm danh sinh viên")
    attendance_form("Sinh viên", SV_SHEET)

# ================= QUẢN TRỊ =================
else:
    st.subheader("Quản trị hệ thống")

    pw = st.text_input("Mật khẩu", type="password")

    if pw == ADMIN_PASSWORD:

        df_gv = load(GV_SHEET)
        df_sv = load(SV_SHEET)

        st.markdown("### Tổng quan")

        col1, col2 = st.columns(2)
        col1.metric("Tổng GV", len(df_gv))
        col2.metric("Tổng SV", len(df_sv))

        if not df_gv.empty:
            st.markdown("### Thống kê giảng viên")
            st.line_chart(df_gv.groupby("Ngày").size())

        if not df_sv.empty:
            st.markdown("### Thống kê sinh viên")
            st.line_chart(df_sv.groupby("Ngày").size())

        st.markdown("### Dữ liệu chi tiết")
        st.dataframe(df_gv, use_container_width=True)

# ================= FOOTER =================
st.markdown("""
<hr>
<p style='text-align:center;font-size:13px'>
Đại học Y Dược TP.HCM - 217 Hồng Bàng
</p>
""", unsafe_allow_html=True)
