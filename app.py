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
        # Streamlit के Secrets से क्रेडेंशियल्स लेना
        creds_dict = dict(st.secrets["gspread"])
        
        # यह लाइन PEM फाइल एरर को ठीक करने के लिए बहुत ज़रूरी है
        if 'private_key' in creds_dict:
            creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
            
        # Google Sheet से जुड़ना
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open("Clinic_Management_Database")
        return sh, None
    except Exception as e:
        return None, str(e)

# कनेक्शन कॉल करें
sh, raw_error = connect_to_sheets()

if sh is None:
    st.error(f"❌ कनेक्शन एरर: {raw_error}")
    st.info("कृपया सुनिश्चित करें कि Secrets में private_key सही तरीके से पेस्ट की गई है।")
    st.stop()

# --- 🎨 बेसिक UI ---
st.title("Normal Child Clinic Management")
st.success("✅ Google Sheets से सफलतापूर्वक कनेक्ट हो गया है!")

# --- यहाँ अपना बाकी का प्रोजेक्ट कोड जोड़ें ---
# उदाहरण के लिए:
# data = sh.worksheet("Sheet1").get_all_records()
# df = pd.DataFrame(data)
# st.write(df)
