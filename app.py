import streamlit as st
import gspread
import pandas as pd

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

# --- 🛡️ सेशन स्टेट ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- 侧बार (Sidebar) डिज़ाइन ---
st.sidebar.markdown("### 🏥 नॉर्मल चाइल्ड क्लिनिक")

if not st.session_state['logged_in']:
    # लॉगिन साइडबार
    st.sidebar.text_input("सेंटर का चयन करें (Center):", "HR_Admin")
    st.sidebar.text_input("HR_Admin का पासवर्ड डालें:", type="password")
    if st.sidebar.button("Login"):
        st.session_state['logged_in'] = True
        st.rerun()
else:
    # लॉगिन के बाद वाला डैशबोर्ड साइडबार
    st.sidebar.success("✅ एक्सेस स्वीकृत")
    st.sidebar.selectbox("सेंटर व्यू बदलें (Master Filter):", ["सभी सेंटर्स (All Centers)"])
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### 🧭 मेनू नेविगेशन:")
    menu = st.sidebar.radio("", [
        "🏠 डैशबोर्ड (Dashboard)",
        "👤 स्टाफ मैनेजमेंट (HR & Staff)",
        "📅 दैनिक हाजिरी (Attendance)",
        "🧒 मरीज रजिस्ट्रेशन (Patient Entry)",
        "📊 रिपोर्ट सेंटर (Advanced Reports)",
        "🔑 पासवर्ड व क्लिनिक मैनेजर"
    ])
    
    if st.sidebar.button("Logout 🚪"):
        st.session_state['logged_in'] = False
        st.rerun()

# --- मुख्य कंटेंट ---
if not st.session_state['logged_in']:
    st.title("कृपया लॉगिन करें")
else:
    st.title(f"आप वर्तमान में देख रहे हैं: {menu}")
    # यहाँ आप अपनी शीट का डेटा दिखा सकते हैं
    if menu == "🏠 डैशबोर्ड (Dashboard)":
        st.subheader("कुल एक्टिव स्टाफ: 3")
