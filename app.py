import streamlit as st

st.set_page_config(layout="wide")

# ================= CSS CHUẨN =================
st.markdown("""
<style>

/* remove padding */
.block-container {
    padding-top:0 !important;
}

/* header full bar */
.header {
    position:relative;
    width:100%;
    height:70px;
    background:#2c6b95;
    display:flex;
    align-items:center;
    justify-content:center;
}

/* title */
.header-title {
    color:white;
    font-size:24px;
    font-weight:600;
}

/* logo wrapper (chìa ra sidebar) */
.header-logo {
    position:absolute;
    left:-5px;
    top:5px;
    height:60px;
}

/* sidebar style */
section[data-testid="stSidebar"]{
    background:#2c6b95 !important;
}
section[data-testid="stSidebar"] *{
    color:white !important;
    font-size:16px !important;
}

/* content */
.main-content {
    max-width:1000px;
    margin:auto;
    padding:20px;
}

/* card */
.card {
    background:white;
    padding:20px;
    border-radius:10px;
    margin-top:20px;
}

/* footer */
.footer {
    background:#2b2f65;
    color:white;
    padding:15px;
    text-align:center;
    margin-top:40px;
}

/* mobile */
@media (max-width:768px){
    .header-title {font-size:18px;}
    .header {height:55px;}
    .header-logo {height:45px;}
}

</style>
""", unsafe_allow_html=True)

# ================= HEADER + LOGO =================
col1, col2 = st.columns([1,8])

with col1:
    # ✅ LOGO THẬT (KHÔNG HTML IMG)
    st.image("h.png", width=180)

with col2:
    st.markdown("""
    <div class="header">
        <div class="header-title">HỆ THỐNG ĐIỂM DANH</div>
    </div>
    """, unsafe_allow_html=True)

# ================= SIDEBAR =================
menu = st.sidebar.radio(
    "",
    ["Giảng viên", "Sinh viên", "Quản trị"]
)

# ================= CONTENT =================
st.markdown("<div class='main-content'>", unsafe_allow_html=True)

if menu == "Giảng viên":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Điểm danh giảng viên")

    st.text_input("MSGV")
    st.text_input("Họ tên")
    st.selectbox("Ca", ["Sáng", "Chiều"])
    st.number_input("Tiết bắt đầu",1,11,1)
    st.number_input("Tiết kết thúc",1,11,3)
    st.info("[1, 2, 3] | 07:00 - 09:30")

    st.button("Check-in")
    st.button("Check-out")

    st.markdown("</div>", unsafe_allow_html=True)

elif menu == "Sinh viên":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Điểm danh sinh viên")

    st.text_input("MSSV")
    st.text_input("Họ tên")
    st.selectbox("Ca", ["Sáng", "Chiều"])
    st.number_input("Tiết bắt đầu",1,11,1)
    st.number_input("Tiết kết thúc",1,11,3)
    st.info("[1, 2, 3] | 07:00 - 09:30")

    st.button("Check-in SV")
    st.button("Check-out SV")

    st.markdown("</div>", unsafe_allow_html=True)

else:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Quản trị hệ thống")

    st.text_input("Mật khẩu", type="password")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ================= FOOTER =================
st.markdown("""
<div class="footer">
Đại học Y Dược TP.HCM - 217 Hồng Bàng
</div>
""", unsafe_allow_html=True)
