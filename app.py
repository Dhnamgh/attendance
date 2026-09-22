import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import io
import time
import requests
import msal
import plotly.express as px
from streamlit_js_eval import get_geolocation, streamlit_js_eval
import firebase_admin
from firebase_admin import credentials, db
import sys

# ============================== 1. CẤU HÌNH GIAO DIỆN ==============================
st.set_page_config(
    page_title="APP ĐIỂM DANH",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =============================== 2. CSS GIAO DIỆN ===============================
st.markdown("""
<style>
    /* 1. Ẩn Header, Sidebar, Footer mặc định của Streamlit */
    div[data-testid="stDecoration"], 
    header, 
    [data-testid="stHeader"],
    [data-testid="stSidebar"], 
    [data-testid="stSidebarNav"], 
    #MainMenu, 
    .stAppDeployButton, 
    [data-testid="stStatusWidget"],
    footer, 
    div[data-testid="stFooter"], 
    [data-testid="stViewerBadge"], 
    .stAppViewerBadge { 
        display: none !important; 
        height: 0 !important;
        visibility: hidden !important;
    }

    /* 2. Căn chỉnh lề gọn gàng trên mobile */
    .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 3rem !important;
    }
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            padding-top: 0.5rem !important;
        }
    }

    /* 3. Hiển thị chữ rõ nét */
    label, p, span, div[data-baseweb="input"], input {
        color: #262730 !important;
        opacity: 1 !important;
        -webkit-text-fill-color: #262730 !important;
    }
    input:disabled, 
    div[data-baseweb="input"]:has(input:disabled) {
        background-color: #F0F2F6 !important;
        color: #262730 !important;
        -webkit-text-fill-color: #262730 !important;
        opacity: 1 !important;
    }

    /* 4. Tiêu đề App */
    .app-title-custom {
        font-size: 18px !important;
        font-weight: 700 !important;
        color: #1f2937 !important;
        margin: 0px 0 12px 0 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px;
        text-align: center;
        border-bottom: 2px solid #1877F2;
        padding-bottom: 6px;
    }
</style>

<!-- Tiêu đề App -->
<div class="app-title-custom">📍 HỆ THỐNG ĐIỂM DANH TRỰC TUYẾN</div>
""", unsafe_allow_html=True)

# ================= PHẦN CODE XỬ LÝ CHÍNH CỦA APP ĐIỂM DANH =================

CLASS_LIST = ["D26A", "D26B", "D26C", "D26D", "KTHA26"]
MAX_ALLOWED_RADIUS = 150.0 
ALLOWED_IP_PREFIXES = ["103.180.97.", "118.69.1.", "203.162.1.", "171.244.1."]

CAMPUSES = {
    "CS1": {
        "name": "Cơ sở 1", 
        "address": "217 Hồng Bàng, P. Chợ Lớn, TP.HCM", 
        "lat": 10.754535, 
        "lng": 106.663351
    },
    "CS2": {
        "name": "Cơ sở 2", 
        "address": "201 Nguyễn Chí Thanh, P. Chợ Lớn, TP.HCM", 
        "lat": 10.757973, 
        "lng": 106.661271
    },
    "CS3": {
        "name": "Cơ sở 3", 
        "address": "41 Đinh Tiên Hoàng, P. Sài Gòn, TP.HCM", 
        "lat": 10.785324, 
        "lng": 106.702328
    }
}

LESSON_TIMES_THEORY = {
    1:  {"start": (7, 0),   "end": (7, 50)},
    2:  {"start": (7, 50),  "end": (8, 40)},
    3:  {"start": (8, 50),  "end": (9, 40)},
    4:  {"start": (9, 40),  "end": (10, 30)},
    5:  {"start": (10, 30), "end": (11, 20)},
    6:  {"start": (13, 0),  "end": (13, 50)},
    7:  {"start": (13, 50), "end": (14, 40)},
    8:  {"start": (14, 50), "end": (15, 40)},
    9:  {"start": (15, 40), "end": (16, 30)},
    10: {"start": (16, 30), "end": (17, 20)}
}

LESSON_TIMES_PRACTICE = {
    1:  {"start": (7, 30),  "end": (8, 20)},
    2:  {"start": (8, 20),  "end": (9, 10)},
    3:  {"start": (9, 10),  "end": (10, 0)},
    4:  {"start": (10, 0),  "end": (10, 50)},
    5:  {"start": (10, 50), "end": (11, 40)},
    6:  {"start": (13, 30), "end": (14, 20)},
    7:  {"start": (14, 20), "end": (15, 10)},
    8:  {"start": (15, 10), "end": (16, 0)},
    9:  {"start": (16, 0),  "end": (16, 50)},
    10: {"start": (16, 50), "end": (17, 40)}
}

def get_vietnam_now():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7)))

def shorten_unit_name(name):
    """Rút gọn tên Bộ môn / Đơn vị chuẩn hóa triệt để để hiển thị vừa vặn trên Biểu đồ"""
    if not name or pd.isna(name): return "Chưa xác định"
    s = str(name).strip()
    
    if "Hành chính tổ chức" in s or "Hành chính Tổ chức" in s or "HCTC" in s or "Văn phòng khoa" in s or "Văn phòng Khoa" in s:
        return "Tổ HCTC-VPK"
        
    s = s.replace("Bộ môn", "BM.").replace("Bộ Môn", "BM.")
    s = s.replace("Giáo dục thể chất", "GDTC").replace("Giáo Dục Thể Chất", "GDTC")
    s = s.replace("Lý luận chính trị", "LLCT").replace("Lý Luận Chính Trị", "LLCT")
    return s

