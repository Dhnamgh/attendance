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
.block-container {padding-top:0;padding-bottom:0;}
header[data-testid="stHeader"] {display:none;}

section[data-testid="stSidebar"] {
    background-color:#2b628c;
}
section[data-testid="stSidebar"] * {
    color:white;
}

.card {
    background:white;
    padding:20px;
    border-radius:8px;
    box-shadow:0 2px 6px rgba(0,0,0,0.1);
    margin-bottom:20px;
}

.footer {
    background:#252d61;
    color:white;
    padding:20px;
    margin-top:30px;
}
</style>
""", unsafe_allow_html=True)

# ================= HEADER =================
col1, col2 = st.columns([1,8])
with col1:
    st.image("h.png", width=70)
with col2:
    st.markdown("<h2>HỆ THỐNG ĐIỂM DANH</h2>", unsafe_allow_html=True)

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

@st.cache_data(ttl=10)
def load(key):
    return pd.DataFrame(sheet(key).get_all_records())

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
        d = distance(LAT_CENTER, LON_CENTER, loc["latitude"], loc["longitude"])
        return d <= RADIUS
    return False

# ================= TIME =================
def now():
    return datetime.datetime.now(VN_TZ)

def now_str():
    return now().strftime("%Y-%m-%d %H:%M:%S")

def today_str():
    return now().strftime("%d/%m/%Y")

# ================= LESSON ENGINE =================
LESSON_SCHEDULE = {
    1: ("07:00", "07:50"),
    2: ("07:50", "08:40"),
    3: ("08:40", "09:30"),
    4: ("09:45", "10:35"),
    5: ("10:35", "11:25"),
    7: ("13:00", "13:50"),
    8: ("13:50", "14:40"),
    9: ("14:40", "15:30"),
    10: ("15:45", "16:35"),
    11: ("16:35", "17:25"),
}

MORNING = [1,2,3,4,5]
AFTERNOON = [7,8,9,10,11]

def lesson_range(shift, l_from, l_to):
    allowed = MORNING if shift == "Sáng" else AFTERNOON
    l_from = max(min(l_from, max(allowed)), min(allowed))
    l_to = max(min(l_to, max(allowed)), l_from)
    sel = [x for x in allowed if l_from <= x <= l_to]
    start = LESSON_SCHEDULE[sel[0]][0]
    end = LESSON_SCHEDULE[sel[-1]][1]
    return sel, start, end

def required_minutes(n):
    base = n * 50
    if n > 3:
        base += 15
    return base

def compute_late(start):
    h,m = map(int,start.split(":"))
    start_m = h*60+m
    now_m = now().hour*60+now().minute
    return max(0, now_m-start_m)

def can_checkout(start_hms, req):
    t = datetime.datetime.strptime(start_hms, "%H:%M:%S").time()
    st_dt = datetime.datetime.combine(now().date(), t, VN_TZ)
    worked = (now()-st_dt).total_seconds()/60
    return worked >= req

# ================= CARD =================
def card(title, func):
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader(title)
    func()
    st.markdown("</div>", unsafe_allow_html=True)

# ================= STUDENT =================
def student_view():
    def content():
        mssv = st.text_input("MSSV", key="sv_mssv")
        name = st.text_input("Họ tên", key="sv_name")

        if st.button("Check-in", key="sv_in"):
            if not check_location():
                st.error("Ngoài khu vực")
                return
            append(SV_SHEET, [today_str(), mssv, name, "IN", now_str()])
            st.success("Thành công")

        if st.button("Check-out", key="sv_out"):
            append(SV_SHEET, [today_str(), mssv, name, "OUT", now_str()])
            st.success("Thành công")
    card("Điểm danh sinh viên", content)

# ================= LECTURER =================
def lecturer_view():
    def content():
        msgv = st.text_input("MSGV", key="gv_msgv")
        name = st.text_input("Họ tên", key="gv_name")

        shift = st.selectbox("Ca", ["Sáng", "Chiều"], key="gv_shift")
        l_from = st.number_input("Tiết bắt đầu", 1, 11, 1, key="gv_from")
        l_to = st.number_input("Tiết kết thúc", 1, 11, 3, key="gv_to")

        lessons, start, end = lesson_range(shift, l_from, l_to)
        st.info(f"{lessons} | {start} - {end}")

        if st.button("Check-in", key="gv_in"):
            if not check_location():
                st.error("Ngoài khu vực")
                return
            late = compute_late(start)
            append(GV_SHEET, [
                today_str(), msgv, name, shift,
                l_from, l_to, len(lessons),
                start, end, late, "IN", now().strftime("%H:%M:%S")
            ])
            st.success(f"Muộn: {late} phút")

        if st.button("Check-out", key="gv_out"):
            df = load(GV_SHEET)
            last = df[(df["MSGV"]==msgv) & (df["IN/OUT"]=="IN")]
            if last.empty:
                st.error("Chưa có IN")
                return
            last = last.iloc[-1]
            req = required_minutes(int(last["Số tiết"]))
            if not can_checkout(last["Giờ"], req):
                st.error("Chưa đủ giờ")
                return
            append(GV_SHEET, [
                today_str(), msgv, name, shift,
                "", "", "", "", "", "", "OUT", now().strftime("%H:%M:%S")
            ])
            st.success("Ra ca thành công")

    card("Điểm danh giảng viên", content)

# ================= DASHBOARD =================
def dashboard_view():

    def content():

        df_gv = load(GV_SHEET)
        df_sv = load(SV_SHEET)

        st.subheader("Tổng quan")

        col1, col2, col3 = st.columns(3)

        col1.metric("Tổng log GV", len(df_gv))
        col2.metric("Tổng log SV", len(df_sv))
        col3.metric("Hôm nay", today_str())

        # ==== GV ANALYTICS ====
        if not df_gv.empty:

            df_gv["date"] = df_gv["Ngày"]
            df_gv["type"] = df_gv["IN/OUT"]

            st.subheader("Giảng viên")

            by_day = df_gv.groupby("date").size()
            st.line_chart(by_day)

            by_type = df_gv.groupby("type").size()
            st.bar_chart(by_type)

            late = df_gv[df_gv["Muộn"] != ""]
            if not late.empty:
                late["Muộn"] = pd.to_numeric(late["Muộn"], errors="coerce")
                st.write("Top vào muộn")
                st.dataframe(late.sort_values("Muộn", ascending=False).head(10))

        # ==== SV ANALYTICS ====
        if not df_sv.empty:

            st.subheader("Sinh viên")

            df_sv["date"] = df_sv["Ngày"]
            by_day_sv = df_sv.groupby("date").size()
            st.line_chart(by_day_sv)

            by_status = df_sv.groupby("IN/OUT").size()
            st.bar_chart(by_status)

    card("Dashboard tổng hợp", content)

# ================= ADMIN =================
def admin_view():
    def content():
        pw = st.text_input("Mật khẩu", type="password", key="admin_pw")
        if pw == ADMIN_PASSWORD:
            dashboard_view()
        else:
            st.warning("Chưa đăng nhập")
    card("Quản trị", content)

# ================= SIDEBAR =================
menu = st.sidebar.radio(
    "",
    ["Giảng viên", "Sinh viên", "Quản trị"],
    key="menu"
)

# ================= MAIN =================
if menu == "Giảng viên":
    lecturer_view()
elif menu == "Sinh viên":
    student_view()
else:
    admin_view()

# ================= FOOTER =================
st.markdown("""
<div class="footer">
ĐẠI HỌC Y DƯỢC TP. HỒ CHÍ MINH<br>
ĐC: 217 Hồng Bàng, TP.HCM<br>
ĐT: 028 3855 8411<br>
Email: hanhchinh@ump.edu.vn
</div>
""", unsafe_allow_html=True)
