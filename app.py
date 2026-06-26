import streamlit as st
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(layout="centered")

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

@st.cache_data(ttl=5)
def load(k):
    return pd.DataFrame(sheet(k).get_all_records())

def append(k, row):
    sheet(k).append_row(row)

# ================= TIME =================
def now():
    return datetime.datetime.now(VN_TZ)

def today():
    return now().strftime("%d/%m/%Y")

def hhmmss():
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

# ================= ENGINE =================
def calc_lessons(ca, start, end):
    allowed = range(1,6) if ca=="Sáng" else [7,8,9,10,11]
    arr = [x for x in allowed if start <= x <= end]
    start_time = LESSON[arr[0]][0]
    end_time = LESSON[arr[-1]][1]
    return arr, start_time, end_time

def to_min(t):
    h,m = map(int, t.split(":"))
    return h*60 + m

def late_min(start_time):
    return max(0, now().hour*60+now().minute - to_min(start_time))

def required_min(n):
    base = n*50
    if n > 3:
        base += 15
    return base

def can_out(checkin_time, need):
    t = datetime.datetime.strptime(checkin_time, "%H:%M:%S").time()
    dt = datetime.datetime.combine(now().date(), t, VN_TZ)
    worked = (now()-dt).total_seconds()/60
    return worked >= need

# ================= FORM =================
def attendance_form(label_code, SHEET):

    code = st.text_input(label_code)

    ca = st.selectbox("Ca", ["Sáng","Chiều"])

    c1,c2 = st.columns(2)
    with c1:
        start = st.number_input("Tiết bắt đầu",1,11,1)
    with c2:
        end = st.number_input("Tiết kết thúc",1,11,3)

    arr,s,e = calc_lessons(ca,start,end)

    st.info(f"{arr} | {s} - {e}")

    col1,col2 = st.columns(2)

    # ===== IN =====
    with col1:
        if st.button("Check-in", use_container_width=True):

            late = late_min(s)

            append(SHEET,[
                today(), code, ca,
                start, end, len(arr),
                s, e,
                late,
                "IN",
                hhmmss()
            ])

            st.success(f"Đã vào ca - muộn {late} phút")

    # ===== OUT =====
    with col2:
        if st.button("Check-out", use_container_width=True):

            df = load(SHEET)

            last = df[
                (df[label_code] == code) &
                (df["IN/OUT"] == "IN")
            ]

            if last.empty:
                st.error("Chưa check-in")
                return

            last = last.iloc[-1]

            need = required_min(int(last["Số tiết"]))

            if not can_out(last["Giờ"], need):
                st.error("Chưa đủ thời gian")
                return

            append(SHEET,[
                today(), code, ca,
                "", "", "", "", "",
                "",
                "OUT",
                hhmmss()
            ])

            st.success("Ra ca thành công")

# ================= MAIN =================
st.title("Hệ thống điểm danh")
st.image("h.png", width=150)

menu = st.radio("", ["Giảng viên","Sinh viên","Quản trị"])

if menu == "Giảng viên":
    st.subheader("Điểm danh giảng viên")
    attendance_form("MSGV", GV_SHEET)

elif menu == "Sinh viên":
    st.subheader("Điểm danh sinh viên")
    attendance_form("MSSV", SV_SHEET)

else:
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

        st.dataframe(df_gv)

# ================= FOOTER =================
st.markdown("""
<hr>
<p style='text-align:center'>
Đại học Y Dược TP.HCM - 217 Hồng Bàng
</p>
""", unsafe_allow_html=True)