# ================= 2. KẾT NỐI FIREBASE & MICROSOFT GRAPH =================
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            fb_sec = dict(st.secrets["firebase"])
            db_url = fb_sec.get("databaseURL")
            cert_dict = {k: v for k, v in fb_sec.items() if k != "databaseURL"}
            
            if "private_key" in cert_dict:
                cert_dict["private_key"] = cert_dict["private_key"].replace("\\n", "\n")
            
            cred = credentials.Certificate(cert_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        except Exception as e:
            st.error(f"Lỗi khởi tạo Firebase SDK: {str(e)}")

init_firebase()

def clean_dict_for_firebase(d):
    cleaned = {}
    forbidden_chars = [".", "#", "$", "[", "]"]
    for k, v in d.items():
        clean_k = str(k)
        for char in forbidden_chars:
            clean_k = clean_k.replace(char, "-")

        if pd.isna(v) or v is None:
            cleaned[clean_k] = ""
        elif isinstance(v, (float, int)):
            if math.isnan(v) or math.isinf(v):
                cleaned[clean_k] = 0.0
            else:
                cleaned[clean_k] = v
        else:
            cleaned[clean_k] = str(v)
    return cleaned

def save_to_firebase(node_name, record_dict):
    try:
        cleaned_data = clean_dict_for_firebase(record_dict)
        ref = db.reference(node_name)
        ref.push(cleaned_data)
        return True, None
    except Exception as e:
        return False, str(e)

def read_from_firebase(node_name):
    try:
        ref = db.reference(node_name)
        data = ref.get()
        if data:
            if isinstance(data, dict):
                return pd.DataFrame(list(data.values()))
            elif isinstance(data, list):
                return pd.DataFrame([x for x in data if x is not None])
        return pd.DataFrame()
    except Exception as e:
        st.caption(f"Lỗi đọc dữ liệu từ Firebase ({node_name}): {str(e)}")
        return pd.DataFrame()

# Hàm truy vấn dùng Index, không kéo toàn bộ DB về RAM
def get_user_records_from_firebase(node_name, user_id):
    try:
        ref = db.reference(node_name)
        snapshot = ref.order_by_child("Mã Số").equal_to(str(user_id)).get()
        if snapshot:
            if isinstance(snapshot, dict):
                return list(snapshot.values())
            elif isinstance(snapshot, list):
                return [x for x in snapshot if x is not None]
        return []
    except Exception as e:
        return []

def get_azure_token():
    try:
        azure_sec = st.secrets["azure"]
        tenant_id = azure_sec.get("tenant_id") or azure_sec.get("TENANT_ID")
        client_id = azure_sec.get("client_id") or azure_sec.get("CLIENT_ID")
        client_secret = azure_sec.get("client_secret") or azure_sec.get("CLIENT_SECRET")
        
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)
        scopes = ["https://graph.microsoft.com/.default"]
        result = app.acquire_token_for_client(scopes=scopes)
        return result.get("access_token")
    except Exception:
        return None

def build_graph_url(file_path):
    if "onedrive" in st.secrets and "drive_id" in st.secrets["onedrive"]:
        drive_id = st.secrets["onedrive"]["drive_id"]
        return f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{file_path}:"
    elif "USER_EMAIL" in st.secrets["azure"] or "user_email" in st.secrets["azure"]:
        user_email = st.secrets["azure"].get("USER_EMAIL") or st.secrets["azure"].get("user_email")
        return f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{file_path}:"
    else:
        return f"https://graph.microsoft.com/v1.0/me/drive/root:/{file_path}:"

# Bộ nhớ đệm 30 phút cho file danh sách
@st.cache_data(ttl=1800, show_spinner=False)
def read_excel_from_onedrive(file_path, sheet_name=None):
    token = get_azure_token()
    if not token: return pd.DataFrame()
    try:
        url = f"{build_graph_url(file_path)}/content"
        response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if response.status_code == 200:
            excel_bytes = io.BytesIO(response.content)
            df = pd.read_excel(excel_bytes, sheet_name=sheet_name if sheet_name else 0, dtype=str, engine="openpyxl")
            df.columns = [str(c).strip().replace('\xa0', '') for c in df.columns]
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def upload_file_to_onedrive(folder_path, file_name, file_bytes):
    token = get_azure_token()
    if not token: return False
    try:
        full_path = f"{folder_path}/{file_name}"
        content_url = f"{build_graph_url(full_path)}/content"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }
        res = requests.put(content_url, headers=headers, data=file_bytes)
        return res.status_code in [200, 201]
    except Exception:
        return False

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ================= 3. GIAO DIỆN HỆ THỐNG =================
tabs = st.tabs(["Điểm danh", "Báo nghỉ phép", "Dashboard"])

if "early_leave_pending" not in st.session_state:
    st.session_state["early_leave_pending"] = False
if "early_leave_mins" not in st.session_state:
    st.session_state["early_leave_mins"] = 0

