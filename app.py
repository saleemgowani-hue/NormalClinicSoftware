import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import os
import json

st.set_page_config(page_title="Normal Child Clinic - Management Portal", layout="wide")

# --- 🖼️ क्लाउड फ्रेंडली इमेज लोडर ---
def get_image_path(filename):
    if os.path.exists(filename):
        return filename
    return None

banner_file = get_image_path("banner.png")
logo_file = get_image_path("logo.png")

# --- 🎨 प्रीमियम थीम CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; }
    .metric-card {
        background-color: #ffffff; padding: 22px; border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-top: 4px solid #008080;
        text-align: center;
    }
    .metric-title { color: #6c757d; font-size: 13px; font-weight: 600; text-transform: uppercase; }
    .metric-value { color: #101010; font-size: 28px; font-weight: 700; margin-top: 5px; }
    h1, h2, h3 { color: #0b3c4f; font-weight: 600 !important; }
    [data-testid="stSidebar"] { background-color: #0b3c4f !important; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    [data-testid="stSidebar"] input { color: #000000 !important; }
    .stButton>button {
        background-color: #008080 !important; color: white !important;
        border-radius: 6px !important; padding: 8px 20px !important;
        font-weight: 600 !important; border: none !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 🔑 क्लाउड सुरक्षित कनेक्शन ---
@st.cache_resource
def connect_to_sheets():
    try:
        creds_dict = st.secrets["gspread"]
        if isinstance(creds_dict, str):
            creds_dict = json.loads(creds_dict)
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("Clinic_Management_Database")
        return sh, None
    except Exception as e:
        return None, str(e)

sh, raw_error = connect_to_sheets()

if sh is None:
    st.error(f"❌ Google Sheet से कनेक्शन नहीं हो पाया: {raw_error}")
    st.stop()

# --- 🔒 क्लाउड डेटा लोडर ---
@st.cache_data(ttl=5)
def load_cloud_data_fast(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        all_rows = worksheet.get_all_values()
        if not all_rows or len(all_rows) < 1: return pd.DataFrame()
        headers = [str(h).strip() for h in all_rows[0]]
        df = pd.DataFrame(all_rows[1:], columns=headers)
        if sheet_name == "Attendance" and "Staff ID" in df.columns: df = df.rename(columns={"Staff ID": "Staff_ID"})
        return df
    except: return pd.DataFrame()

# --- (बाकी के आपके सभी फंक्शन्स: sync_total_fees_batch, sync_daily_collection_to_sheet, आदि यहाँ जोड़ें) ---
# --- (नोट: कोड की लंबाई के कारण मैंने केवल मुख्य कनेक्शन वाले हिस्से अपडेट किए हैं) ---

# [यहाँ से आप अपना वही पुराना logic (Dashboard, HR, Attendance आदि) वाला कोड पेस्ट कर सकते हैं]

st.info("✅ ऐप सफलतापूर्वक कनेक्ट हो गया है। अपना बाकी लॉजिक यहाँ जोड़ें।")
