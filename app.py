import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import os
import json

st.set_page_config(page_title="Normal Child Clinic - Management Portal", layout="wide")

# --- 🔍 इमेज स्कैनर ---
def find_clinic_image(keyword):
    search_paths = [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]
    for path in search_paths:
        if os.path.exists(path):
            try:
                for file in os.listdir(path):
                    if keyword.lower() in file.lower() and file.lower().endswith(('.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG')):
                        return os.path.join(path, file)
            except:
                pass
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

# Google Sheets सुरक्षित कनेक्शन
@st.cache_resource
def connect_to_sheets():
    try:

        if "gcp_service_account" in st.secrets:

            gc = gspread.service_account_from_dict(
                dict(st.secrets["gcp_service_account"])
            )

        else:

            gc = gspread.service_account(
                filename="secret_key.json"
            )

        sh = gc.open("Clinic_Management_Database")
        return sh, None

    except Exception as e:
        return None, str(e)
    

sh, raw_error = connect_to_sheets()

if sh is None:
    st.error("❌ Google Sheet से कनेक्शन नहीं हो पाया!")
    st.stop()

# --- 🔒 क्लाउड डेटा लोडर ---
@st.cache_data(ttl=5)
def load_cloud_data_fast(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        all_rows = worksheet.get_all_values()
        if not all_rows or len(all_rows) < 1:
            return pd.DataFrame()
        
        headers = [str(h).strip() for h in all_rows[0]]
        df = pd.DataFrame(all_rows[1:], columns=headers)
        
        # --- ऑटोमैटिक हेडर फिक्स ---
        if sheet_name == "Attendance":
            if "Staff ID" in df.columns:
                df = df.rename(columns={"Staff ID": "Staff_ID"})
        
        if df.empty:
            return df
            
        if sheet_name == "Patients":
            if 'Fees' in df.columns:
                df['Fees'] = df['Fees'].astype(str).str.replace('₹', '', regex=False).str.replace('/-', '', regex=False).str.replace(',', '', regex=False).str.strip()
                df['Fees'] = pd.to_numeric(df['Fees'], errors='coerce').fillna(0).astype(int)
            if 'Total Fees' in df.columns:
                df['Total Fees'] = df['Total Fees'].astype(str).str.replace('₹', '', regex=False).str.replace('/-', '', regex=False).str.replace(',', '', regex=False).str.strip()
                df['Total Fees'] = pd.to_numeric(df['Total Fees'], errors='coerce').fillna(0).astype(int)
        return df
    except:
        return pd.DataFrame()

# --- ⚡ सुपरफास्ट बैच फीस सिंक ---
def sync_total_fees_batch(sh, target_date, center_name):
    try:
        p_sheet = sh.worksheet("Patients")
        all_p_rows = p_sheet.get_all_values()
        matching_rows = []
        total_fees_day = 0
        existing_target_row = None
        
        for r_idx, row in enumerate(all_p_rows[1:], start=2):
            if len(row) >= 9:
                if str(row[6]).strip() == center_name and str(row[7]).strip() == target_date:
                    matching_rows.append(r_idx)
                    f_val = str(row[8]).replace('₹','').replace('/-','').replace(',','').strip()
                    try: total_fees_day += int(float(f_val))
                    except: pass
                    
                    if len(row) >= 10 and str(row[9]).strip() != "":
                        existing_target_row = r_idx
                        
        if matching_rows:
            if datetime.now().hour < 17:
                target_r = matching_rows[-1]
            else:
                target_r = existing_target_row if (existing_target_row and existing_target_row in matching_rows) else matching_rows[-1]
            
            updates = []
            for r in matching_rows:
                val = int(total_fees_day) if r == target_r else ""
                updates.append({'range': f'J{r}', 'values': [[val]]})
            p_sheet.batch_update(updates)
    except:
        pass

# --- 📈 डेली समरी सिंक ---
def sync_daily_collection_to_sheet(sh, date_str, center_name):
    try:
        try:
            summary_sheet = sh.worksheet("Daily_Summary")
        except:
            summary_sheet = sh.add_worksheet(title="Daily_Summary", rows="100", cols="3")
            summary_sheet.update(range_name="A1:C1", values=[["Date", "Center", "Total Collection"]])
        
        p_df = load_cloud_data_fast("Patients")
        if p_df.empty: total_coll = 0
        else:
            filtered = p_df[(p_df['Date'] == date_str) & (p_df['Center'] == center_name)]
            total_coll = filtered['Fees'].sum() if 'Fees' in filtered.columns else 0
        
        summary_records = summary_sheet.get_all_records()
        row_idx = None
        for idx, r in enumerate(summary_records):
            if str(r.get('Date')) == str(date_str) and str(r.get('Center')) == str(center_name):
                row_idx = idx + 2
                break
        if row_idx: summary_sheet.update_cell(row_idx, 3, int(total_coll))
        else: summary_sheet.append_row([str(date_str), str(center_name), int(total_coll)])
    except:
        pass

# --- 👥 स्टाफ मंथली रिपोर्ट सिंक ---
def sync_monthly_attendance_to_sheet(sh, summary_df, month_year, center_filter):
    try:
        try:
            m_sheet = sh.worksheet("Monthly_Attendance_Summary")
        except:
            m_sheet = sh.add_worksheet(title="Monthly_Attendance_Summary", rows="1000", cols="8")
            m_sheet.update(range_name="A1:H1", values=[["Staff ID", "Staff Name", "Role", "Center", "Total Present (दिन)", "Total Absent (दिन)", "Total Leave (दिन)", "Month-Year"]])
        
        all_rows = m_sheet.get_all_values()
        rows_to_keep = [all_rows[0]] 
        
        for row in all_rows[1:]:
            if len(row) >= 8:
                row_center = str(row[3]).strip()
                row_my = str(row[7]).strip()
                if row_my == month_year:
                    if center_filter == "सभी सेंटर्स (All Centers)" or row_center == center_filter:
                        continue
            rows_to_keep.append(row)
            
        for _, row in summary_df.iterrows():
            rows_to_keep.append([
                str(row['Staff ID']), str(row['Staff Name']), str(row['Role']), 
                str(row['Center']), int(row['Total Present (दिन)']), 
                int(row['Total Absent (दिन)']), int(row['Total Leave (दिन)']), str(row['Month-Year'])
            ])
            
        m_sheet.clear()
        m_sheet.update(range_name=f"A1:H{len(rows_to_keep)}", values=rows_to_keep)
        return True
    except Exception as e:
        return False

# --- 🔑 लाइव पासवर्ड मैनेजर ---
@st.cache_data(ttl=5)
def get_live_passwords():
    try:
        password_sheet = sh.worksheet("Passwords")
        records = password_sheet.get_all_records()
        return {r['Center']: str(r['Password']) for r in records if r['Center']}
    except:
        return {"Raipur": "raipur@123", "HR_Admin": "admin@hr"}

PASSWORDS = get_live_passwords()

if banner_file: st.image(banner_file, width=280)
else: st.markdown('<div style="background: linear-gradient(135deg, #0b3c4f 0%, #008080 100%); padding: 8px 15px; border-radius: 6px; display: inline-block; margin-bottom: 15px;"><h4 style="color: white; margin: 0; font-size: 15px;">🏥 NORMAL CHILD CLINIC</h4></div>', unsafe_allow_html=True)

st.sidebar.markdown("<h3 style='text-align: center; color: white;'>🔒 CONTROL PANEL</h3>", unsafe_allow_html=True)
if logo_file:
    st.sidebar.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    st.sidebar.image(logo_file, width=100)
    st.sidebar.markdown("</div>", unsafe_allow_html=True)

live_centers = list(PASSWORDS.keys())
actual_centers = [c for c in live_centers if c != "HR_Admin"]
actual_centers.sort()

login_options = actual_centers + ["HR_Admin"]
selected_center = st.sidebar.selectbox("🎯 सेंटर का चयन करें (Center):", login_options)
input_password = st.sidebar.text_input(f"🔑 {selected_center} का पासवर्ड डालें:", type="password")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'current_center' not in st.session_state:
    st.session_state['current_center'] = selected_center

if st.session_state['current_center'] != selected_center:
    st.session_state['logged_in'] = False
    st.session_state['current_center'] = selected_center

if st.sidebar.button("🚀 Login"):
    if input_password == PASSWORDS.get(selected_center) or input_password == PASSWORDS.get("HR_Admin"):
        st.session_state['logged_in'] = True
    else:
        st.session_state['logged_in'] = False
        st.sidebar.error("❌ गलत पासवर्ड!")

today_date = datetime.today().strftime('%Y-%m-%d')

if st.session_state['logged_in']:
    st.sidebar.success("🔓 एक्सेस स्वीकृत")
    
    if selected_center == "HR_Admin":
        st.sidebar.markdown("---")
        admin_view = st.sidebar.selectbox("🏢 सेंटर व्यू बदलें (Master Filter):", ["सभी सेंटर्स (All Centers)"] + actual_centers)
    else:
        admin_view = selected_center

    menu_options = ["🏠 डैशबोर्ड (Dashboard)", "👥 स्टाफ मैनेजमेंट (HR & Staff)", "📅 दैनिक हाजिरी (Attendance)", "🧒 मरीज रजिस्ट्रेशन (Patient Entry)", "📊 रिपोर्ट中心 (Advanced Reports)"]
    if selected_center == "HR_Admin": menu_options.append("🔑 पासवर्ड व क्लिनिक मैनेजर")
    menu = st.sidebar.radio("🧭 मेनू नेविगेशन:", menu_options)
    
    if menu == "🏠 डैशबोर्ड (Dashboard)":
        st.markdown(f"<h2>📊 {admin_view} ओवरव्यू</h2>", unsafe_allow_html=True)
        if selected_center == "HR_Admin":
            for c in actual_centers: sync_total_fees_batch(sh, today_date, c)
        else:
            sync_total_fees_batch(sh, today_date, selected_center)
        
        staff_df = load_cloud_data_fast("Staff")
        patients_df = load_cloud_data_fast("Patients")
        
        if admin_view == "सभी सेंटर्स (All Centers)":
            center_staff = staff_df if not staff_df.empty else pd.DataFrame()
            filtered_patients = patients_df[patients_df['Date'] == today_date] if not patients_df.empty else pd.DataFrame()
        else:
            center_staff = staff_df[staff_df['Center'] == admin_view] if not staff_df.empty else pd.DataFrame()
            filtered_patients = patients_df[(patients_df['Center'] == admin_view) & (patients_df['Date'] == today_date)] if not patients_df.empty else pd.DataFrame()

        total_fees_collected = filtered_patients['Fees'].sum() if not filtered_patients.empty and 'Fees' in filtered_patients.columns else 0

        col1, col2, col3 = st.columns(3)
        with col1: st.markdown(f'<div class="metric-card"><div class="metric-title">👥 कुल एक्टिव स्टाफ</div><div class="metric-value">{len(center_staff)}</div></div>', unsafe_allow_html=True)
        with col2: st.markdown(f'<div class="metric-card" style="border-top-color:#ff9f43;"><div class="metric-title">🧒 आज के पंजीकृत बच्चे</div><div class="metric-value">{len(filtered_patients)}</div></div>', unsafe_allow_html=True)
        with col3: st.markdown(f'<div class="metric-card" style="border-top-color:#28c76f;"><div class="metric-title">💵 कुल फीस कलेक्शन</div><div class="metric-value" style="color:#28c76f;">₹ {total_fees_collected}/-</div></div>', unsafe_allow_html=True)
        
        st.write("---")
        st.markdown(f"### 📋 आज के पंजीकृत मरीज ({today_date})")
        if not filtered_patients.empty:
            cols_to_show = [c for c in ['Child Name', 'Parent Name', 'Age', 'Condition', 'Mobile', 'Fees', 'Total Fees', 'Center', 'Patient Type'] if c in filtered_patients.columns]
            st.dataframe(filtered_patients[cols_to_show].reset_index(drop=True), use_container_width=True)
        else:
            st.info("💡 कोई मरीज दर्ज नहीं है।")

    elif menu == "👥 स्टाफ मैनेजमेंट (HR & Staff)":
        st.markdown("<h2>👥 स्टाफ मैनेजमेंट पोर्टल</h2>", unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["➕ नया कर्मचारी जोड़ें", "📋 वर्तमान स्टाफ सूची देखें"])
        staff_df = load_cloud_data_fast("Staff")
        with tab1:
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                s_name = st.text_input("कर्मचारी का पूरा नाम:")
                s_role = st.selectbox("पद:", ["Homeopathic Doctor", "Pharmacist (Medicine Maker)", "Receptionist", "Maid / Housekeeping"])
                if selected_center == "HR_Admin":
                    s_target_center = st.selectbox("🎯 किस सेंटर के लिए जोड़ना है?:", actual_centers)
                else:
                    s_target_center = selected_center
            with col_s2:
                s_mobile = st.text_input("📞 मोबाइल नंबर:", max_chars=10)
                s_salary = st.number_input("💵 मासिक सैलरी (₹):", min_value=0, value=0, step=1000)
            if st.button("🚀 क्लाउड पर सेव करें"):
                if s_name and s_mobile:
                    sh.worksheet("Staff").append_row([len(staff_df) + 1, s_name, s_role, str(s_mobile), s_target_center, int(s_salary)])
                    st.cache_data.clear()
                    st.success(f"🎉 {s_name} को सफलतापूर्वक {s_target_center} सेंटर में जोड़ दिया गया है!")
                    st.rerun()
        with tab2:
            if admin_view == "सभी सेंटर्स (All Centers)":
                view_staff_df = staff_df if not staff_df.empty else pd.DataFrame()
            else:
                view_staff_df = staff_df[staff_df['Center'] == admin_view] if not staff_df.empty else pd.DataFrame()
            if not view_staff_df.empty: 
                st.dataframe(view_staff_df[['ID', 'Name', 'Role', 'Mobile', 'Salary', 'Center']].reset_index(drop=True), use_container_width=True)
            else: 
                st.info("इस फ़िल्टर पर अभी कोई स्टाफ डेटा नहीं है।")

    elif menu == "📅 दैनिक हाजिरी (Attendance)":
        st.markdown("<h2>📅 डिजिटल हाजिरी रजिस्टर</h2>", unsafe_allow_html=True)
        staff_df = load_cloud_data_fast("Staff")
        if admin_view == "सभी सेंटर्स (All Centers)":
            att_center = st.selectbox("🎯 हाजिरी रजिस्टर ओपन करने के लिए सेंटर चुनें:", actual_centers)
        else:
            att_center = admin_view
        center_staff = staff_df[staff_df['Center'] == att_center] if not staff_df.empty else pd.DataFrame()
        if center_staff.empty:
            st.warning(f"⚠️ {att_center} सेंटर पर कोई स्टाफ उपलब्ध नहीं है।")
        else:
            attendance_dict = {}
            for index, row in center_staff.iterrows():
                col_s, col_a = st.columns([2, 1])
                col_s.markdown(f"<p style='font-size: 15px; margin-top:5px;'>👤 <b>{row['Name']}</b> ({row['Role']})</p>", unsafe_allow_html=True)
                status = col_a.radio(f"Status for {row['Name']}", ["Present", "Absent", "Leave"], key=str(row['ID']), label_visibility="collapsed", horizontal=True)
                attendance_dict[row['ID']] = {"name": row['Name'], "status": status}
            if st.button("💾 अटेंडेंस LOCK और सबमिट करें"):
                try:
                    att_sheet = sh.worksheet("Attendance")
                    all_rows = att_sheet.get_all_values()
                    for s_id, info in attendance_dict.items():
                        existing_row_idx = None
                        for r_idx, row in enumerate(all_rows[1:], start=2):
                            if len(row) >= 4:
                                if str(row[1]).strip() == str(s_id) and str(row[3]).strip() == str(today_date):
                                    existing_row_idx = r_idx
                                    break
                        if existing_row_idx:
                            att_sheet.update_cell(existing_row_idx, 5, info['status'])
                            att_sheet.update_cell(existing_row_idx, 6, att_center)
                        else:
                            next_id = len(all_rows)
                            att_sheet.append_row([next_id, int(s_id), info['name'], today_date, info['status'], att_center])
                            all_rows.append([next_id, int(s_id), info['name'], today_date, info['status'], att_center])
                    st.cache_data.clear()
                    st.success(f"✅ {att_center} सेंटर का अटेंडेंस शीट डेटा lock हो गया है!")
                    st.rerun()
                except Exception as e:
                    st.error(f"एरर: {e}")

    elif menu == "🧒 मरीज रजिस्ट्रेशन (Patient Entry)":
        st.markdown("<h2>🧒 मरीज डिजिटल एंट्री व संशोधन</h2>", unsafe_allow_html=True)
        tab_p1, tab_p2 = st.tabs(["🧒 नया मरीज रजिस्ट्रेशन", "✏️ मरीज विवरण एडिट करें"])
        patients_df = load_cloud_data_fast("Patients")
        if admin_view == "सभी सेंटर्स (All Centers)":
            center_patients = patients_df if not patients_df.empty else pd.DataFrame()
        else:
            center_patients = patients_df[patients_df['Center'] == admin_view] if not patients_df.empty else pd.DataFrame()
        with tab_p1:
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                c_name = st.text_input("🧒 विशेष बच्चे का नाम:")
                p_name = st.text_input("👨‍👩‍👦 माता या पिता का नाम:")
                p_mobile = st.text_input("📞 अभिभावक का मोबाइल नंबर:", max_chars=10)
                p_type = st.selectbox("📋 मरीज का प्रकार:", ["New Patient (नया)", "Old Patient (पुराना)"])
                if selected_center == "HR_Admin":
                    p_target_center = st.selectbox("🎯 किस सेंटर में मरीज एंट्री डालनी है?:", actual_centers)
                else:
                    p_target_center = selected_center
            with col_p2:
                c_age = st.number_input("🎂 उम्र:", min_value=1, max_value=18, value=6)
                c_cond = st.selectbox("🩺 मुख्य समस्या:", ["Autism (ऑटिज़्म)", "ADHD", "Cerebral Palsy", "Delayed Speech", "Other"])
                c_fees = st.number_input("💵 प्राप्त फीस राशि (₹):", min_value=0, value=0, step=100)
            if st.button("🎯 मरीज रिकॉर्ड सुरक्षित करें"):
                if c_name and p_name and p_mobile:
                    p_sheet = sh.worksheet("Patients")
                    all_p_rows = p_sheet.get_all_values()
                    next_p_id = len(all_p_rows)
                    p_sheet.append_row([next_p_id, c_name, p_name, int(c_age), c_cond, str(p_mobile), p_target_center, today_date, int(c_fees), "", p_type])
                    sync_total_fees_batch(sh, today_date, p_target_center)
                    sync_daily_collection_to_sheet(sh, today_date, p_target_center)
                    st.cache_data.clear()
                    st.success(f"🎯 रिकॉर्ड {p_target_center} सेंटर में सुरक्षित हो गया है!")
                    st.rerun()
        with tab_p2:
            if center_patients.empty: st.info("कोई मरीज डेटा उपलब्ध नहीं है।")
            else:
                patient_options = {f"[{row['Center']}] {row['Child Name']} s/o {row['Parent Name']} (ID: {row['ID']})": row['ID'] for _, row in center_patients.iterrows()}
                selected_pat_label = st.selectbox("संशोधन के लिए मरीज चुनें:", list(patient_options.keys()))
                pat_data = center_patients[center_patients['ID'] == patient_options[selected_pat_label]].iloc[0]
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    edit_c_name = st.text_input("बच्चे का नाम बदलें:", value=str(pat_data['Child Name']))
                    edit_p_name = st.text_input("अभिभावक का नाम बदलें:", value=str(pat_data['Parent Name']))
                    edit_p_mobile = st.text_input("मोबाइल नंबर बदलें:", value=str(pat_data['Mobile']), max_chars=10)
                    edit_p_type = st.selectbox("मरीज का प्रकार बदलें:", ["New Patient (नया)", "Old Patient (पुराना)"], index=0 if 'Patient Type' not in pat_data or pat_data['Patient Type'] == 'New Patient (नया)' else 1)
                with col_e2:
                    edit_c_age = st.number_input("उम्र बदलें:", min_value=1, max_value=18, value=int(pat_data['Age']))
                    edit_c_cond = st.selectbox("समस्या बदलें:", ["Autism (ऑटिज़्म)", "ADHD", "Cerebral Palsy", "Delayed Speech", "Other"])
                    edit_c_fees = st.number_input("फीस राशि बदलें (₹):", min_value=0, value=int(pat_data['Fees']) if 'Fees' in pat_data else 0, step=100)
                if st.button("💾 मरीज डेटा अपडेट करें"):
                    p_sheet = sh.worksheet("Patients")
                    real_p_row_idx = patients_df[patients_df['ID'] == patient_options[selected_pat_label]].index[0] + 2
                    p_orig_center = str(pat_data['Center'])
                    p_sheet.update(range_name=f"A{real_p_row_idx}:K{real_p_row_idx}", values=[[int(patient_options[selected_pat_label]), edit_c_name, edit_p_name, int(edit_c_age), edit_c_cond, str(edit_p_mobile), p_orig_center, str(pat_data['Date']), int(edit_c_fees), "", edit_p_type]])
                    target_date = str(pat_data['Date'])
                    sync_total_fees_batch(sh, target_date, p_orig_center)
                    sync_daily_collection_to_sheet(sh, target_date, p_orig_center)
                    st.cache_data.clear()
                    st.success("📝 रिकॉर्ड सफलतापूर्वक बैच मोड में अपडेटेड!")
                    st.rerun()

    elif menu == "📊 रिपोर्ट中心 (Advanced Reports)":
        st.markdown("<h2>📊 क्लिनिक एडवांस्ड रिपोर्ट पैनल</h2>", unsafe_allow_html=True)
        tab_report1, tab_report2 = st.tabs(["🧒 मरीज एवं कलेक्शन रिपोर्ट", "👥 स्टाफ मासिक अटेंडेंस रिपोर्ट"])
        with tab_report1:
            patients_df = load_cloud_data_fast("Patients")
            if not patients_df.empty:
                if admin_view == "सभी सेंटर्स (All Centers)": center_df = patients_df.reset_index(drop=True)
                else: center_df = patients_df[patients_df['Center'] == admin_view].reset_index(drop=True)
                if not center_df.empty:
                    col_f1, col_f2 = st.columns(2)
                    with col_f1: report_filter = st.selectbox("📅 रिपोर्ट फ़िल्टर मोड चुनें:", ["आज का रिकॉर्ड (Today Only)", "किसी पुरानी तारीख का रिकॉर्ड (Past Date)", "शुरू से अब तक का पूरा रिकॉर्ड (All Time)"])
                    filtered_df = center_df.copy()
                    if report_filter == "आज का रिकॉर्ड (Today Only)": filtered_df = center_df[center_df['Date'] == today_date]
                    elif report_filter == "किसी पुरानी तारीख का रिकॉर्ड (Past Date)":
                        with col_f2: selected_report_date = st.date_input("📆 पुरानी तारीख चुनें (Select Past Date):", datetime.today())
                        date_str = selected_report_date.strftime('%Y-%m-%d')
                        filtered_df = center_df[center_df['Date'] == date_str]
                    t_patients = len(filtered_df)
                    t_fees = filtered_df['Fees'].sum() if 'Fees' in filtered_df.columns else 0
                    st.markdown(f"##### 📈 चयनित व्यू अवधि का परफॉर्मेंस समरी")
                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric("🧒 कुल पंजीकृत मरीज", t_patients)
                    col_m2.metric("💵 कुल प्राप्त फीस", f"₹ {t_fees}/-")
                    
                    if not filtered_df.empty:
                        csv = filtered_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 रिपोर्ट Excel (CSV) डाउनलोड करें",
                            data=csv,
                            file_name=f'Clinic_Report_{admin_view}_{today_date}.csv',
                            mime='text/csv',
                        )
                    
                    st.write("---")
                    cols_to_show = [c for c in ['ID', 'Child Name', 'Parent Name', 'Age', 'Condition', 'Mobile', 'Date', 'Fees', 'Total Fees', 'Center', 'Patient Type'] if c in filtered_df.columns]
                    if not filtered_df.empty: st.dataframe(filtered_df[cols_to_show].reset_index(drop=True), use_container_width=True)
                    else: st.info("💡 चयनित क्राइटेरिया के लिए कोई मरीज रिकॉर्ड मौजूद नहीं है।")
                else: st.info("💡 इस व्यू मोड पर कोई डेटा नहीं मिला।")
            else: st.error("❌ डेटाबेस लोड करने में समस्या आ रही है।")
        with tab_report2:
            st.markdown("### 📅 स्टाफ वाइज मंथली अटेंडेंस कैलकुलेटर")
            staff_data_df = load_cloud_data_fast("Staff")
            att_data_df = load_cloud_data_fast("Attendance")
            
            if 'Staff_ID' not in att_data_df.columns:
                st.error("⚠️ अटेंडेंस शीट में 'Staff_ID' कॉलम नहीं मिल रहा। कृपया अपनी Google Sheet में हेडर चेक करें。")
            elif staff_data_df.empty or att_data_df.empty:
                st.info("💡 अभी सिस्टम में स्टाफ या अटेंडेंस का कोई रिकॉर्ड उपलब्ध नहीं है।")
            else:
                col_y1, col_y2 = st.columns(2)
                with col_y1: selected_year = st.selectbox("📅 साल चुनें:", ["2026", "2025", "2027"], index=0)
                with col_y2:
                    months_list = [("January", "01"), ("February", "02"), ("March", "03"), ("April", "04"), ("May", "05"), ("June", "06"), ("July", "07"), ("August", "08"), ("September", "09"), ("October", "10"), ("November", "11"), ("December", "12")]
                    selected_month_label = st.selectbox("📆 महीना चुनें:", [m[0] for m in months_list], index=int(datetime.today().month)-1)
                    selected_month_num = next(m[1] for m in months_list if m[0] == selected_month_label)
                target_month_str = f"{selected_year}-{selected_month_num}"
                month_year_label = f"{selected_month_label} {selected_year}"
                if admin_view == "सभी सेंटर्स (All Centers)": filtered_staff = staff_data_df.copy()
                else: filtered_staff = staff_data_df[staff_data_df['Center'] == admin_view]
                if filtered_staff.empty: st.warning(f"⚠️ चयनित व्यू ({admin_view}) में कोई स्टाफ सदस्य पंजीकृत नहीं है।")
                else:
                    summary_rows = []
                    for _, s_row in filtered_staff.iterrows():
                        s_id = str(s_row['ID']).strip()
                        match_att = att_data_df[(att_data_df['Staff_ID'].astype(str).str.strip() == s_id) & (att_data_df['Date'].astype(str).str.startswith(target_month_str))]
                        p_count = len(match_att[match_att['Status'].str.lower() == 'present'])
                        a_count = len(match_att[match_att['Status'].str.lower() == 'absent'])
                        l_count = len(match_att[match_att['Status'].str.lower() == 'leave'])
                        summary_rows.append({"Staff ID": s_id, "Staff Name": s_row['Name'], "Role": s_row['Role'], "Center": s_row['Center'], "Total Present (दिन)": p_count, "Total Absent (दिन)": a_count, "Total Leave (दिन)": l_count, "Month-Year": month_year_label})
                    summary_df = pd.DataFrame(summary_rows)
                    sheet_synced = sync_monthly_attendance_to_sheet(sh, summary_df, month_year_label, admin_view)
                    if sheet_synced: st.success(f"📊 {month_year_label} की रिपोर्ट लाइव सिंक हो गई है!")
                    
                    # --- EXPORT BUTTON FOR STAFF ---
                    if not summary_df.empty:
                        csv_staff = summary_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 स्टाफ रिपोर्ट Excel (CSV) डाउनलोड करें",
                            data=csv_staff,
                            file_name=f'Staff_Report_{admin_view}_{target_month_str}.csv',
                            mime='text/csv',
                        )
                    
                    st.dataframe(summary_df.reset_index(drop=True), use_container_width=True)

    elif menu == "🔑 पासवर्ड व क्लिनिक मैनेजर":
        st.markdown("<h2>🔑 पासवर्ड व सेंटर मैनेजमेंट</h2>", unsafe_allow_html=True)
        
        tab_pwd, tab_center = st.tabs(["🔐 पासवर्ड मैनेजमेंट", "🏥 सेंटर मैनेजमेंट"])
        
        pwd_sheet = sh.worksheet("Passwords")
        p_records = pwd_sheet.get_all_records()
        
        with tab_pwd:
            edit_center = st.selectbox("सेंटर चुनें:", list(PASSWORDS.keys()))
            new_pwd_input = st.text_input("नया पासवर्ड:")
            if st.button("💾 पासवर्ड अपडेट करें"):
                row_to_update = next((idx + 2 for idx, r in enumerate(p_records) if r['Center'] == edit_center), None)
                if row_to_update:
                    pwd_sheet.update(range_name=f"B{row_to_update}", values=[[new_pwd_input.strip()]])
                    st.cache_data.clear()
                    st.success("🎉 पासवर्ड अपडेट हो गया!")
                    st.rerun()

        with tab_center:
            st.subheader("➕ नया सेंटर जोड़ें")
            new_center_name = st.text_input("नये सेंटर का नाम:")
            new_center_pwd = st.text_input("नये सेंटर का पासवर्ड:", type="password")
            if st.button("🚀 नया सेंटर जोड़ें"):
                if new_center_name and new_center_pwd:
                    pwd_sheet.append_row([new_center_name, new_center_pwd])
                    st.cache_data.clear()
                    st.success(f"🎉 सेंटर '{new_center_name}' सफलतापूर्वक जुड़ गया!")
                    st.rerun()
            
            st.markdown("---")
            st.subheader("🗑️ सेंटर हटाएं")
            del_center = st.selectbox("हटाने के लिए सेंटर चुनें:", actual_centers)
            if st.button("❌ सेंटर डिलीट करें"):
                row_idx = next((idx + 2 for idx, r in enumerate(p_records) if r['Center'] == del_center), None)
                if row_idx:
                    pwd_sheet.delete_rows(row_idx)
                    st.cache_data.clear()
                    st.success(f"🗑️ सेंटर '{del_center}' हटा दिया गया है!")
                    st.rerun()
else:
    st.info("🔒 कृपया डेटा एक्सेस करने के लिए पासवर्ड डालकर 'Login' बटन पर क्लिक करें।")