# ----------------- TAB 1: ĐIỂM DANH -----------------
with tabs[0]:
    col1, col2 = st.columns(2)
    now_vn = get_vietnam_now()
    is_out_of_hours = (now_vn.hour >= 18) or (now_vn.hour < 6)
    
    with col1:
        # Mặc định Sinh viên đứng đầu tiên
        user_role = st.radio("Chọn đối tượng:", ["Sinh viên", "Giảng viên", "Viên chức"], index=0, horizontal=True)
        
        selected_class = ""
        if user_role == "Sinh viên":
            selected_class = st.selectbox("Chọn Lớp sinh viên:", CLASS_LIST)
            
        # Cho phép nhập tối đa 9 ký tự cho TẤT CẢ các đối tượng
        input_id = st.text_input("Nhập Mã số (tối đa 9 chữ số):", max_chars=9, placeholder="Nhập MSSV hoặc Mã CBVC (tối đa 9 số)", key="t1_id").strip()
        
        fetched_name, fetched_unit, fetched_sub, fetched_course = "", "", "", ""
        
        if len(input_id) >= 6:
            if user_role in ["Giảng viên", "Viên chức"]:
                target_df = read_excel_from_onedrive("OGSM/ATTENDANCE/DATA/CBVC.xlsx", sheet_name="Nhansu")
                if not target_df.empty:
                    col_msvc = target_df.columns[0]
                    col_name = target_df.columns[1] if len(target_df.columns) > 1 else target_df.columns[0]
                    col_unit = target_df.columns[2] if len(target_df.columns) > 2 else ""
                    col_sub = target_df.columns[3] if len(target_df.columns) > 3 else ""
                    
                    # Chuẩn hóa mã số (bỏ khoảng trắng, bỏ .0 và lấp đủ số)
                    raw_col = target_df[col_msvc].astype(str).str.strip().str.replace('\xa0', '').str.replace('.0', '', regex=False)
                    target_df["CLEAN_ID"] = raw_col
                    
                    # Khớp chính xác mã số hoặc so khớp theo 8 chữ số
                    match = target_df[(target_df["CLEAN_ID"] == input_id) | (target_df["CLEAN_ID"] == input_id.zfill(8))]
                    if not match.empty:
                        fetched_name = match.iloc[0][col_name]
                        fetched_unit = match.iloc[0][col_unit] if col_unit else ""
                        fetched_sub = match.iloc[0][col_sub] if col_sub else ""
            else:
                sv_class_path = f"OGSM/ATTENDANCE/DATA/SV/{selected_class}.xlsx"
                target_df = read_excel_from_onedrive(sv_class_path)
                if not target_df.empty:
                    col_mssv = target_df.columns[0]
                    col_name = target_df.columns[1] if len(target_df.columns) > 1 else target_df.columns[0]
                    col_unit = target_df.columns[2] if len(target_df.columns) > 2 else ""
                    col_sub = target_df.columns[3] if len(target_df.columns) > 3 else ""
                    col_course = target_df.columns[4] if len(target_df.columns) > 4 else ""
                    
                    raw_col = target_df[col_mssv].astype(str).str.strip().str.replace('\xa0', '').str.replace('.0', '', regex=False)
                    target_df["CLEAN_ID"] = raw_col
                    
                    # Khớp đúng 9 số hoặc theo định dạng chuỗi
                    match = target_df[(target_df["CLEAN_ID"] == input_id) | (target_df["CLEAN_ID"] == input_id.zfill(9))]
                    if not match.empty:
                        fetched_name = match.iloc[0][col_name]
                        fetched_unit = match.iloc[0][col_unit] if col_unit else ""
                        fetched_sub = match.iloc[0][col_sub] if col_sub else ""
                        fetched_course = match.iloc[0][col_course] if col_course else ""

        st.text_input("Họ và tên:", value=str(fetched_name if fetched_name else ("Chưa tìm thấy mã số trong danh sách" if len(input_id) >= 6 else "")), disabled=True)
        st.text_input("Đơn vị (Trường/Khoa):", value=str(fetched_unit), disabled=True)
        st.text_input("Bộ môn:", value=str(fetched_sub), disabled=True)
        if user_role == "Sinh viên":
            st.text_input("Tên học phần:", value=str(fetched_course), disabled=True)

        start_lesson, end_lesson = 1, 1
        lesson_schedule = LESSON_TIMES_THEORY
        study_type = "Lý thuyết"
        vc_shift = "Ca Sáng (07:00 - 11:00)"

        if is_out_of_hours:
            st.markdown('<div class="status-box-error">Hệ thống đã đóng điểm danh. Hiện tại nằm ngoài khung giờ làm việc / học tập quy định (06:00 - 18:00)!</div>', unsafe_allow_html=True)
        else:
            if user_role in ["Giảng viên", "Sinh viên"]:
                study_type = st.radio("Hình thức:", ["Lý thuyết", "Thực hành"], horizontal=True)
                lesson_schedule = LESSON_TIMES_PRACTICE if study_type == "Thực hành" else LESSON_TIMES_THEORY
                
                valid_start_lessons = []
                for t in range(1, 11):
                    t_end_h, t_end_m = lesson_schedule[t]["end"]
                    t_end_dt = now_vn.replace(hour=t_end_h, minute=t_end_m, second=0, microsecond=0)
                    if now_vn <= t_end_dt or (t >= 6 and now_vn.hour < 12): 
                        valid_start_lessons.append(t)
                
                if not valid_start_lessons: valid_start_lessons = list(range(1, 11))

                c_t1, c_t2 = st.columns(2)
                with c_t1:
                    start_lesson = st.selectbox("Từ tiết:", valid_start_lessons, index=0)
                
                with c_t2:
                    if start_lesson <= 5:
                        valid_end_lessons = [t for t in range(start_lesson, 6)]
                    else:
                        valid_end_lessons = [t for t in range(start_lesson, 11)]
                        
                    end_lesson = st.selectbox("Đến tiết:", valid_end_lessons, index=min(1, len(valid_end_lessons)-1))
                    
                s_h, s_m = lesson_schedule[start_lesson]["start"]
                e_h, e_m = lesson_schedule[end_lesson]["end"]
                st.caption(f"Thời gian ca ({study_type}): **{s_h:02d}:{s_m:02d} - {e_h:02d}:{e_m:02d}**")

            elif user_role == "Viên chức":
                default_shift_idx = 0 if now_vn.hour < 12 else 1
                vc_shift = st.selectbox("Ca làm việc Viên chức:", ["Ca Sáng (07:00 - 11:00)", "Ca Chiều (13:00 - 17:00)"], index=default_shift_idx)

    with col2:
        st.markdown("**Xác thực Tự động (GPS)**")
        location = get_geolocation()
        user_lat, user_lng = None, None
        if location and 'coords' in location:
            user_lat, user_lng = location['coords']['latitude'], location['coords']['longitude']
            st.caption(f"GPS: `{user_lat:.5f}, {user_lng:.5f}`")
        else:
            st.warning("⚠️ Đang chờ GPS... Bấm 'CHO PHÉP' (Allow) vị trí trên trình duyệt!")

        action_type = st.radio("Thao tác ca làm việc:", ["Vào ca (Check-in)", "Ra ca (Check-out)"], horizontal=True)

        distances = {}
        auto_detected_key = None
        if user_lat is not None and user_lng is not None:
            for c_key, c_val in CAMPUSES.items():
                distances[c_key] = calculate_distance(user_lat, user_lng, c_val["lat"], c_val["lng"])
            if distances.get("CS1", 9999) <= MAX_ALLOWED_RADIUS:
                auto_detected_key = "CS1"
            else:
                closest_key = min(distances, key=distances.get)
                if distances[closest_key] <= MAX_ALLOWED_RADIUS: auto_detected_key = closest_key

        campus_options = ["Tự động nhận diện", "Cơ sở 1 (217 Hồng Bàng)", "Cơ sở 2 (201 Nguyễn Chí Thanh)", "Cơ sở 3 (41 Đinh Tiên Hoàng)"]
        selected_campus_option = st.selectbox("Cơ sở điểm danh:", campus_options)

        final_campus_key = None
        if selected_campus_option == "Tự động nhận diện": final_campus_key = auto_detected_key
        elif "Cơ sở 1" in selected_campus_option: final_campus_key = "CS1"
        elif "Cơ sở 2" in selected_campus_option: final_campus_key = "CS2"
        elif "Cơ sở 3" in selected_campus_option: final_campus_key = "CS3"

        detected_campus_info = CAMPUSES.get(final_campus_key) if final_campus_key else None
        curr_dist = distances.get(final_campus_key, 0.0) if final_campus_key else 0.0

        if user_lat is None or user_lng is None:
            st.info("⏳ Vui lòng bật vị trí (GPS) trên điện thoại và tải lại trang nếu chưa hiện toạ độ.")
        elif detected_campus_info and curr_dist <= MAX_ALLOWED_RADIUS:
            st.success(f"✅ Hợp lệ: **{detected_campus_info['name']}** (Cách ~{int(curr_dist)}m)")
        else:
            st.error(f"❌ Ngoài bán kính cho phép (Cách cơ sở ~{int(curr_dist)}m > 150m)!")

    btn_confirm = st.button("XÁC NHẬN ĐIỂM DANH", use_container_width=True)

    # --- XỬ LÝ RA CA SỚM ---
    if st.session_state["early_leave_pending"]:
        st.warning(f"⚠️ CẢNH BÁO: Ra ca sớm **{st.session_state['early_leave_mins']} phút**!")
        c_confirm1, c_confirm2 = st.columns(2)
        with c_confirm1:
            if st.button("CÓ, XÁC NHẬN RA CA SỚM", key="btn_yes_early", use_container_width=True):
                node_map = {"Giảng viên": "LichSu_GV", "Viên chức": "LichSu_VC", "Sinh viên": "LichSu_SV"}
                target_node = node_map.get(user_role, "LichSu_SV")
                early_mins = st.session_state['early_leave_mins']
                record_data = {
                    "Mã Số": input_id,
                    "Họ Và Tên": str(fetched_name),
                    "Đối Tượng": user_role,
                    "Đơn Vị": str(fetched_unit),
                    "Bộ Môn - Lớp": str(shorten_unit_name(f"{fetched_sub} ({selected_class})" if user_role == "Sinh viên" else fetched_sub)),
                    "Cơ Sở": detected_campus_info['name'] if detected_campus_info else "N/A",
                    "Thời Gian": now_vn.strftime("%Y-%m-%d %H:%M:%S"),
                    "Thao Tác": "Ra ca (Check-out)",
                    "Khoảng Cách (m)": round(curr_dist, 1),
                    "Địa Chỉ IP": "N/A",
                    "Trạng Thái": f"Về sớm ({early_mins} phút)",
                    "Số Phút Trễ": 0,
                    "Số Phút Về Sớm": early_mins,
                    "Ghi Chú": f"Xác nhận Ra ca sớm {early_mins} phút."
                }
                save_to_firebase(target_node, record_data)
                st.success("✅ Đã ghi nhận Ra ca sớm thành công!")
                st.session_state["early_leave_pending"] = False
                st.session_state["early_leave_mins"] = 0

        with c_confirm2:
            if st.button("KHÔNG, Ở LẠI", key="btn_no_early", use_container_width=True):
                st.session_state["early_leave_pending"] = False
                st.session_state["early_leave_mins"] = 0
                st.rerun()

    elif btn_confirm:
        if is_out_of_hours:
            st.error("Hiện tại nằm ngoài khung giờ làm việc/học tập quy định!")
        elif user_lat is None or user_lng is None:
            st.error("Chưa nhận được tín hiệu GPS. Vui lòng cho phép quyền vị trí trên điện thoại!")
        elif curr_dist > MAX_ALLOWED_RADIUS or not detected_campus_info:
            st.error(f"Điểm danh thất bại: Bạn đang cách trường {curr_dist:.1f}m (vượt quá 150m)!")
        elif len(input_id) < 6 or not fetched_name:
            st.error("Mã số chưa chính xác hoặc không có trong danh sách dữ liệu!")
        else:
            node_map = {"Giảng viên": "LichSu_GV", "Viên chức": "LichSu_VC", "Sinh viên": "LichSu_SV"}
            target_node = node_map.get(user_role, "LichSu_SV")
            
            # --- LUỒNG SINH VIÊN SIÊU TỐC (CHỐNG NGHẼN CHO HÀNG TRĂM NGƯỜI) ---
            if user_role == "Sinh viên":
                record_data = {
                    "Mã Số": input_id,
                    "Họ Và Tên": str(fetched_name),
                    "Đối Tượng": "Sinh viên",
                    "Đơn Vị": str(fetched_unit),
                    "Bộ Môn - Lớp": str(shorten_unit_name(f"{fetched_sub} ({selected_class})")),
                    "Cơ Sở": detected_campus_info['name'],
                    "Thời Gian": now_vn.strftime("%Y-%m-%d %H:%M:%S"),
                    "Thao Tác": action_type,
                    "Khoảng Cách (m)": round(curr_dist, 1),
                    "Địa Chỉ IP": "N/A",
                    "Trạng Thái": "Đúng giờ",
                    "Số Phút Trễ": 0,
                    "Số Phút Về Sớm": 0,
                    "Ghi Chú": f"[{study_type}] Tiết {start_lesson}-{end_lesson}"
                }
                ok, err = save_to_firebase("LichSu_SV", record_data)
                if ok:
                    st.success(f"🎉 ĐIỂM DANH THÀNH CÔNG: {fetched_name} ({input_id}) lúc {now_vn.strftime('%H:%M:%S')}!")
                else:
                    st.error(f"Lỗi gửi dữ liệu: {err}")

            # --- LUỒNG GIẢNG VIÊN / VIÊN CHỨC ---
            else:
                user_records = get_user_records_from_firebase(target_node, input_id)
                last_action, last_time_str = None, ""
                if user_records:
                    last_record = user_records[-1]
                    last_action = str(last_record.get("Thao Tác", "")).strip()
                    last_time_str = str(last_record.get("Thời Gian", ""))

                if "Sáng" in vc_shift:
                    sched_start = now_vn.replace(hour=7, minute=0, second=0, microsecond=0)
                    sched_end_base = now_vn.replace(hour=11, minute=0, second=0, microsecond=0)
                else:
                    sched_start = now_vn.replace(hour=13, minute=0, second=0, microsecond=0)
                    sched_end_base = now_vn.replace(hour=17, minute=0, second=0, microsecond=0)

                late_mins = max(0, int((now_vn - sched_start).total_seconds() / 60))
                late_actual = late_mins if late_mins > 5 else 0
                sched_end = sched_end_base + timedelta(minutes=late_actual)

                if action_type == "Ra ca (Check-out)":
                    if last_action != "Vào ca (Check-in)":
                        st.error("Bạn chưa thực hiện Vào ca (Check-in)!")
                    elif now_vn < sched_end:
                        st.session_state["early_leave_pending"] = True
                        st.session_state["early_leave_mins"] = int((sched_end - now_vn).total_seconds() / 60)
                        st.rerun()
                    else:
                        rec = {
                            "Mã Số": input_id, "Họ Và Tên": str(fetched_name), "Đối Tượng": user_role,
                            "Đơn Vị": str(fetched_unit), "Bộ Môn - Lớp": str(shorten_unit_name(fetched_sub)),
                            "Cơ Sở": detected_campus_info['name'], "Thời Gian": now_vn.strftime("%Y-%m-%d %H:%M:%S"),
                            "Thao Tác": action_type, "Khoảng Cách (m)": round(curr_dist, 1),
                            "Địa Chỉ IP": "N/A", "Trạng Thái": "Đúng giờ", "Số Phút Trễ": 0, "Số Phút Về Sớm": 0,
                            "Ghi Chú": f"Hoàn thành ca làm việc"
                        }
                        save_to_firebase(target_node, rec)
                        st.success(f"✅ Ghi nhận Ra ca thành công cho {fetched_name}!")
                else:
                    status = "Đi trễ (Có bù giờ)" if late_actual > 0 else "Đúng giờ"
                    rec = {
                        "Mã Số": input_id, "Họ Và Tên": str(fetched_name), "Đối Tượng": user_role,
                        "Đơn Vị": str(fetched_unit), "Bộ Môn - Lớp": str(shorten_unit_name(fetched_sub)),
                        "Cơ Sở": detected_campus_info['name'], "Thời Gian": now_vn.strftime("%Y-%m-%d %H:%M:%S"),
                        "Thao Tác": action_type, "Khoảng Cách (m)": round(curr_dist, 1),
                        "Địa Chỉ IP": "N/A", "Trạng Thái": status, "Số Phút Trễ": late_actual, "Số Phút Về Sớm": 0,
                        "Ghi Chú": f"Vào ca lúc {now_vn.strftime('%H:%M')}"
                    }
                    save_to_firebase(target_node, rec)
                    st.success(f"✅ Điểm danh Vào ca thành công cho {fetched_name} ({status})!")

