# ================= GPS (ĐÃ SỬA) =================
def check_gps(loc):
    # Nhận trực tiếp dữ liệu loc từ form truyền vào thay vì tự gọi hàm độc lập
    if not loc or not loc.get("latitude"):
        st.error("Không lấy được GPS hoặc chưa cấp quyền vị trí.")
        return False

    lat = loc["latitude"]
    lon = loc["longitude"]

    dlat = radians(lat - LAT_CENTER)
    dlon = radians(lon - LON_CENTER)

    a = sin(dlat/2)**2 + cos(radians(LAT_CENTER))*cos(radians(lat))*sin(dlon/2)**2
    d = 2 * 6371000 * atan2(sqrt(a), sqrt(1-a))

    if d > RADIUS:
        st.error(f"Ngoài khu vực điểm danh (Khoảng cách hiện tại: {round(d, 1)}m)")
        return False

    return True

# ================= LOGIC CHUNG (ĐÃ SỬA) =================
def checkin(sheet_key, code, ca, f, t, loc):
    # 1. Kiểm tra mã định danh trước
    if not code.strip():
        st.error("Vui lòng nhập Mã số trước khi Check-in!")
        return

    # 2. Kiểm tra GPS dựa trên tọa độ lấy lúc bấm nút
    if not check_gps(loc):
        return

    arr, s, e = calc_lessons(ca, f, t)
    late = calc_late(s)

    append_row(sheet_key, [
        today(), code, ca,
        f, t, len(arr),
        s, e,
        late,
        "IN",
        now_str()
    ])

    st.success(f"Đã vào ca - muộn {late} phút")


def checkout(sheet_key, code, col_name):
    if not code.strip():
        st.error("Vui lòng nhập Mã số trước khi Check-out!")
        return

    df = load_df(sheet_key)

    last = df[
        (df[col_name] == code) &
        (df["IN/OUT"] == "IN")
    ]

    if last.empty:
        st.error("Chưa check-in")
        return

    last = last.iloc[-1]

    need = required_time(int(last["Số tiết"]))

    if not can_checkout(last["Giờ"], need):
        st.error("Chưa đủ thời gian")
        return

    append_row(sheet_key, [
        today(), code,
        "", "", "", "", "", "", "",
        "OUT",
        now_str()
    ])

    st.success("Ra ca thành công")

# ================= FORM (ĐÃ SỬA) =================
def render(label, sheet_key):
    # Gọi định vị ở mức giao diện chính để người dùng cấp quyền trước
    loc = streamlit_geolocation()

    code = st.text_input(label, value="")

    ca = st.selectbox("Ca", ["Sáng", "Chiều"])

    c1, c2 = st.columns(2)
    with c1:
        f = st.number_input("Tiết bắt đầu", 1, 11, 1)
    with c2:
        t = st.number_input("Tiết kết thúc", 1, 11, 3)

    arr, s, e = calc_lessons(ca, f, t)

    st.info(f"Tiết học: {arr} | Giờ chuẩn: {s} - {e}")

    col1, col2 = st.columns(2)

    with col1:
        # Truyền thêm biến loc vào hàm checkin khi bấm nút
        if st.button("Check-in", use_container_width=True):
            checkin(sheet_key, code, ca, f, t, loc)

    with col2:
        if st.button("Check-out", use_container_width=True):
            checkout(sheet_key, code, label)

# ================= MAIN =================
st.title("Hệ thống điểm danh")
# st.image("h.png", width=150) # Thầy nhớ kiểm tra lại file ảnh này có sẵn ở thư mục chưa nhé

menu = st.radio("", ["Giảng viên", "Sinh viên"])

if menu == "Giảng viên":
    st.subheader("Điểm danh giảng viên")
    render("MSGV", GV_SHEET)
else:
    st.subheader("Điểm danh sinh viên")
    render("MSSV", SV_SHEET)
