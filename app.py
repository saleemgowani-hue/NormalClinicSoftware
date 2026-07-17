import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import os

# --- ⚙️ कॉन्फ़िगरेशन ---
st.set_page_config(page_title="Normal Child Clinic - Management Portal", layout="wide")

# --- 🔒 Google Sheets सुरक्षित कनेक्शन (Streamlit Cloud के लिए अपडेटेड) ---
@st.cache_resource
def connect_to_sheets():
    try:
        # Streamlit secrets.toml से क्रेडेंशियल्स लोड करना
        creds_dict = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("Clinic_Management_Database")
        return sh, None
    except Exception as e:
        return None, str(e)

sh, raw_error = connect_to_sheets()

if sh is None:
    st.error(f"❌ Google Sheet से कनेक्शन नहीं हो पाया! कृपया Secret Settings चेक करें। एरर: {raw_error}")
    st.stop()

# (बाकी सारा कोड आपका पुराना ही है, बस ऊपर वाले फंक्शन को यहाँ बदल दिया गया है)

# --- 🔍 इमेज स्कैनर (अगर इमेज फोल्डर में है) ---
def find_clinic_image(keyword):
    search_paths = [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]
    for path in search_paths:
        if os.path.exists(path):
            try:
                for file in os.listdir(path):
                    if keyword.lower() in file.lower() and file.lower().endswith(('.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG')):
                        return os.path.join(path, file)
            except: pass
    return None

banner_file = find_clinic_image("banner")
logo_file = find_clinic_image("logo")

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

# (यहाँ से आगे आपका बाकी पूरा कोड वैसा ही रखें जैसा आपके कंप्यूटर में था, 
# बस 'load_cloud_data_fast' और अन्य फंक्शन्स को नीचे पेस्ट करें)

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
        if sheet_name == "Patients":
            for col in ['Fees', 'Total Fees']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace('₹', '', regex=False).str.replace('/-', '', regex=False).str.replace(',', '', regex=False).str.strip()
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        return df
    except: return pd.DataFrame()

# [नोट: यहाँ अपना बाकी सारा फंक्शन logic नीचे पेस्ट करें...]