# ----------------- TAB 2: BÁO NGHỈ PHÉP -----------------
with tabs[1]:
    mc_user_role = st.radio("Chọn đối tượng nộp đơn:", ["Sinh viên", "Giảng viên", "Viên chức"], index=0, horizontal=True, key="mc_role_radio")
    
    mc_class = ""
    if mc_user_role == "Sinh viên":
        mc_class = st.selectbox("Chọn Lớp sinh viên:", CLASS_LIST, key="mc_class_select")
        
    mc_id = st.text_input("Nhập Mã số (tối đa 9 chữ số):", max_chars=9, placeholder="Nhập MSSV hoặc Mã CBVC", key="mc_id_input").strip()
    
    mc_fetched_name = ""
    mc_fetched_unit = ""
    
    if len(mc_id) >= 6:
        if mc_user_role in ["Giảng viên", "Viên chức"]:
            cbvc_df = read_excel_from_onedrive("OGSM/ATTENDANCE/DATA/CBVC.xlsx", sheet_name="Nhansu")
            if not cbvc_df.empty:
                col_msvc = cbvc_df.columns[0]
                col_name = cbvc_df.columns[1] if len(cbvc_df.columns) > 1 else cbvc_df.columns[0]
                col_unit = cbvc_df.columns[2] if len(cbvc_df.columns) > 2 else ""
                
                raw_col = cbvc_df[col_msvc].astype(str).str.split('.').str[0].str.strip().str.replace('\xa0', '')
                cbvc_df["CLEAN_ID"] = raw_col
                match = cbvc_df[(cbvc_df["CLEAN_ID"] == mc_id) | (cbvc_df["CLEAN_ID"] == mc_id.zfill(8))]
                if not match.empty:
                    mc_fetched_name = str(match.iloc[0][col_name]).strip()
                    mc_fetched_unit = str(match.iloc[0][col_unit]).strip() if col_unit else ""
        else:
            sv_df = read_excel_from_onedrive(f"OGSM/ATTENDANCE/DATA/SV/{mc_class}.xlsx")
            if not sv_df.empty:
                col_mssv = sv_df.columns[0]
                col_name = sv_df.columns[1] if len(sv_df.columns) > 1 else sv_df.columns[0]
                col_unit = sv_df.columns[2] if len(sv_df.columns) > 2 else ""
                
                raw_col = sv_df[col_mssv].astype(str).str.split('.').str[0].str.strip().str.replace('\xa0', '')
                sv_df["CLEAN_ID"] = raw_col
                match = sv_df[(sv_df["CLEAN_ID"] == mc_id) | (sv_df["CLEAN_ID"] == mc_id.zfill(9))]
                if not match.empty:
                    mc_fetched_name = str(match.iloc[0][col_name]).strip()
                    unit_raw = str(match.iloc[0][col_unit]).strip() if col_unit else ""
                    mc_fetched_unit = f"{unit_raw} - Lớp {mc_class}" if unit_raw else f"Lớp {mc_class}"

    display_name = mc_fetched_name if mc_fetched_name else ("Chưa tìm thấy mã số trong danh sách" if len(mc_id) >= 6 else "")
    display_unit = mc_fetched_unit if mc_fetched_unit else ""

    col_mc1, col_mc2 = st.columns(2)
    with col_mc1:
        st.text_input("Họ và tên người nộp:", value=display_name, disabled=True)
    with col_mc2:
        st.text_input("Đơn vị / Lớp:", value=display_unit, disabled=True)

    has_attended_today = False
    attendance_today_time = ""
    is_morning_attended = False
    is_afternoon_attended = False

    if len(mc_id) >= 6 and mc_fetched_name:
        node_map_role = {"Giảng viên": "LichSu_GV", "Viên chức": "LichSu_VC", "Sinh viên": "LichSu_SV"}
        target_mc_node = node_map_role.get(mc_user_role, "LichSu_SV")
        today_str = now_vn.strftime("%Y-%m-%d")
        
        hist_records = get_user_records_from_firebase(target_mc_node, mc_id)
        for r in hist_records:
            t_str = str(r.get("Thời Gian", ""))
            if t_str.startswith(today_str):
                has_attended_today = True
                attendance_today_time = t_str
                if len(t_str) >= 16:
                    try:
                        hour = int(t_str[11:13])
                        if hour < 12: is_morning_attended = True
                        else: is_afternoon_attended = True
                    except Exception:
                        pass

    with st.form("form_minh_chung_detail"):
        mc_type = st.selectbox("Loại yêu cầu:", ["Nghỉ phép Buổi Sáng", "Nghỉ phép Buổi Chiều", "Nghỉ phép Cả Ngày", "Minh chứng Đi trễ > 30 phút"])
        mc_reason = st.text_area("Lý do chi tiết:")
        mc_file = st.file_uploader("Tải lên file đi kèm (Ảnh / PDF):", type=["png", "jpg", "jpeg", "pdf"])
        
        btn_submit = st.form_submit_button("GỬI YÊU CẦU MINH CHỨNG")
        
        if btn_submit:
            if len(mc_id) < 6 or not mc_fetched_name:
                st.error("Mã số chưa chính xác hoặc không có trong danh sách dữ liệu trên OneDrive!")
            elif not mc_reason:
                st.error("Vui lòng nhập lý do chi tiết!")
            elif mc_type == "Nghỉ phép Cả Ngày" and has_attended_today:
                st.error(f"Từ chối gửi đơn: Bạn đã có lượt điểm danh có mặt trong ngày hôm nay lúc `{attendance_today_time}`! Không thể nộp đơn xin nghỉ cả ngày.")
            elif mc_type == "Nghỉ phép Buổi Sáng" and is_morning_attended:
                st.error("Từ chối gửi đơn: Bạn đã có lượt điểm danh trong Buổi Sáng hôm nay! Không thể nộp đơn xin nghỉ buổi sáng.")
            elif mc_type == "Nghỉ phép Buổi Chiều" and is_afternoon_attended:
                st.error("Từ chối gửi đơn: Bạn đã có lượt điểm danh trong Buổi Chiều hôm nay! Không thể nộp đơn xin nghỉ buổi chiều.")
            else:
                file_saved_name = "Không có file"
                if mc_file is not None:
                    file_ext = mc_file.name.split(".")[-1]
                    timestamp_str = now_vn.strftime("%Y%m%d_%H%M%S")
                    file_saved_name = f"{mc_id}_{timestamp_str}.{file_ext}"
                    
                    upload_file_to_onedrive(
                        "OGSM/ATTENDANCE/DATA/MINHCHUNG_FILES", 
                        file_saved_name, 
                        mc_file.getvalue()
                    )

                mc_record = {
                    "Mã Số": mc_id,
                    "Họ Và Tên": str(mc_fetched_name),
                    "Đối Tượng": mc_user_role,
                    "Đơn Vị": str(mc_fetched_unit),
                    "Loại Yêu Cầu": mc_type,
                    "Lý Do": mc_reason,
                    "File Minh Chứng": file_saved_name,
                    "Thời Gian Gửi": now_vn.strftime("%Y-%m-%d %H:%M:%S"),
                    "Trạng Thái Duyệt": "Chờ duyệt"
                }
                
                saved_mc, err_mc = save_to_firebase("MinhChung_NghiPhep", mc_record)
                
                if saved_mc:
                    st.success(f"Yêu cầu xin nghỉ / minh chứng của {mc_user_role} {mc_fetched_name} ({mc_id}) đã được ghi nhận thành công!")
                else:
                    st.error(f"Lỗi gửi đơn lên Firebase: {err_mc}")

