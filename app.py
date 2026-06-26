# app.py
import os
import io
import re
import time
import base64
import urllib.parse
import unicodedata
import datetime

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image
import qrcode
import pandas as pd
import altair as alt

# Import các thư viện vệ tinh bảo đảm logic định vị của thầy
try:
    from streamlit_geolocation import streamlit_geolocation
except Exception:
    streamlit_geolocation = None

try:
    from geopy.distance import geodesic
except Exception:
    geodesic = None

st.set_page_config(layout="centered")

# ===================== TÙY CHỈNH GIAO DIỆN (FONT 16 & HÀNG NGANG) =====================
st.markdown(
    """
    <style>
    .custom-title {
        font-family: "Times New Roman", Times, serif;
        font-size: 21px; /* Tương đương cỡ 16pt Word */
        font-weight: bold;
        text-align: center;
        margin-bottom: 15px;
        color: #1E3A8A;
    }
    /* Đẩy thanh chọn Radio GV/SV thành hàng ngang lên trên cùng */
    div[data-testid="stRadio"] > div {
        flex-direction: row !important;
        justify-content: center !important;
        gap: 30px;
    }
    div[data-testid="stRadio"] label {
        font-size: 16px !important;
    }
    </style>
    <div class="custom-title">Hệ thống điểm danh tích hợp</div>
    """,
    unsafe_html=True
)

# ===================== CẤU HÌNH THỜI GIAN & TOẠ ĐỘ GỐC =====================
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
LAT_CENTER = 10.754665
LON_CENTER = 106.663381
RADIUS_METERS = 100

LESSON_MINUTES = 50
BREAK_AFTER_LESSONS = 3
BREAK_MINUTES = 15

LESSON_SCHEDULE = {
    1:  ("07:00", "07:50"),
    2:  ("07:50", "08:40"),
    3:  ("08:40", "09:30"),
    4:  ("09:45", "10:35"),
    5:  ("10:35", "11:25"),
    6:  ("11:25", "12:15"),
    7:  ("13:00", "13:50"),
    8:  ("13:50", "14:40"),
    9:  ("14:40", "15:30"),
    10: ("15:45", "16:35"),
    11: ("16:35", "17:25"),
    12: ("17:25", "18:15")
}

# Lấy cấu hình các biến Sheet từ Secrets của thầy
try:
    GV_SHEET_KEY = st.secrets["GV_SHEET"]
    SV_SHEET_KEY = st.secrets["SV_SHEET"]
    STAFF_SHEET_NAME = st.secrets.get("STAFF_SHEET_NAME", "NhanSu")
    LOG_SHEET_NAME = st.secrets.get("LOG_SHEET_NAME", "Log")
except Exception:
    st.error("Thiếu cấu hình GV_SHEET hoặc SV_SHEET trong mục Streamlit Secrets!")
    st.stop()

# ===================== KẾT NỐI GOOGLE SHEET =====================
@st.cache_resource
def get_gspread_client():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["google_service_account"]),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(creds)

def get_workspace_sheets(sheet_key):
    client = get_gspread_client()
    sh = client.open_by_key(sheet_key)
    
    # Đảm bảo có sheet nhân sự/sinh viên và sheet ghi log
    try:
        sw = sh.worksheet(STAFF_SHEET_NAME)
    except gspread.WorksheetNotFound:
        sw = sh.sheet1
    try:
        lw = sh.worksheet(LOG_SHEET_NAME)
    except gspread.WorksheetNotFound:
        lw = sh.add_worksheet(title=LOG_SHEET_NAME, rows=1000, cols=20)
    return sw, lw

# ===================== LOGIC THỜI GIAN CHUẨN =====================
def get_now_vn():
    return datetime.datetime.now(VN_TZ)

def parse_time_str(s):
    h, m = map(int, s.split(":"))
    return h, m

