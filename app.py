import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. Google Sheets से जुड़ने का फंक्शन
def get_data_from_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('secret_key.json', scope)
    client = gspread.authorize(creds)
    # अपनी Google Sheet का नाम यहाँ लिखें
    sheet = client.open('Clinic_Management_Database').sheet1 
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# 2. मुख्य ऐप लेआउट
st.set_page_config(page_title="Normal Child Clinic", layout="wide")
st.title("🏥 Normal Child Clinic - डैशबोर्ड")

try:
    df = get_data_from_google_sheets()

    # 3. डैशबोर्ड सेक्शन
    st.subheader("📊 दैनिक क्लिनिक सारांश")
    col1, col2 = st.columns(2)
    
    total_patients = len(df)
    col1.metric(label="कुल मरीज़", value=total_patients)

    # 4. ग्राफ और विज़ुअलाइज़ेशन
    if 'Diagnosis' in df.columns:
        diagnosis_counts = df['Diagnosis'].value_counts()
        st.write("### मरीज़ों की समस्याओं का वितरण")
        st.bar_chart(diagnosis_counts)

    # 5. डेटा टेबल (एक्सेस कंट्रोल)
    if st.checkbox("मरीज़ों की पूरी सूची देखें"):
        st.dataframe(df)

except Exception as e:
    st.error(f"डेटा लोड करने में त्रुटि: {e}")
    st.info("सुनिश्चित करें कि 'secret_key.json' फाइल सही जगह पर है और आपके पास एक्सेस है।")

# 6. क्लिनिक स्टाफ SOP रिफरेंस (Optional)
with st.expander("ℹ️ स्टाफ SOP निर्देश देखें"):
    st.write("रिसेप्शनिस्ट, डॉक्टर और फार्मेसी स्टाफ के लिए मानक प्रक्रियाओं का पालन करें[cite: 2]।")
