import streamlit as st
import gspread
import pandas as pd

# --- 🎨 पेज कॉन्फ़िगरेशन ---
st.set_page_config(page_title="Normal Child Clinic", layout="wide")

# --- 🔑 क्लाउड सुरक्षित कनेक्शन ---
@st.cache_resource
def connect_to_sheets():
    try:
        # यहाँ 'gspread' का उपयोग किया गया है जो आपके Secrets में सेव है
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

# --- 🔐 सेशन स्टेट ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = ""

# --- 🛡️ पासवर्ड सेटिंग्स ---
PASSWORDS = {
    "Admin": "admin123",
    "Doctor": "doctor123",
    "Staff": "staff123"
}

# --- 1️⃣ लॉगिन पेज ---
def show_login_page():
    st.markdown("<h1 style='text-align: center;'>🏥 Normal Child Clinic</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            role = st.selectbox("रोल चुनें:", ["Admin", "Doctor", "Staff"])
            password = st.text_input("पासवर्ड:", type="password")
            submit = st.form_submit_button("Login")
            if submit:
                if PASSWORDS.get(role) == password:
                    st.session_state['logged_in'] = True
                    st.session_state['user_role'] = role
                    st.rerun()
                else:
                    st.error("❌ गलत पासवर्ड!")

# --- 2️⃣ डैशबोर्ड और मेनू ---
def show_dashboard():
    st.sidebar.title(f"👤 {st.session_state['user_role']} Panel")
    menu = st.sidebar.radio("मेनू चुनें:", ["📊 डैशबोर्ड (Data)", "➕ नया एंट्री जोड़ें"])
    
    if st.sidebar.button("Logout 🚪"):
        st.session_state['logged_in'] = False
        st.rerun()

    if menu == "📊 डैशबोर्ड (Data)":
        st.title("📊 क्लिनिक डैशबोर्ड")
        data = sh.sheet1.get_all_records()
        if data:
            st.dataframe(pd.DataFrame(data), use_container_width=True)
        else:
            st.info("डेटा उपलब्ध नहीं है।")

    elif menu == "➕ नया एंट्री जोड़ें":
        st.title("➕ नया डेटा जोड़ें")
        with st.form("add_form"):
            name = st.text_input("नाम:")
            role_entry = st.text_input("रोल/विवरण:")
            mobile = st.text_input("मोबाइल:")
            submit = st.form_submit_button("सेव करें")
            if submit:
                sh.sheet1.append_row([name, role_entry, mobile])
                st.success("✅ डेटा सेव हो गया!")

# --- ⚙️ मुख्य लॉजिक ---
if not st.session_state['logged_in']:
    show_login_page()
else:
    show_dashboard()