def get_lesson_interval(ca, bat_dau, ket_thuc):
    if bat_dau > ket_thuc:
        bat_dau, ket_thuc = ket_thuc, bat_dau
    
    start_str = LESSON_SCHEDULE.get(bat_dau, ("07:00", "07:50"))[0]
    end_str = LESSON_SCHEDULE.get(ket_thuc, ("07:00", "07:50"))[1]
    
    # Tính tổng số tiết đứng lớp thực tế
    count = 0
    for idx in range(bat_dau, ket_thuc + 1):
        if idx in LESSON_SCHEDULE:
            count += 1
            
    return start_str, end_str, count

def calc_required_minutes(num_lessons):
    total = num_lessons * LESSON_MINUTES
    if num_lessons > BREAK_AFTER_LESSONS:
        total += BREAK_MINUTES
    return total

# ===================== GIAO DIỆN HỆ THỐNG ĐIỂM DANH (DÙNG CHUNG) =====================
def render_attendance_form(user_type, sheet_key):
    st.write(f"### Phân hệ Điểm danh {user_type}")
    
    # Thành phần định vị vệ tinh được đặt ẩn nhận diện riêng theo Tab bằng key
    loc_data = streamlit_geolocation(key=f"gps_data_{user_type}")

    sw, lw = get_workspace_sheets(sheet_key)

    # Ô nhập mã định danh riêng biệt không lo trùng state
    label_input = "Nhập Mã số Giảng viên (MSGV)" if user_type == "GV" else "Nhập Mã số Sinh viên (MSSV)"
    user_code = st.text_input(label_input, value="", key=f"code_{user_type}").strip()

    # Tra cứu thông tin họ tên từ file sheet danh sách gốc của thầy
    user_info = None
    if user_code:
        try:
            records = sw.get_all_records()
            df_records = pd.DataFrame(records)
            # Tìm kiếm ở cột đầu tiên hoặc cột chứa chữ 'Mã'
            col_code = df_records.columns[0]
            match = df_records[df_records[col_code].astype(str) == user_code]
            if not match.empty:
                user_info = match.iloc[0].to_dict()
                # Hiển thị tên định danh trực quan lên ứng dụng
                col_name_key = df_records.columns[1] if len(df_records.columns) > 1 else col_code
                st.success(f"🟢 Xin chào {user_type}: **{user_info.get(col_name_key, user_code)}**")
            else:
                st.warning(f"⚠️ Mã số '{user_code}' không tồn tại trong danh sách dữ liệu cơ sở.")
        except Exception:
            st.caption(f"Connected to Sheet ID: {sheet_key[:8]}...")

    # Giao diện chọn ca học/tiết dạy
    now_vn = get_now_vn()
    default_ca_idx = 0 if now_vn.hour < 12 else 1
    ca_lam = st.selectbox("Ca làm việc", ["Sáng", "Chiều"], index=default_ca_idx, key=f"ca_{user_type}")

    c1, c2 = st.columns(2)
    with c1:
        def_start = 1 if ca_lam == "Sáng" else 7
        t_bat_dau = st.number_input("Tiết bắt đầu", 1, 12, def_start, key=f"start_{user_type}")
    with c2:
        def_end = 3 if ca_lam == "Sáng" else 9
        t_ket_thuc = st.number_input("Tiết kết thúc", 1, 12, def_end, key=f"end_{user_type}")

    s_time, e_time, total_lessons = get_lesson_interval(ca_lam, t_bat_dau, t_ket_thuc)
    st.info(f"📋 Khung giờ chuẩn: Tiết {t_bat_dau} -> {t_ket_thuc} | Thời gian: {s_time} - {e_time} ({total_lessons} tiết)")

    # Nút chức năng xử lý
    b1, b2 = st.columns(2)
    
    with b1:
        if st.button("Ghi nhận VÀO CA (Check-in)", use_container_width=True, key=f"btn_in_{user_type}"):
            if not user_code:
                st.error("Vui lòng điền mã số trước khi thực hiện!")
            elif not loc_data or "latitude" not in loc_data:
                st.error("Chưa lấy được định vị GPS. Vui lòng cấp quyền vị trí cho trình duyệt và thử lại.")
            else:
                # Tính khoảng cách thực tế
                u_lat = loc_data["latitude"]
                u_lon = loc_data["longitude"]
                distance = geodesic((u_lat, u_lon), (LAT_CENTER, LON_CENTER)).meters
                
                if distance > RADIUS_METERS:
                    st.error(f"❌ Ngoài bán kính cho phép! Khoảng cách hiện tại: {round(distance, 1)}m (Yêu cầu < {RADIUS_METERS}m)")
                else:
                    # Tính phút đi muộn dựa theo giờ chuẩn của Tiết học
                    h_start, m_start = parse_time_str(s_time)
                    target_time = now_vn.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
                    diff_minutes = (now_vn - target_time).total_seconds() / 60
                    late_min = max(0, int(diff_minutes))

                    # Tiến hành lưu dữ liệu
                    try:
                        lw.append_row([
                            now_vn.strftime("%d/%m/%Y"),
                            user_code, ca_lam, t_bat_dau, t_ket_thuc,
                            total_lessons, s_time, e_time, late_min, "IN", now_vn.strftime("%H:%M:%S")
                        ])
                        st.success(f"🎉 Đã ghi nhận VÀO CA thành công! Đi muộn: {late_min} phút.")
                    except Exception as ex:
                        st.error(f"Lỗi kết nối lưu dữ liệu: {ex}")

    with b2:
        if st.button("Ghi nhận RA CA (Check-out)", use_container_width=True, key=f"btn_out_{user_type}"):
            if not user_code:
                st.error("Vui lòng điền mã số trước khi thực hiện!")
            else:
                try:
                    logs = lw.get_all_records()
                    df_log = pd.DataFrame(logs)
                    
                    # Tìm dòng Check-in gần nhất của User hiện tại
                    col_user = df_log.columns[1]
                    user_logs = df_log[(df_log[col_user].astype(str) == user_code) & (df_log["IN/OUT"] == "IN")]
                    
                    if user_logs.empty:
                        st.error("❌ Không tìm thấy lịch sử dữ liệu vào ca (Check-in) trước đó của bạn.")
                    else:
                        last_in = user_logs.iloc[-1]
                        in_time_str = last_in["Giờ"]
                        num_les = int(last_in["Số tiết"])
                        
                        # Tính toán xem đủ giờ đứng lớp tối thiểu chưa
                        h_in, m_in = parse_time_str(in_time_str)
                        in_datetime = now_vn.replace(hour=h_in, minute=m_in, second=0, microsecond=0)
                        worked_minutes = (now_vn - in_datetime).total_seconds() / 60
                        required_minutes = calc_required_minutes(num_les)
                        
                        if worked_minutes < required_minutes:
                            st.error(f"❌ Chưa đủ thời gian yêu cầu! Thời gian tối thiểu là {required_minutes} phút (Hiện tại đạt: {int(worked_minutes)} phút).")
                        else:
                            lw.append_row([
                                now_vn.strftime("%d/%m/%Y"), user_code, "", "", "", "", "", "", "", "OUT", now_vn.strftime("%H:%M:%S")
                            ])
                            st.success("🚀 Đã ghi nhận RA CA thành công. Chúc thầy/cô hoặc bạn ra về an toàn!")
                except Exception as ex:
                    st.error(f"Lỗi kiểm tra dữ liệu ra ca: {ex}")

# ===================== ĐIỀU HƯỚNG CHÍNH TIÊN QUYẾT =====================
# Gom tab hiển thị nằm ngang lên trên đầu
menu_select = st.radio("", ["Giảng viên", "Sinh viên"], horizontal=True)

if menu_select == "Giảng viên":
    render_attendance_form("GV", GV_SHEET_KEY)
else:
    render_attendance_form("SV", SV_SHEET_KEY)
