import streamlit as st
import gspread
import pandas as pd
import os

# --- 🎨 पेज कॉन्फ़िगरेशन ---
st.set_page_config(page_title="Normal Child Clinic - Management Portal", layout="wide")

# --- 🔑 क्लाउड सुरक्षित कनेक्शन (Streamlit Secrets का उपयोग) ---
@st.cache_resource
def connect_to_sheets():
    try:
        # Streamlit के Secrets से 'gspread' क्रेडेंशियल्स लोड करना
        creds_dict = st.secrets["gspread"]
        # सर्विस अकाउंट के जरिए Google Sheets से जुड़ना
        gc = gspread.service_account_from_dict(creds_dict)
        # अपनी Google Sheet का नाम यहाँ सही लिखें
        sh = gc.open("Clinic_Management_Database")
        return sh, None
    except Exception as e:
        return None, str(e)

# कनेक्शन कॉल करें
sh, raw_error = connect_to_sheets()

if sh is None:
    st.error(f"❌ Google Sheet से कनेक्शन नहीं हो पाया! कृपया Secrets चेक करें. एरर: {raw_error}")
    st.stop()

# --- 🎨 प्रीमियम थीम CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; }
    h1, h2, h3 { color: #0b3c4f; font-weight: 600 !important; }
    [data-testid="stSidebar"] { background-color: #0b3c4f !important; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    </style>
""", unsafe_allow_html=True)

# --- 🔑 पासवर्ड मैनेजर ---
@st.cache_data(ttl=5)
def get_live_passwords():
    try:
        return {r['Center']: str(r['Password']) for r in sh.worksheet("Passwords").get_all_records() if r['Center']}
    except:
        return {"Raipur": "raipur@123", "HR_Admin": "admin@hr"}

PASSWORDS = get_live_passwords()

# --- ऐप इंटरफेस ---
st.sidebar.markdown("<h3 style='text-align: center; color: white;'>🔒 CONTROL PANEL</h3>", unsafe_allow_html=True)

# यहाँ अपना बाकी का प्रोजेक्ट कोड जोड़ें जो आप पहले उपयोग कर रहे थे...
st.title("Normal Child Clinic Management")
st.write("सफलतापूर्वक कनेक्टेड! अब आप अपना डैशबोर्ड यहाँ देख सकते हैं।")
