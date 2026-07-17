import streamlit as st
import gspread
import pandas as pd
import os

# --- 🎨 पेज कॉन्फ़िगरेशन ---
st.set_page_config(page_title="Normal Child Clinic", layout="wide")

# --- 🔑 क्लाउड सुरक्षित कनेक्शन ---
@st.cache_resource
def connect_to_sheets():
    try:
        creds_dict = dict(st.secrets["gspread"])
        if 'private_key' in creds_dict:
            creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
            
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("Clinic_Management_Database")
        return sh, None
    except Exception as e:
        return None, str(e)

sh, raw_error = connect_to_sheets()

if sh is None:
    st.error(f"❌ कनेक्शन एरर: {raw_error}")
    st.stop()

# --- 🔐 सेशन स्टेट (लॉगिन को याद रखने के लिए) ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = ""

# --- 🛡️ पासवर्ड सेटिंग्स (आप इसे बाद में बदल सकते हैं) ---
PASSWORDS = {
    "Admin": "admin123",
    "Doctor": "doctor123",
    "Staff": "staff123"
}

# --- 1️⃣ लॉगिन सिस्टम फ़ंक्शन ---
def show_login_page():
    st.markdown("<h1 style='text-align: center; color: #0b3c4f;'>🏥 Normal Child Clinic</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>लॉगिन करें</h3>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            role = st.selectbox("अपना रोल चुनें:", ["Admin", "Doctor", "Staff"])
            password = st.text_input("पासवर्ड दर्ज करें:", type="password")
            submit_button = st.form_submit_button("Login", use_container_width=True)
            
            if submit_button:
                if PASSWORDS.get(role) == password:
                    st.session_state['logged_in'] = True
                    st.session_state['user_role'] = role
                    st.rerun()  # पेज को रिफ्रेश करता है
                else:
                    st.error("❌ गलत पासवर्ड! कृपया दोबारा प्रयास करें।")

# --- 2️⃣ मुख्य डैशबोर्ड फ़ंक्शन ---
def show_dashboard():
    # साइडबार (Sidebar)
    st.sidebar.title(f"👤 Welcome, {st.session_state['user_role']}")
    if st.sidebar.button("Logout 🚪", use_container_width=True):
        st.session_state['logged_in'] = False
        st.session_state['user_role'] = ""
        st.rerun()

    # मुख्य पेज
    st.title("📊 Clinic Management Dashboard")
    st.success("✅ Google Sheets से लाइव कनेक्टेड!")
    
    st.divider()

    # डेटा पढ़ना और दिखाना
    st.subheader("📋 हाल ही का डेटा")
    try:
        # यह आपकी Google Sheet की पहली (First) शीट का डेटा लाएगा
        worksheet = sh.sheet1
        data = worksheet.get_all_records()
        
        if data:
            df = pd.DataFrame(data)
            # डेटा को एक सुंदर टेबल में दिखाना
            st.dataframe(df, use_container_width=True)
        else:
            st.info("ℹ️ आपकी Sheet में अभी तक कोई डेटा नहीं है। कृपया Google Sheet की पहली पंक्ति (Row 1) में हेडिंग्स डालें।")
            
    except Exception as e:
        st.warning("⚠️ डेटा लोड करने में समस्या। सुनिश्चित करें कि आपकी Sheet खाली नहीं है और Row 1 में कॉलम के नाम (जैसे Name, Age, Date) लिखे हैं।")

# --- ⚙️ मुख्य ऐप लॉजिक (कौन सा पेज दिखाना है) ---
if not st.session_state['logged_in']:
    show_login_page()
else:
    show_dashboard()