# ----------------- TAB 3: DASHBOARD -----------------
with tabs[2]:
    st.subheader("🔒 BÁO CÁO & THỐNG KÊ QUẢN TRỊ")
    
    admin_pass = str(st.secrets["admin"]["password"]).strip()
    input_pass = st.text_input("Nhập mật khẩu Quản trị viên để truy cập:", type="password", key="db_pass_input")
    
    if input_pass != admin_pass:
        if input_pass:
            st.error("Mật khẩu không chính xác! Vui lòng liên hệ Ban quản trị.")
        else:
            st.info("Vui lòng nhập mật khẩu Quản trị viên để xem biểu đồ, báo cáo và xuất file Excel.")
    else:
        st.success("Đã xác thực quyền Quản trị viên!")
        st.markdown("---")

        # ================= NÚT ĐỒNG BỘ DỮ LIỆU SANG ONEDRIVE =================
        st.markdown("### ☁️ ĐỒNG BỘ DỮ LIỆU SANG ONEDRIVE")
        st.caption("Nhấn nút này để gom toàn bộ dữ liệu điểm danh từ Firebase ghi đè vào các file Excel trên OneDrive.")
        
        if st.button("🔄 ĐỒNG BỘ TẤT CẢ DỮ LIỆU SANG ONEDRIVE (XLSX)", type="primary", use_container_width=True):
            with st.spinner("Đang trích xuất dữ liệu từ Firebase và ghi vào OneDrive..."):
                sync_tasks = [
                    ("Sinh viên", "LichSu_SV", "LichSu_SV.xlsx"),
                    ("Giảng viên", "LichSu_GV", "LichSu_GV.xlsx"),
                    ("Viên chức", "LichSu_VC", "LichSu_VC.xlsx"),
                    ("Nghỉ phép", "MinhChung_NghiPhep", "MinhChung_NghiPhep.xlsx")
                ]
                success_count = 0
                for role_label, node, fname in sync_tasks:
                    df_sync = read_from_firebase(node)
                    if not df_sync.empty:
                        buf = io.BytesIO()
                        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                            df_sync.to_excel(writer, sheet_name='Sheet1', index=False)
                        
                        uploaded = upload_file_to_onedrive("OGSM/ATTENDANCE/DATA", fname, buf.getvalue())
                        if uploaded:
                            success_count += 1
                
                if success_count > 0:
                    st.success(f"✅ Đã đồng bộ thành công {success_count} file dữ liệu sang thư mục OneDrive (OGSM/ATTENDANCE/DATA)!")
                else:
                    st.warning("Chưa có dữ liệu mới để đồng bộ hoặc kiểm tra lại quyền kết nối Microsoft Graph.")
        st.markdown("---")
        
        view_mode = st.radio("Chọn loại báo cáo:", [
            "Nhật ký điểm danh chi tiết & Biểu đồ", 
            "Báo cáo Thống kê Thi đua / Đèn Rèn luyện (Theo Tháng)", 
            "Danh sách đơn minh chứng / nghỉ phép"
        ], index=0, horizontal=True, key="db_view_mode")
        
        # --- CHỨC NĂNG 1: NHẬT KÝ CHI TIẾT & BIỂU ĐỒ ---
        if view_mode == "Nhật ký điểm danh chi tiết & Biểu đồ":
            selected_report_role = st.selectbox("Chọn nhóm dữ liệu xem báo cáo:", ["Sinh viên", "Giảng viên", "Viên chức"], key="report_role_select")
            node_map_report = {"Giảng viên": "LichSu_GV", "Viên chức": "LichSu_VC", "Sinh viên": "LichSu_SV"}
            history_df = read_from_firebase(node_map_report[selected_report_role])
            
            if history_df.empty:
                st.info(f"Chưa có dữ liệu điểm danh trên Firebase cho nhóm **{selected_report_role}**.")
            else:
                unit_col = "Bộ Môn - Lớp" if "Bộ Môn - Lớp" in history_df.columns else ("Bộ Môn / Lớp" if "Bộ Môn / Lớp" in history_df.columns else ("Đơn Vị" if "Đơn Vị" in history_df.columns else history_df.columns[3]))
                
                history_df[unit_col] = history_df[unit_col].apply(shorten_unit_name)

                available_units = ["Tất cả (Toàn Khoa / Toàn Trường)"] + sorted([str(u) for u in history_df[unit_col].dropna().unique() if str(u).strip() != ""])
                
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    selected_unit_filter = st.selectbox("📌 Lọc dữ liệu theo Bộ môn / Lớp / Đơn vị:", available_units, index=0, key="dashboard_unit_filter")
                with c_f2:
                    selected_action_filter = st.selectbox("🔄 Lọc theo Thao tác ca làm việc:", ["Tất cả (Vào ca & Ra ca)", "Vào ca (Check-in)", "Ra ca (Check-out)"], index=0, key="dashboard_action_filter")

                filtered_df = history_df.copy()

                if selected_unit_filter != "Tất cả (Toàn Khoa / Toàn Trường)":
                    filtered_df = filtered_df[filtered_df[unit_col] == selected_unit_filter]

                if selected_action_filter != "Tất cả (Vào ca & Ra ca)":
                    filtered_df = filtered_df[filtered_df["Thao Tác"] == selected_action_filter]

                total_records = len(filtered_df)
                checkin_count = len(filtered_df[filtered_df["Thao Tác"] == "Vào ca (Check-in)"]) if "Thao Tác" in filtered_df.columns else 0
                checkout_count = len(filtered_df[filtered_df["Thao Tác"] == "Ra ca (Check-out)"]) if "Thao Tác" in filtered_df.columns else 0
                
                on_time_count = len(filtered_df[filtered_df["Trạng Thái"] == "Đúng giờ"]) if "Trạng Thái" in filtered_df.columns else 0
                early_leave_count = len(filtered_df[filtered_df["Trạng Thái"].str.contains("Về sớm", na=False)]) if "Trạng Thái" in filtered_df.columns else 0
                late_count = len(filtered_df[filtered_df["Trạng Thái"].str.contains("trễ|Trễ", na=False)]) if "Trạng Thái" in filtered_df.columns else 0
                
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Tổng lượt ghi nhận", total_records)
                m2.metric("Lượt Vào ca (Check-in)", checkin_count)
                m3.metric("Lượt Ra ca (Check-out)", checkout_count)
                m4.metric("Lượt Đi trễ", late_count)
                m5.metric("Lượt Ra ca sớm", early_leave_count)
                
                st.markdown("---")
                
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    chart_title_unit = f" - {selected_unit_filter}" if selected_unit_filter != "Tất cả (Toàn Khoa / Toàn Trường)" else " (Toàn Khoa)"
                    chart_title_action = f" [{selected_action_filter}]"
                    st.markdown(f"**Biểu đồ Tỷ lệ Trạng thái{chart_title_action}{chart_title_unit}**")

                    if "Trạng Thái" in filtered_df.columns and not filtered_df.empty:
                        status_counts = filtered_df["Trạng Thái"].value_counts().reset_index()
                        status_counts.columns = ["Trạng Thái", "Số Lượng"]
                        fig_pie = px.pie(
                            status_counts, 
                            values="Số Lượng", 
                            names="Trạng Thái", 
                            hole=0.4,
                            color_discrete_sequence=["#1877F2", "#E41E3F", "#FF9900", "#6c757d", "#17a2b8"]
                        )
                        fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10))
                        st.plotly_chart(fig_pie, use_container_width=True)
                    else:
                        st.info("Không có dữ liệu phù hợp với bộ lọc hiện tại.")

                with col_chart2:
                    st.markdown(f"**Biểu đồ Phân bố theo Bộ môn / Đơn vị{chart_title_unit}**")
                    if not filtered_df.empty and "Thao Tác" in filtered_df.columns:
                        action_unit_counts = filtered_df.groupby([unit_col, "Thao Tác"]).size().reset_index(name="Số Lượt")
                        fig_bar = px.bar(
                            action_unit_counts, 
                            x=unit_col, 
                            y="Số Lượt", 
                            color="Thao Tác",
                            barmode="group",
                            text_auto=True,
                            color_discrete_map={"Vào ca (Check-in)": "#1877F2", "Ra ca (Check-out)": "#28a745"}
                        )
                        fig_bar.update_layout(margin=dict(t=10, b=10, l=10, r=10))
                        st.plotly_chart(fig_bar, use_container_width=True)
                    else:
                        st.info("Không có dữ liệu phù hợp để vẽ biểu đồ cột.")

                st.markdown(f"**Bảng Nhật ký Chi tiết ({selected_report_role} - {selected_unit_filter} - {selected_action_filter}):**")
                st.dataframe(filtered_df, use_container_width=True)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    filtered_df.to_excel(writer, sheet_name='Sheet1', index=False)
                    
                st.download_button(
                    label=f"XUẤT BÁO CÁO EXCEL ĐÃ LỌC (.XLSX)",
                    data=buffer.getvalue(),
                    file_name=f"Bao_Cao_{selected_report_role}_{now_vn.strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        # --- CHỨC NĂNG 2: BÁO CÁO THI ĐUA THEO THÁNG ---
        elif view_mode == "Báo cáo Thống kê Thi đua / Đèn Rèn luyện (Theo Tháng)":
            selected_report_role = st.selectbox("Chọn đối tượng:", ["Sinh viên", "Giảng viên", "Viên chức"], key="stat_role_select")
            
            node_map_report = {"Giảng viên": "LichSu_GV", "Viên chức": "LichSu_VC", "Sinh viên": "LichSu_SV"}
            history_df = read_from_firebase(node_map_report[selected_report_role])
            
            if history_df.empty:
                st.info("Chưa có dữ liệu điểm danh trên Firebase.")
            else:
                history_df["THỜI GIAN DT"] = pd.to_datetime(history_df["Thời Gian"], errors='coerce')
                history_df["THÁNG_NĂM"] = history_df["THỜI GIAN DT"].dt.strftime("%m/%Y")
                
                available_months = sorted(history_df["THÁNG_NĂM"].dropna().unique(), reverse=True)
                selected_month = st.selectbox("Chọn Tháng/Năm xem báo cáo thi đua:", available_months if available_months else [now_vn.strftime("%m/%Y")])
                
                df_month = history_df[history_df["THÁNG_NĂM"] == selected_month].copy()
                
                if df_month.empty:
                    st.info(f"Không có dữ liệu điểm danh trong tháng {selected_month}.")
                else:
                    if "Số Phút Trễ" not in df_month.columns: df_month["Số Phút Trễ"] = 0
                    if "Số Phút Về Sớm" not in df_month.columns: df_month["Số Phút Về Sớm"] = 0
                    
                    df_month["Số Phút Trễ"] = pd.to_numeric(df_month["Số Phút Trễ"], errors='coerce').fillna(0)
                    df_month["Số Phút Về Sớm"] = pd.to_numeric(df_month["Số Phút Về Sớm"], errors='coerce').fillna(0)

                    summary_list = []
                    grouped = df_month.groupby("Mã Số")
                    for ms, group in grouped:
                        name = group["Họ Và Tên"].iloc[0] if "Họ Và Tên" in group.columns else ""
                        unit = group["Đơn Vị"].iloc[0] if "Đơn Vị" in group.columns else ""
                        sub_class = group["Bộ Môn - Lớp"].iloc[0] if "Bộ Môn - Lớp" in group.columns else (group["Bộ Môn / Lớp"].iloc[0] if "Bộ Môn / Lớp" in group.columns else "")
                        sub_class = shorten_unit_name(sub_class)
                        
                        total_att = len(group)
                        on_time = len(group[group["Trạng Thái"] == "Đúng giờ"])
                        late_cnt = len(group[group["Trạng Thái"].str.contains("trễ|Trễ", na=False)])
                        early_cnt = len(group[group["Trạng Thái"].str.contains("Về sớm", na=False)])
                        unclosed_cnt = len(group[group["Trạng Thái"].str.contains("Chưa Ra ca", na=False)])
                        total_late_min = int(group["Số Phút Trễ"].sum())
                        total_early_min = int(group["Số Phút Về Sớm"].sum())
                        
                        summary_list.append({
                            "Mã Số": ms,
                            "Họ Và Tên": name,
                            "Đơn Vị": unit,
                            "Bộ Môn - Lớp": sub_class,
                            "Tháng": selected_month,
                            "Tổng Số Lượt Điểm Danh": total_att,
                            "Số Lượt Đúng Giờ": on_time,
                            "Số Lượt Đi Trễ": late_cnt,
                            "Tổng Phút Trễ": total_late_min,
                            "Số Lượt Về Sớm": early_cnt,
                            "Tổng Phút Về Sớm": total_early_min,
                            "Số Lượt Quên Ra Ca": unclosed_cnt
                        })
                    
                    sum_df = pd.DataFrame(summary_list)
                    
                    st.markdown(f"### 📊 BẢNG THỐNG KÊ THI ĐUẢ / ĐIỂM RÈN LUYỆN - THÁNG {selected_month}")
                    st.dataframe(sum_df, use_container_width=True)
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        sum_df.to_excel(writer, sheet_name=f'ThiDua_{selected_month.replace("/", "_")}', index=False)
                        
                    st.download_button(
                        label=f"XUẤT BÁO CÁO THI ĐUẢ THÁNG {selected_month} (.XLSX)",
                        data=buffer.getvalue(),
                        file_name=f"Bao_Cao_Thi_Dua_{selected_report_role}_{selected_month.replace('/', '_')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

        # --- CHỨC NĂNG 3: DANH SÁCH ĐƠN MINH CHỨNG / NGHỈ PHÉP ---
        else:
            mc_df = read_from_firebase("MinhChung_NghiPhep")
            if mc_df.empty:
                st.info("Chưa có đơn xin nghỉ phép / minh chứng nào được gửi lên hệ thống.")
            else:
                st.metric("Tổng số đơn đã gửi", len(mc_df))
                
                col_mc_chart1, col_mc_chart2 = st.columns(2)
                with col_mc_chart1:
                    st.markdown("**Phân loại Đơn theo Đối tượng**")
                    if "Đối Tượng" in mc_df.columns:
                        role_mc_counts = mc_df["Đối Tượng"].value_counts().reset_index()
                        role_mc_counts.columns = ["Đối Tượng", "Số Lượng"]
                        fig_mc_role = px.pie(role_mc_counts, values="Số Lượng", names="Đối Tượng", hole=0.3)
                        st.plotly_chart(fig_mc_role, use_container_width=True)
                    
                with col_mc_chart2:
                    st.markdown("**Phân loại theo Loại Yêu cầu**")
                    if "Loại Yêu Cầu" in mc_df.columns:
                        type_mc_counts = mc_df["Loại Yêu Cầu"].value_counts().reset_index()
                        type_mc_counts.columns = ["Loại Yêu Cầu", "Số Lượng"]
                        fig_mc_type = px.bar(type_mc_counts, x="Loại Yêu Cầu", y="Số Lượng", color="Loại Yêu Cầu", text_auto=True)
                        st.plotly_chart(fig_mc_type, use_container_width=True)

                st.dataframe(mc_df, use_container_width=True)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    mc_df.to_excel(writer, sheet_name='MinhChung', index=False)
                    
                st.download_button(
                    label="XUẤT BÁO CÁO MINH CHỨNG (.XLSX)",
                    data=buffer.getvalue(),
                    file_name=f"Bao_Cao_Minh_Chung_{now_vn.strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
