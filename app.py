import streamlit as st

def get_query_params():
    if hasattr(st, "query_params"):
        return dict(st.query_params)
    return st.experimental_get_query_params()

qp = get_query_params()

# ===================== SV =====================
if qp.get("sv") == "1":

    import os, io, re, time, base64, urllib.parse, unicodedata, datetime
    from difflib import get_close_matches
    import gspread
    from google.oauth2.service_account import Credentials
    from PIL import Image
    import qrcode
    import pandas as pd
    import altair as alt

    QR_SLOT_SECONDS = 30
    UNLOCK_TTL = 120
    MSSV_PREFIX = st.secrets.get("SESSION_PREFIX", "51125")

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    SHEET_KEY = st.secrets.get("SHEET_KEY")
    WORKSHEET_NAME = "D25C"

    VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

    def get_sheet():
        creds = Credentials.from_service_account_info(
            dict(st.secrets["google_service_account"]),
            scopes=SCOPES
        )
        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_KEY).worksheet(WORKSHEET_NAME)

    def get_query_params():
        if hasattr(st, "query_params"):
            return dict(st.query_params)
        return st.experimental_get_query_params()

    def token_valid(t):
        if not t or not str(t).isdigit():
            return False
        now = int(time.time()) // QR_SLOT_SECONDS
        return abs(int(t) - now) <= 1

    qp = get_query_params()

    buoi = qp.get("buoi", "Buổi 1")
    token = qp.get("t", "")

    st.title("Điểm danh sinh viên")

    if not token_valid(token):
        st.error("QR hết hạn")
        st.stop()

    mssv = st.text_input("4 số cuối MSSV")
    name = st.text_input("Họ tên")

    if st.button("Xác nhận"):
        if not mssv or not name:
            st.error("Thiếu thông tin")
            st.stop()

        sheet = get_sheet()
        records = sheet.get_all_records()

        full = MSSV_PREFIX + mssv

        row_index = None
        for i, r in enumerate(records, start=2):
            if str(r.get("MSSV")).endswith(mssv):
                row_index = i
                break

        if not row_index:
            st.error("Không tìm thấy")
            st.stop()

        col = sheet.find(buoi).col
        val = sheet.cell(row_index, col).value

        if val:
            st.success("Đã điểm danh")
        else:
            sheet.update_cell(row_index, col, "✅")
            st.success("Thành công")

# ===================== GV =====================
else:

    import os, io, re, time, base64, urllib.parse, unicodedata, datetime
    import gspread
    from google.oauth2.service_account import Credentials
    from PIL import Image
    import qrcode
    import pandas as pd
    import altair as alt

    QR_SLOT_SECONDS = 30

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    SHEET_KEY = st.secrets.get("SHEET_KEY")
    WORKSHEET_NAME = "D25C"

    VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

    def get_sheet():
        creds = Credentials.from_service_account_info(
            dict(st.secrets["google_service_account"]),
            scopes=SCOPES
        )
        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_KEY).worksheet(WORKSHEET_NAME)

    st.title("QR điểm danh giảng viên")

    buoi = st.selectbox(
        "Chọn buổi",
        ["Buổi 1","Buổi 2","Buổi 3","Buổi 4","Buổi 5","Buổi 6"]
    )

    if st.button("Tạo QR"):

        while True:
            now = int(time.time())
            token = now // QR_SLOT_SECONDS

            base = st.secrets.get("WRAPPER_URL") or "https://qrlecturer.streamlit.app"

            link = f"{base}/?sv=1&buoi={urllib.parse.quote(buoi)}&t={token}"

            qr = qrcode.make(link)

            buf = io.BytesIO()
            qr.save(buf)
            buf.seek(0)

            st.image(buf, width=300)

            time.sleep(1)
