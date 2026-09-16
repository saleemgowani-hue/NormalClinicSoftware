import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import hashlib
import hmac
import secrets
import logging
import calendar
import io
import re
import urllib.parse
import pyotp
import qrcode
from fpdf import FPDF

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("clinic_app")

# --- 🧾 PDF हेल्पर्स ---
# PDF हमेशा पूरी तरह अंग्रेज़ी में रहती है: हिंदी वर्ण हटा दिए जाते हैं, और उसके बाद बचे
# खाली कोष्ठक/डबल-स्पेस भी साफ कर दिए जाते हैं ताकि "Autism ()" जैसा अधूरा टेक्स्ट न दिखे।
def _pdf_safe(text):
    s = str(text).encode('latin-1', 'ignore').decode('latin-1')
    s = re.sub(r'\(\s*\)', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def generate_receipt_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Normal Child Clinic - Fee Receipt", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.ln(4)
    fields = [
        ("Receipt No", str(data.get('ID', ''))),
        ("Date", str(data.get('Date', ''))),
        ("Center", _pdf_safe(data.get('Center', ''))),
        ("Child Name", _pdf_safe(data.get('Child Name', ''))),
        ("Parent Name", _pdf_safe(data.get('Parent Name', ''))),
        ("Mobile", str(data.get('Mobile', ''))),
        ("Age", str(data.get('Age', ''))),
        ("Doctor", _pdf_safe(data.get('Doctor', ''))),
        ("Amount Paid (Rs.)", str(data.get('Fees', ''))),
        ("Total Charge (Rs.)", str(data.get('Total Charge', data.get('Fees', '')))),
    ]
    for label, value in fields:
        pdf.cell(60, 8, f"{label}:", border=0)
        pdf.cell(0, 8, value, ln=True)
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 8, "Thank you for visiting!", ln=True, align="C")
    return bytes(pdf.output())

def generate_salary_slip_pdf(staff_name, role, center, month_label, monthly_salary, present_days, absent_days, leave_days, total_days_in_month):
    per_day = monthly_salary / total_days_in_month if total_days_in_month else 0
    payable = round(per_day * present_days)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Normal Child Clinic - Salary Slip", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.ln(4)
    fields = [
        ("Month", month_label),
        ("Staff Name", _pdf_safe(staff_name)),
        ("Role", _pdf_safe(role)),
        ("Center", _pdf_safe(center)),
        ("Monthly Salary (Rs.)", str(int(monthly_salary))),
        ("Days in Month", str(total_days_in_month)),
        ("Present Days", str(present_days)),
        ("Absent Days", str(absent_days)),
        ("Leave Days", str(leave_days)),
        ("Payable Amount (Rs.)", str(int(payable))),
    ]
    for label, value in fields:
        pdf.cell(70, 8, f"{label}:", border=0)
        pdf.cell(0, 8, value, ln=True)
    return bytes(pdf.output())

def generate_table_pdf(title, df, columns):
    pdf = FPDF(orientation='L')
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _pdf_safe(title), ln=True, align="C")
    pdf.ln(2)
    col_width = 270 / max(len(columns), 1)
    pdf.set_font("Helvetica", "B", 8)
    for col in columns:
        pdf.cell(col_width, 8, _pdf_safe(col)[:22], border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    for _, row in df.head(200).iterrows():
        for col in columns:
            pdf.cell(col_width, 7, _pdf_safe(row[col])[:24], border=1)
        pdf.ln()
    return bytes(pdf.output())

def generate_prescription_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Normal Child Clinic - Prescription", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.ln(4)
    header_fields = [
        ("Date", str(data.get('Date', ''))),
        ("Center", _pdf_safe(data.get('Center', ''))),
        ("Doctor", _pdf_safe(data.get('Doctor', ''))),
        ("Patient", _pdf_safe(data.get('Child Name', ''))),
        ("Parent", _pdf_safe(data.get('Parent Name', ''))),
        ("Mobile", str(data.get('Mobile', ''))),
        ("Weight (kg)", str(data.get('Weight (kg)', '')) if data.get('Weight (kg)') else "-"),
    ]
    for label, value in header_fields:
        pdf.cell(45, 7, f"{label}:", border=0)
        pdf.cell(0, 7, value, ln=True)
    pdf.ln(4)

    def section(title, content):
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, title, ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _pdf_safe(content) if content else "-")
        pdf.ln(2)

    section("Chief Complaint / Diagnosis:", data.get('Chief Complaint', ''))
    section("Prescription:", data.get('Prescription', ''))
    section("Medicine Given:", data.get('Medicine Given', ''))
    if data.get('Notes'):
        section("Notes:", data.get('Notes', ''))

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Charges", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Consultation Charges: Rs. {int(data.get('Consultation Charges', 0) or 0)}", ln=True)
    pdf.cell(0, 6, f"Medicine Charges: Rs. {int(data.get('Medicine Charges', 0) or 0)}", ln=True)
    pdf.cell(0, 6, f"Total Fees Collected: Rs. {int(data.get('Total Fees', 0) or 0)}", ln=True)
    if data.get('Next Follow-up Date'):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, f"Next Follow-up: {data.get('Next Follow-up Date', '')}", ln=True)

    return bytes(pdf.output())

# --- 📲 WhatsApp मैसेज हेल्पर ---
def _clean_whatsapp_number(mobile):
    digits = ''.join(ch for ch in str(mobile) if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return digits

def build_whatsapp_url(mobile, message):
    number = _clean_whatsapp_number(mobile)
    return f"https://wa.me/{number}?text={urllib.parse.quote(message)}"

def render_whatsapp_sender(data, key_prefix):
    st.markdown("**📲 WhatsApp मैसेज भेजें**")
    template_choice = st.selectbox(
        "टेम्पलेट चुनें:",
        ["Appointment Confirmation", "Fees Receipt", "Next Follow-up Reminder"],
        key=f"{key_prefix}_wa_template",
    )
    child_name = data.get('Child Name', '')
    parent_name = data.get('Parent Name', '')
    center = data.get('Center', '')
    date_str = data.get('Date', '')
    doctor = data.get('Doctor', '')
    try:
        fees = int(data.get('Fees', 0) or 0)
    except (TypeError, ValueError):
        fees = 0
    try:
        total_charge = int(data.get('Total Charge', fees) or fees)
    except (TypeError, ValueError):
        total_charge = fees
    due = max(0, total_charge - fees)

    if template_choice == "Next Follow-up Reminder":
        followup_date = st.date_input("अगली फॉलो-अप तारीख:", datetime.today() + timedelta(days=7), key=f"{key_prefix}_followup_date")
        message = (
            f"Hello {parent_name},\n\n"
            f"This is a reminder from Normal Child Clinic ({center}) for {child_name}'s next follow-up visit "
            f"on {followup_date.strftime('%d-%b-%Y')}.\n\n"
            f"Please arrive 10 minutes early.\n\nThank you!"
        )
    elif template_choice == "Fees Receipt":
        payment_line = f"Balance Due: Rs. {due}" if due > 0 else "Payment Status: Fully Paid"
        message = (
            f"Hello {parent_name},\n\n"
            f"Thank you for visiting Normal Child Clinic ({center}) on {date_str}.\n"
            f"Patient: {child_name}\n"
            f"Doctor: {doctor}\n"
            f"Amount Paid: Rs. {fees}\n"
            f"{payment_line}\n\n"
            f"Thank you for choosing us!"
        )
    else:
        message = (
            f"Hello {parent_name},\n\n"
            f"This is to confirm {child_name}'s appointment at Normal Child Clinic ({center}) on {date_str}.\n"
            f"Doctor: {doctor}\n\nSee you soon!"
        )

    mobile = str(data.get('Mobile', '')).strip()
    with st.expander("मैसेज प्रीव्यू देखें"):
        st.text(message)

    if _clean_whatsapp_number(mobile):
        st.link_button("📲 WhatsApp पर भेजें", build_whatsapp_url(mobile, message), key=f"{key_prefix}_wa_send")
    else:
        st.caption("⚠️ मोबाइल नंबर उपलब्ध नहीं है।")

def render_appointment_whatsapp(name, mobile, center, date_str, time_slot, token):
    message = (
        f"Hello {name},\n\n"
        f"Your appointment at Normal Child Clinic ({center}) is confirmed.\n"
        f"Date: {date_str}\n"
        f"Time: {time_slot}\n"
        f"Token No: {token}\n\n"
        f"Please arrive 10 minutes early. Thank you!"
    )
    st.markdown("**📲 WhatsApp पर अपॉइंटमेंट डिटेल भेजें**")
    with st.expander("मैसेज प्रीव्यू देखें"):
        st.text(message)
    if _clean_whatsapp_number(mobile):
        st.link_button("📲 WhatsApp पर भेजें", build_whatsapp_url(mobile, message), key=f"appt_wa_{token}_{mobile}")
    else:
        st.caption("⚠️ मोबाइल नंबर उपलब्ध नहीं है।")

# --- 🔐 पासवर्ड हैशिंग हेल्पर्स ---
def hash_password(password):
    salt = secrets.token_hex(16)
    iterations = 260000
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"

def verify_password(stored, provided):
    try:
        algo, iterations, salt, hash_hex = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        dk = hashlib.pbkdf2_hmac('sha256', provided.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except ValueError:
        return False

def is_hashed(stored):
    return stored.startswith("pbkdf2_sha256$")

def is_valid_mobile(mobile):
    return str(mobile).strip().isdigit() and len(str(mobile).strip()) == 10

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
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Poppins', 'Segoe UI', sans-serif; }
    .main { background: linear-gradient(180deg, #f4f7fa 0%, #eef2f7 100%); }

    h1, h2, h3 { color: #0b3c4f; font-weight: 600 !important; }
    hr { background: linear-gradient(90deg, transparent, #008080, transparent) !important; height: 2px !important; border: none !important; }

    /* --- मेट्रिक कार्ड --- */
    .metric-card {
        background-color: #ffffff; padding: 22px; border-radius: 14px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.06); border-top: 4px solid #008080;
        text-align: center; transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 10px 24px rgba(0,0,0,0.12);
    }
    .metric-title { color: #6c757d; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-value { color: #101010; font-size: 26px; font-weight: 700; margin-top: 6px; }

    /* --- बटन --- */
    .stButton>button, .stDownloadButton>button, .stLinkButton>a {
        background: linear-gradient(135deg, #00b4d8, #008080) !important;
        color: white !important;
        border-radius: 8px !important; padding: 8px 22px !important;
        font-weight: 600 !important; border: none !important;
        transition: all 0.2s ease-in-out !important;
        box-shadow: 0 3px 8px rgba(0,128,128,0.3) !important;
    }
    .stButton>button:hover, .stDownloadButton>button:hover, .stLinkButton>a:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 14px rgba(0,128,128,0.45) !important;
    }

    /* --- साइडबार बेस --- */
    [data-testid="stSidebar"] { background-color: #0b3c4f !important; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    [data-testid="stSidebar"] input { color: #ffffff !important; background-color: #123b4d !important; }

    /* --- मल्टीकलर साइडबार नेविगेशन मेनू --- */
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] {
        gap: 8px;
    }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] label[data-testid="stRadioOption"] {
        border-radius: 10px !important;
        padding: 10px 14px !important;
        display: block !important;
        width: 100% !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        transition: all 0.15s ease-in-out !important;
    }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] label[data-testid="stRadioOption"]:hover {
        filter: brightness(1.15);
        transform: translateX(3px);
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] > div:nth-of-type(1) label[data-testid="stRadioOption"] { background: linear-gradient(135deg, #00b4d8, #0077b6); }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] > div:nth-of-type(2) label[data-testid="stRadioOption"] { background: linear-gradient(135deg, #9d4edd, #7b2cbf); }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] > div:nth-of-type(3) label[data-testid="stRadioOption"] { background: linear-gradient(135deg, #ff9f43, #f77f00); }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] > div:nth-of-type(4) label[data-testid="stRadioOption"] { background: linear-gradient(135deg, #ff6b9d, #e63980); }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] > div:nth-of-type(5) label[data-testid="stRadioOption"] { background: linear-gradient(135deg, #4895ef, #3a0ca3); }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] > div:nth-of-type(6) label[data-testid="stRadioOption"] { background: linear-gradient(135deg, #2ec4b6, #06923e); }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] > div:nth-of-type(7) label[data-testid="stRadioOption"] { background: linear-gradient(135deg, #f9a826, #f77f00); }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] [data-testid="stRadioGroup"] > div:nth-of-type(8) label[data-testid="stRadioOption"] { background: linear-gradient(135deg, #ef476f, #d90429); }
    [data-testid="stElementContainer"]:has(.menu-nav-anchor) + [data-testid="stElementContainer"] label[data-testid="stRadioOption"][data-selected="true"] {
        box-shadow: 0 0 0 2px #ffffff inset, 0 4px 14px rgba(0,0,0,0.4) !important;
        transform: scale(1.02);
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
# नई कॉलम फीचर्स जोड़ने पर Google Sheet की हेडर रो मैन्युअली बदले बिना भी डेटा सही पढ़ने के लिए
EXPECTED_HEADERS = {
    "Patients": ["ID", "Child Name", "Parent Name", "Age", "Condition", "Mobile", "Center", "Date", "Fees", "Total Fees", "Patient Type", "Doctor", "Total Charge"],
}

@st.cache_data(ttl=20)
def load_cloud_data_fast(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        all_rows = worksheet.get_all_values()
        if not all_rows or len(all_rows) < 1:
            return pd.DataFrame()

        headers = [str(h).strip() for h in all_rows[0]]
        for expected_col in EXPECTED_HEADERS.get(sheet_name, []):
            if expected_col not in headers:
                headers.append(expected_col)

        data_rows = []
        for r in all_rows[1:]:
            r = list(r)
            if len(r) < len(headers):
                r = r + [""] * (len(headers) - len(r))
            elif len(r) > len(headers):
                r = r[:len(headers)]
            data_rows.append(r)

        df = pd.DataFrame(data_rows, columns=headers)

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
            if 'Total Charge' in df.columns:
                df['Total Charge'] = df['Total Charge'].astype(str).str.replace('₹', '', regex=False).str.replace('/-', '', regex=False).str.replace(',', '', regex=False).str.strip()
                df['Total Charge'] = pd.to_numeric(df['Total Charge'], errors='coerce').fillna(0).astype(int)
        if sheet_name == "Expenses" and 'Amount' in df.columns:
            df['Amount'] = df['Amount'].astype(str).str.replace('₹', '', regex=False).str.replace(',', '', regex=False).str.strip()
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0).astype(int)
        if sheet_name == "Consultations":
            if 'Weight (kg)' in df.columns:
                df['Weight (kg)'] = pd.to_numeric(df['Weight (kg)'], errors='coerce').fillna(0)
            for numcol in ['Consultation Charges', 'Medicine Charges', 'Total Fees']:
                if numcol in df.columns:
                    df[numcol] = pd.to_numeric(df[numcol], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        logger.warning(f"load_cloud_data_fast('{sheet_name}') failed: {e}")
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
    except Exception as e:
        logger.warning(f"sync_total_fees_batch failed for {center_name}/{target_date}: {e}")

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
    except Exception as e:
        logger.warning(f"sync_daily_collection_to_sheet failed for {center_name}/{date_str}: {e}")

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
        logger.warning(f"sync_monthly_attendance_to_sheet failed for {month_year}/{center_filter}: {e}")
        return False

# --- 👤 रोल-वाइज मेनू एक्सेस (स्टाफ लॉगिन के लिए) ---
ROLE_MENU_ACCESS = {
    "Homeopathic Doctor": ["🏠 डैशबोर्ड (Dashboard)", "🧒 मरीज रजिस्ट्रेशन (Patient Entry)", "🩺 परामर्श (Consultation)", "📊 रिपोर्ट सेंटर (Advanced Reports)"],
    "Receptionist": ["🏠 डैशबोर्ड (Dashboard)", "📅 दैनिक हाजिरी (Attendance)", "🧒 मरीज रजिस्ट्रेशन (Patient Entry)", "🎫 अपॉइंटमेंट (Appointments)"],
    "Pharmacist (Medicine Maker)": ["🏠 डैशबोर्ड (Dashboard)", "🧒 मरीज रजिस्ट्रेशन (Patient Entry)", "🩺 परामर्श (Consultation)"],
    "Maid / Housekeeping": ["🏠 डैशबोर्ड (Dashboard)"],
}

# --- 📝 ऑडिट लॉग ---
def log_audit(actor, action, details):
    try:
        try:
            audit_sheet = sh.worksheet("Audit_Log")
        except Exception:
            audit_sheet = sh.add_worksheet(title="Audit_Log", rows="1000", cols="4")
            audit_sheet.update(range_name="A1:D1", values=[["Timestamp", "Center/User", "Action", "Details"]])
        audit_sheet.append_row([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), str(actor), str(action), str(details)])
    except Exception as e:
        logger.warning(f"log_audit failed: {e}")

def current_actor():
    if st.session_state.get('login_mode') == 'staff' and st.session_state.get('staff_user'):
        u = st.session_state['staff_user']
        return f"{u['Full Name']} ({u['Role']}, {u['Center']})"
    return selected_center

# --- 🔐 HR_Admin के लिए 2FA (TOTP) हेल्पर्स ---
def get_totp_secret(center_name):
    try:
        pwd_sheet = sh.worksheet("Passwords")
        records = pwd_sheet.get_all_records()
        for r in records:
            if r.get('Center') == center_name:
                return str(r.get('TOTP_Secret', '')).strip()
    except Exception:
        pass
    return ''

def set_totp_secret(center_name, secret):
    try:
        pwd_sheet = sh.worksheet("Passwords")
        headers = pwd_sheet.row_values(1)
        if len(headers) < 3 or headers[2].strip() != 'TOTP_Secret':
            pwd_sheet.update(range_name="C1", values=[["TOTP_Secret"]])
        records = pwd_sheet.get_all_records()
        row_idx = next((idx + 2 for idx, r in enumerate(records) if r.get('Center') == center_name), None)
        if row_idx:
            pwd_sheet.update(range_name=f"C{row_idx}", values=[[secret]])
        st.cache_data.clear()
    except Exception as e:
        logger.warning(f"set_totp_secret failed: {e}")

# --- 🔑 लाइव पासवर्ड मैनेजर ---
@st.cache_data(ttl=5)
def get_live_passwords():
    try:
        password_sheet = sh.worksheet("Passwords")
        records = password_sheet.get_all_records()
        return {r['Center']: str(r['Password']) for r in records if r['Center']}
    except Exception:
        return {}

PASSWORDS = get_live_passwords()

if not PASSWORDS:
    st.error("❌ पासवर्ड डेटा लोड नहीं हो सका। कृपया 'Passwords' शीट जांचें और पेज रीलोड करें।")
    st.stop()

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

login_mode = st.sidebar.radio("🔀 लॉगिन तरीका (Login Mode):", ["🏢 सेंटर लॉगिन (Center Login)", "👤 स्टाफ लॉगिन (Staff Login - Individual)"], key="login_mode_choice", horizontal=True)

if login_mode == "🏢 सेंटर लॉगिन (Center Login)":
    login_options = actual_centers + ["HR_Admin"]
    selected_center = st.sidebar.selectbox("🎯 सेंटर का चयन करें (Center):", login_options)
    input_password = st.sidebar.text_input(f"🔑 {selected_center} का पासवर्ड डालें (Enter Password):", type="password")
    current_identity = f"center:{selected_center}"
else:
    selected_center = None
    staff_username = st.sidebar.text_input("👤 यूज़रनेम (Username):", key="staff_username_input")
    staff_password = st.sidebar.text_input("🔑 पासवर्ड (Password):", type="password", key="staff_password_input")
    current_identity = f"staff:{staff_username.strip().lower()}"

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'current_identity' not in st.session_state:
    st.session_state['current_identity'] = current_identity
if 'login_attempts' not in st.session_state:
    st.session_state['login_attempts'] = 0
if 'lockout_until' not in st.session_state:
    st.session_state['lockout_until'] = None

if st.session_state['current_identity'] != current_identity:
    st.session_state['logged_in'] = False
    st.session_state['staff_user'] = None
    st.session_state['awaiting_totp'] = False
    st.session_state['pending_totp_secret'] = None
    st.session_state['current_identity'] = current_identity

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 5

def _check_and_migrate(center_key, provided_password):
    stored = PASSWORDS.get(center_key)
    if not stored:
        return False
    if is_hashed(stored):
        return verify_password(stored, provided_password)
    if hmac.compare_digest(stored, provided_password):
        try:
            pwd_sheet = sh.worksheet("Passwords")
            p_records = pwd_sheet.get_all_records()
            row_to_update = next((idx + 2 for idx, r in enumerate(p_records) if r['Center'] == center_key), None)
            if row_to_update:
                pwd_sheet.update(range_name=f"B{row_to_update}", values=[[hash_password(provided_password)]])
                st.cache_data.clear()
        except Exception:
            pass
        return True
    return False

def _check_staff_login(username, provided_password):
    users_df = load_cloud_data_fast("Users")
    if users_df.empty or not username:
        return None
    match = users_df[users_df['Username'].astype(str).str.strip().str.lower() == username.strip().lower()]
    if match.empty:
        return None
    user_row = match.iloc[0]
    stored = str(user_row['PasswordHash'])
    if is_hashed(stored) and verify_password(stored, provided_password):
        return {'Username': user_row['Username'], 'Full Name': user_row['Full Name'], 'Role': user_row['Role'], 'Center': user_row['Center']}
    return None

now = datetime.now()
locked_out = st.session_state['lockout_until'] and now < st.session_state['lockout_until']

if locked_out:
    remaining = int((st.session_state['lockout_until'] - now).total_seconds())
    st.sidebar.error(f"🔒 बहुत ज़्यादा गलत प्रयास। कृपया {remaining} सेकंड बाद कोशिश करें। (Too many failed attempts. Try again in {remaining}s.)")
elif st.sidebar.button("🚀 Login"):
    login_success = False
    requires_totp = False
    if login_mode == "🏢 सेंटर लॉगिन (Center Login)":
        if _check_and_migrate(selected_center, input_password) or _check_and_migrate("HR_Admin", input_password):
            if selected_center == "HR_Admin":
                admin_totp_secret = get_totp_secret("HR_Admin")
                if admin_totp_secret:
                    requires_totp = True
                    st.session_state['pending_totp_secret'] = admin_totp_secret
                else:
                    login_success = True
            else:
                login_success = True
            st.session_state['login_mode'] = 'center'
            st.session_state['staff_user'] = None
    else:
        matched_user = _check_staff_login(staff_username, staff_password)
        if matched_user:
            login_success = True
            st.session_state['login_mode'] = 'staff'
            st.session_state['staff_user'] = matched_user

    if requires_totp:
        st.session_state['awaiting_totp'] = True
        st.session_state['logged_in'] = False
    elif login_success:
        st.session_state['logged_in'] = True
        st.session_state['awaiting_totp'] = False
        st.session_state['login_attempts'] = 0
        st.session_state['lockout_until'] = None
    else:
        st.session_state['logged_in'] = False
        st.session_state['login_attempts'] += 1
        if st.session_state['login_attempts'] >= MAX_LOGIN_ATTEMPTS:
            st.session_state['lockout_until'] = now + timedelta(minutes=LOCKOUT_MINUTES)
            st.sidebar.error(f"🔒 {MAX_LOGIN_ATTEMPTS} गलत प्रयासों के बाद लॉगिन {LOCKOUT_MINUTES} मिनट के लिए लॉक हो गया। (Login locked for {LOCKOUT_MINUTES} min after {MAX_LOGIN_ATTEMPTS} failed attempts.)")
        else:
            left = MAX_LOGIN_ATTEMPTS - st.session_state['login_attempts']
            st.sidebar.error(f"❌ गलत यूज़रनेम/पासवर्ड! ({left} प्रयास शेष) (Wrong username/password! {left} attempts left)")

if st.session_state.get('awaiting_totp') and not st.session_state.get('logged_in'):
    otp_code = st.sidebar.text_input("🔐 Authenticator ऐप का 6-अंकों कोड डालें (Enter 6-digit code):", max_chars=6, key="totp_code_input")
    if st.sidebar.button("✅ OTP वेरिफाई करें (Verify OTP)"):
        totp_obj = pyotp.TOTP(st.session_state.get('pending_totp_secret', ''))
        if otp_code and totp_obj.verify(otp_code, valid_window=1):
            st.session_state['logged_in'] = True
            st.session_state['awaiting_totp'] = False
            st.session_state['login_attempts'] = 0
            st.session_state['lockout_until'] = None
            st.rerun()
        else:
            st.sidebar.error("❌ गलत OTP कोड! (Invalid OTP Code!)")

if st.session_state.get('logged_in') and st.session_state.get('login_mode') == 'staff' and st.session_state.get('staff_user'):
    selected_center = st.session_state['staff_user']['Center']

today_date = datetime.today().strftime('%Y-%m-%d')

if st.session_state['logged_in']:
    if st.session_state.get('login_mode') == 'staff' and st.session_state.get('staff_user'):
        st.sidebar.success(f"🔓 स्वागत है (Welcome), {st.session_state['staff_user']['Full Name']} ({st.session_state['staff_user']['Role']})")
    else:
        st.sidebar.success("🔓 एक्सेस स्वीकृत (Access Granted)")
    if st.sidebar.button("🚪 Logout"):
        st.session_state['logged_in'] = False
        st.session_state['staff_user'] = None
        st.session_state['awaiting_totp'] = False
        st.session_state['pending_totp_secret'] = None
        st.rerun()

    if selected_center == "HR_Admin":
        st.sidebar.markdown("---")
        admin_view = st.sidebar.selectbox("🏢 सेंटर व्यू बदलें (Master Filter):", ["सभी सेंटर्स (All Centers)"] + actual_centers)
    else:
        admin_view = selected_center

    menu_options = ["🏠 डैशबोर्ड (Dashboard)", "👥 स्टाफ मैनेजमेंट (HR & Staff)", "📅 दैनिक हाजिरी (Attendance)", "🧒 मरीज रजिस्ट्रेशन (Patient Entry)", "🩺 परामर्श (Consultation)", "📊 रिपोर्ट सेंटर (Advanced Reports)", "💰 फाइनेंस (Finance)", "🎫 अपॉइंटमेंट (Appointments)"]
    if selected_center == "HR_Admin": menu_options.append("🔑 पासवर्ड व क्लिनिक मैनेजर (Password & Clinic Manager)")

    if st.session_state.get('login_mode') == 'staff' and st.session_state.get('staff_user'):
        allowed_menus = ROLE_MENU_ACCESS.get(st.session_state['staff_user']['Role'])
        if allowed_menus:
            menu_options = [m for m in menu_options if m in allowed_menus]

    st.sidebar.markdown("<p style='margin-bottom:2px; font-weight:600; opacity:0.85;'>🧭 मेनू नेविगेशन (Menu Navigation)</p>", unsafe_allow_html=True)
    st.sidebar.markdown('<div class="menu-nav-anchor"></div>', unsafe_allow_html=True)
    menu = st.sidebar.radio("मेनू नेविगेशन", menu_options, label_visibility="collapsed")
    
    if menu == "🏠 डैशबोर्ड (Dashboard)":
        st.markdown(f"<h2>📊 {admin_view} ओवरव्यू (Overview)</h2>", unsafe_allow_html=True)
        sync_throttle_key = f"last_fee_sync_{admin_view}"
        last_sync_time = st.session_state.get(sync_throttle_key)
        if not last_sync_time or (datetime.now() - last_sync_time).total_seconds() > 30:
            if selected_center == "HR_Admin":
                for c in actual_centers: sync_total_fees_batch(sh, today_date, c)
            else:
                sync_total_fees_batch(sh, today_date, selected_center)
            st.session_state[sync_throttle_key] = datetime.now()

        staff_df = load_cloud_data_fast("Staff")
        patients_df = load_cloud_data_fast("Patients")
        
        if admin_view == "सभी सेंटर्स (All Centers)":
            center_staff = staff_df if not staff_df.empty else pd.DataFrame()
            filtered_patients = patients_df[patients_df['Date'] == today_date] if not patients_df.empty else pd.DataFrame()
        else:
            center_staff = staff_df[staff_df['Center'] == admin_view] if not staff_df.empty else pd.DataFrame()
            filtered_patients = patients_df[(patients_df['Center'] == admin_view) & (patients_df['Date'] == today_date)] if not patients_df.empty else pd.DataFrame()

        consultations_df = load_cloud_data_fast("Consultations")
        if admin_view == "सभी सेंटर्स (All Centers)":
            center_consultations_all = consultations_df if not consultations_df.empty else pd.DataFrame()
        else:
            center_consultations_all = consultations_df[consultations_df['Center'] == admin_view] if not consultations_df.empty else pd.DataFrame()

        def _consultation_fees_for(df_subset):
            if df_subset is None or df_subset.empty or 'Total Fees' not in df_subset.columns:
                return 0
            return df_subset['Total Fees'].sum()

        today_consultations = center_consultations_all[center_consultations_all['Date'] == today_date] if not center_consultations_all.empty else pd.DataFrame()
        total_fees_collected = (filtered_patients['Fees'].sum() if not filtered_patients.empty and 'Fees' in filtered_patients.columns else 0) + _consultation_fees_for(today_consultations)

        col1, col2, col3 = st.columns(3)
        with col1: st.markdown(f'<div class="metric-card"><div class="metric-title">👥 कुल एक्टिव स्टाफ (Total Active Staff)</div><div class="metric-value">{len(center_staff)}</div></div>', unsafe_allow_html=True)
        with col2: st.markdown(f'<div class="metric-card" style="border-top-color:#ff9f43;"><div class="metric-title">🧒 आज के पंजीकृत बच्चे (Today\'s Patients)</div><div class="metric-value">{len(filtered_patients)}</div></div>', unsafe_allow_html=True)
        with col3: st.markdown(f'<div class="metric-card" style="border-top-color:#28c76f;"><div class="metric-title">💵 कुल फीस कलेक्शन (Total Collection)</div><div class="metric-value" style="color:#28c76f;">₹ {total_fees_collected}/-</div></div>', unsafe_allow_html=True)

        # --- 📊 अतिरिक्त KPI कैलकुलेशन ---
        attendance_df = load_cloud_data_fast("Attendance")
        this_month_str = today_date[:7]

        if admin_view == "सभी सेंटर्स (All Centers)":
            center_patients_all = patients_df if not patients_df.empty else pd.DataFrame()
        else:
            center_patients_all = patients_df[patients_df['Center'] == admin_view] if not patients_df.empty else pd.DataFrame()

        month_patients_df = center_patients_all[center_patients_all['Date'].astype(str).str.startswith(this_month_str)] if not center_patients_all.empty else pd.DataFrame()
        month_consultations_df = center_consultations_all[center_consultations_all['Date'].astype(str).str.startswith(this_month_str)] if not center_consultations_all.empty else pd.DataFrame()
        month_collection = (month_patients_df['Fees'].sum() if not month_patients_df.empty and 'Fees' in month_patients_df.columns else 0) + _consultation_fees_for(month_consultations_df)

        att_today = pd.DataFrame()
        if not attendance_df.empty and 'Date' in attendance_df.columns:
            att_today = attendance_df[attendance_df['Date'].astype(str).str.strip() == str(today_date)]
            if admin_view != "सभी सेंटर्स (All Centers)" and 'Center' in att_today.columns:
                att_today = att_today[att_today['Center'] == admin_view]

        present_count = len(att_today[att_today['Status'] == 'Present']) if not att_today.empty and 'Status' in att_today.columns else 0
        absent_count = len(att_today[att_today['Status'] == 'Absent']) if not att_today.empty and 'Status' in att_today.columns else 0
        leave_count = len(att_today[att_today['Status'] == 'Leave']) if not att_today.empty and 'Status' in att_today.columns else 0
        total_marked = present_count + absent_count + leave_count
        attendance_pct = round((present_count / total_marked) * 100, 1) if total_marked > 0 else 0
        avg_fee_today = round(total_fees_collected / len(filtered_patients), 0) if not filtered_patients.empty else 0

        st.write("")
        col4, col5, col6, col7 = st.columns(4)
        with col4: st.markdown(f'<div class="metric-card" style="border-top-color:#5f27cd;"><div class="metric-title">📆 इस महीने कलेक्शन (This Month Collection)</div><div class="metric-value" style="color:#5f27cd;">₹ {int(month_collection)}/-</div></div>', unsafe_allow_html=True)
        with col5: st.markdown(f'<div class="metric-card" style="border-top-color:#00cec9;"><div class="metric-title">🧒 इस महीने मरीज (This Month Patients)</div><div class="metric-value">{len(month_patients_df)}</div></div>', unsafe_allow_html=True)
        with col6: st.markdown(f'<div class="metric-card" style="border-top-color:#0984e3;"><div class="metric-title">✅ आज हाजिरी % (Today Attendance %)</div><div class="metric-value">{attendance_pct}%</div></div>', unsafe_allow_html=True)
        with col7: st.markdown(f'<div class="metric-card" style="border-top-color:#e17055;"><div class="metric-title">💰 औसत फीस/मरीज (Avg Fee/Patient - आज)</div><div class="metric-value">₹ {int(avg_fee_today)}</div></div>', unsafe_allow_html=True)

        st.markdown(f"<p style='margin-top:14px;'>👥 <b>आज की हाजिरी (Today's Attendance):</b> ✅ उपस्थित {present_count} (Present) &nbsp;|&nbsp; ❌ अनुपस्थित {absent_count} (Absent) &nbsp;|&nbsp; 🌴 अवकाश {leave_count} (Leave)</p>", unsafe_allow_html=True)

        # --- 🔔 अलर्ट: कम कलेक्शन / कम हाजिरी ---
        alert_last_7_dates = [(datetime.today() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 8)]
        avg_recent_collection = 0
        recent_patient_sum = 0
        if not center_patients_all.empty:
            recent_alert_df = center_patients_all[center_patients_all['Date'].isin(alert_last_7_dates)]
            if not recent_alert_df.empty:
                recent_patient_sum = recent_alert_df['Fees'].sum()
        recent_consult_alert_df = center_consultations_all[center_consultations_all['Date'].isin(alert_last_7_dates)] if not center_consultations_all.empty else pd.DataFrame()
        avg_recent_collection = (recent_patient_sum + _consultation_fees_for(recent_consult_alert_df)) / 7
        if datetime.now().hour >= 14 and avg_recent_collection > 0 and total_fees_collected < avg_recent_collection * 0.5:
            st.warning(f"⚠️ आज का कलेक्शन (₹{int(total_fees_collected)}) पिछले 7 दिनों की औसत (₹{int(avg_recent_collection)}/दिन) से काफी कम है — ध्यान दें। (Today's collection is much lower than the 7-day average — please check.)")
        if total_marked > 0 and attendance_pct < 70:
            st.warning(f"⚠️ आज स्टाफ हाजिरी सिर्फ {attendance_pct}% है — सामान्य से कम, कृपया जांच करें। (Today's staff attendance is only {attendance_pct}% — lower than normal.)")

        if admin_view == "सभी सेंटर्स (All Centers)" and actual_centers:
            st.write("---")
            st.markdown("### 🏥 सेंटर-वाइज तुलना (Center-wise Comparison)")
            with st.container(border=True):
                comparison_rows = []
                for c in actual_centers:
                    c_staff_count = len(staff_df[staff_df['Center'] == c]) if not staff_df.empty else 0
                    c_today_patients = patients_df[(patients_df['Center'] == c) & (patients_df['Date'] == today_date)] if not patients_df.empty else pd.DataFrame()
                    c_today_fees = c_today_patients['Fees'].sum() if not c_today_patients.empty and 'Fees' in c_today_patients.columns else 0
                    c_today_consultations = consultations_df[(consultations_df['Center'] == c) & (consultations_df['Date'] == today_date)] if not consultations_df.empty else pd.DataFrame()
                    c_today_fees += _consultation_fees_for(c_today_consultations)
                    comparison_rows.append({"सेंटर (Center)": c, "स्टाफ (Staff)": c_staff_count, "आज के मरीज (Patients Today)": len(c_today_patients), "आज की फीस (Fees Today) (₹)": int(c_today_fees)})
                st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)

        st.write("---")
        st.markdown(f"### 📋 आज के पंजीकृत मरीज (Today's Registered Patients) ({today_date})")
        if not filtered_patients.empty:
            cols_to_show = [c for c in ['Child Name', 'Parent Name', 'Age', 'Condition', 'Mobile', 'Fees', 'Total Fees', 'Center', 'Patient Type'] if c in filtered_patients.columns]
            st.dataframe(filtered_patients[cols_to_show].reset_index(drop=True), use_container_width=True)
        else:
            st.info("💡 कोई मरीज दर्ज नहीं है। (No patients registered today.)")

        st.write("---")
        st.markdown("### 📈 पिछले 7 दिनों का ट्रेंड (Last 7 Days Trend)")
        last_7_dates = [(datetime.today() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
        if not center_patients_all.empty and 'Date' in center_patients_all.columns:
            trend_source = center_patients_all[center_patients_all['Date'].isin(last_7_dates)]
            trend_fees = trend_source.groupby('Date')['Fees'].sum().reindex(last_7_dates, fill_value=0) if 'Fees' in trend_source.columns else pd.Series([0] * 7, index=last_7_dates)
            trend_counts = trend_source.groupby('Date').size().reindex(last_7_dates, fill_value=0)
        else:
            trend_fees = pd.Series([0] * 7, index=last_7_dates)
            trend_counts = pd.Series([0] * 7, index=last_7_dates)

        if not center_consultations_all.empty and 'Date' in center_consultations_all.columns and 'Total Fees' in center_consultations_all.columns:
            trend_consult_source = center_consultations_all[center_consultations_all['Date'].isin(last_7_dates)]
            trend_consult_fees = trend_consult_source.groupby('Date')['Total Fees'].sum().reindex(last_7_dates, fill_value=0)
            trend_fees = trend_fees.add(trend_consult_fees, fill_value=0)

        with st.container(border=True):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.markdown("**💵 दैनिक फीस कलेक्शन (Daily Fee Collection)**")
                st.line_chart(trend_fees, color="#008080")
            with col_t2:
                st.markdown("**🧒 दैनिक मरीज पंजीकरण (Daily Patient Registrations)**")
                st.bar_chart(trend_counts, color="#ff9f43")

        if not center_patients_all.empty and 'Condition' in center_patients_all.columns:
            cond_counts = center_patients_all['Condition'].value_counts().head(6)
            if not cond_counts.empty:
                st.write("---")
                st.markdown("### 🩺 समस्या-वार मरीज वितरण (Patient Distribution by Condition / Top Conditions)")
                with st.container(border=True):
                    st.bar_chart(cond_counts, color="#7b2cbf")

    elif menu == "👥 स्टाफ मैनेजमेंट (HR & Staff)":
        st.markdown("<h2>👥 स्टाफ मैनेजमेंट पोर्टल (Staff Management Portal)</h2>", unsafe_allow_html=True)
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["➕ नया कर्मचारी जोड़ें (Add Staff)", "📋 वर्तमान स्टाफ सूची (Staff List)", "✏️ स्टाफ एडिट करें (Edit Staff)", "🧾 सैलरी स्लिप (Salary Slip)", "🌴 लीव मैनेजमेंट (Leave Management)"])
        staff_df = load_cloud_data_fast("Staff")
        with tab1:
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                s_name = st.text_input("कर्मचारी का पूरा नाम (Full Name):")
                s_role = st.selectbox("पद (Role):", ["Homeopathic Doctor", "Pharmacist (Medicine Maker)", "Receptionist", "Maid / Housekeeping"])
                if selected_center == "HR_Admin":
                    s_target_center = st.selectbox("🎯 किस सेंटर के लिए जोड़ना है? (Which Center?):", actual_centers)
                else:
                    s_target_center = selected_center
            with col_s2:
                s_mobile = st.text_input("📞 मोबाइल नंबर (Mobile Number):", max_chars=10)
                s_salary = st.number_input("💵 मासिक सैलरी (Monthly Salary) (₹):", min_value=0, value=0, step=1000)
            if st.button("🚀 क्लाउड पर सेव करें (Save)"):
                if not s_name or not s_mobile:
                    st.warning("⚠️ कृपया नाम और मोबाइल नंबर दोनों भरें। (Please fill both name and mobile number.)")
                elif not is_valid_mobile(s_mobile):
                    st.warning("⚠️ मोबाइल नंबर 10 अंकों का होना चाहिए। (Mobile number must be 10 digits.)")
                else:
                    if not staff_df.empty and 'ID' in staff_df.columns:
                        existing_s_ids = pd.to_numeric(staff_df['ID'], errors='coerce').dropna()
                        next_s_id = int(existing_s_ids.max()) + 1 if not existing_s_ids.empty else 1
                    else:
                        next_s_id = 1
                    sh.worksheet("Staff").append_row([next_s_id, s_name, s_role, str(s_mobile), s_target_center, int(s_salary)])
                    log_audit(current_actor(), "Add Staff", f"{s_name} ({s_role}) added to {s_target_center}, ID {next_s_id}")
                    st.cache_data.clear()
                    st.success(f"🎉 {s_name} को सफलतापूर्वक {s_target_center} सेंटर में जोड़ दिया गया है! (Added successfully!)")
                    st.rerun()
        with tab2:
            if admin_view == "सभी सेंटर्स (All Centers)":
                view_staff_df = staff_df if not staff_df.empty else pd.DataFrame()
            else:
                view_staff_df = staff_df[staff_df['Center'] == admin_view] if not staff_df.empty else pd.DataFrame()

            staff_search = st.text_input("🔍 नाम या मोबाइल नंबर से खोजें (Search by Name/Mobile):", key="staff_search")
            if staff_search and not view_staff_df.empty:
                mask = view_staff_df['Name'].str.contains(staff_search, case=False, na=False) | view_staff_df['Mobile'].str.contains(staff_search, case=False, na=False)
                view_staff_df = view_staff_df[mask]

            if not view_staff_df.empty:
                st.dataframe(view_staff_df[['ID', 'Name', 'Role', 'Mobile', 'Salary', 'Center']].reset_index(drop=True), use_container_width=True)
            else:
                st.info("इस फ़िल्टर पर अभी कोई स्टाफ डेटा नहीं है। (No staff data for this filter.)")

            if not view_staff_df.empty:
                st.markdown("---")
                st.subheader("🗑️ स्टाफ हटाएं (Delete Staff)")
                del_staff_options = {f"{r['Name']} ({r['Role']}, {r['Center']}) - ID {r['ID']}": r['ID'] for _, r in view_staff_df.iterrows()}
                del_staff_label = st.selectbox("हटाने के लिए स्टाफ चुनें (Select staff to delete):", list(del_staff_options.keys()), key="del_staff_select")
                if st.button("❌ स्टाफ डिलीट करें (Delete Staff)"):
                    s_sheet = sh.worksheet("Staff")
                    all_s_rows = s_sheet.get_all_values()
                    target_s_id = str(del_staff_options[del_staff_label])
                    row_to_delete = next((idx + 2 for idx, r in enumerate(all_s_rows[1:]) if r and str(r[0]).strip() == target_s_id), None)
                    if row_to_delete:
                        s_sheet.delete_rows(row_to_delete)
                        log_audit(current_actor(), "Delete Staff", f"{del_staff_label}")
                        st.cache_data.clear()
                        st.success("🗑️ स्टाफ रिकॉर्ड डिलीट हो गया है! (Staff record deleted!)")
                        st.rerun()

        with tab3:
            if staff_df.empty:
                st.info("कोई स्टाफ डेटा उपलब्ध नहीं है। (No staff data available.)")
            else:
                if admin_view == "सभी सेंटर्स (All Centers)":
                    edit_staff_pool = staff_df
                else:
                    edit_staff_pool = staff_df[staff_df['Center'] == admin_view]

                staff_edit_search = st.text_input("🔍 नाम या मोबाइल नंबर से खोजें (Search by Name/Mobile):", key="staff_edit_search")
                if staff_edit_search and not edit_staff_pool.empty:
                    mask = edit_staff_pool['Name'].str.contains(staff_edit_search, case=False, na=False) | edit_staff_pool['Mobile'].str.contains(staff_edit_search, case=False, na=False)
                    edit_staff_pool = edit_staff_pool[mask]

                if edit_staff_pool.empty:
                    st.info("💡 खोज से मेल खाता कोई स्टाफ नहीं मिला। (No matching staff found.)")
                else:
                    staff_edit_options = {f"{r['Name']} ({r['Role']}, {r['Center']}) - ID {r['ID']}": r['ID'] for _, r in edit_staff_pool.iterrows()}
                    selected_staff_label = st.selectbox("एडिट के लिए स्टाफ चुनें (Select staff to edit):", list(staff_edit_options.keys()), key="staff_edit_select")
                    s_data = staff_df[staff_df['ID'] == staff_edit_options[selected_staff_label]].iloc[0]
                    real_s_row_idx = staff_df[staff_df['ID'] == staff_edit_options[selected_staff_label]].index[0] + 2

                    role_options = ["Homeopathic Doctor", "Pharmacist (Medicine Maker)", "Receptionist", "Maid / Housekeeping"]
                    col_se1, col_se2 = st.columns(2)
                    with col_se1:
                        edit_s_name = st.text_input("नाम बदलें (Change Name):", value=str(s_data['Name']))
                        edit_s_role = st.selectbox("पद बदलें (Change Role):", role_options, index=role_options.index(s_data['Role']) if s_data['Role'] in role_options else 0)
                        if selected_center == "HR_Admin":
                            edit_s_center = st.selectbox("सेंटर बदलें (Change Center):", actual_centers, index=actual_centers.index(s_data['Center']) if s_data['Center'] in actual_centers else 0)
                        else:
                            edit_s_center = str(s_data['Center'])
                    with col_se2:
                        edit_s_mobile = st.text_input("मोबाइल नंबर बदलें (Change Mobile):", value=str(s_data['Mobile']), max_chars=10)
                        current_salary = int(s_data['Salary']) if str(s_data['Salary']).strip().isdigit() else 0
                        edit_s_salary = st.number_input("मासिक सैलरी बदलें (Change Salary) (₹):", min_value=0, value=current_salary, step=1000)

                    if st.button("💾 स्टाफ डेटा अपडेट करें (Update Staff)"):
                        if not is_valid_mobile(edit_s_mobile):
                            st.warning("⚠️ मोबाइल नंबर 10 अंकों का होना चाहिए। (Mobile number must be 10 digits.)")
                        else:
                            s_sheet = sh.worksheet("Staff")
                            s_sheet.update(range_name=f"A{real_s_row_idx}:F{real_s_row_idx}", values=[[int(staff_edit_options[selected_staff_label]), edit_s_name, edit_s_role, str(edit_s_mobile), edit_s_center, int(edit_s_salary)]])
                            log_audit(current_actor(), "Edit Staff", f"ID {staff_edit_options[selected_staff_label]} ({edit_s_name}) updated")
                            st.cache_data.clear()
                            st.success("📝 स्टाफ रिकॉर्ड सफलतापूर्वक अपडेट हो गया! (Staff record updated!)")
                            st.rerun()

        with tab4:
            st.markdown("### 🧾 स्टाफ मासिक सैलरी स्लिप जनरेट करें (Generate Monthly Salary Slip)")
            if staff_df.empty:
                st.info("कोई स्टाफ डेटा उपलब्ध नहीं है। (No staff data available.)")
            else:
                if admin_view == "सभी सेंटर्स (All Centers)":
                    slip_staff_pool = staff_df
                else:
                    slip_staff_pool = staff_df[staff_df['Center'] == admin_view]

                if slip_staff_pool.empty:
                    st.info("इस फ़िल्टर पर कोई स्टाफ नहीं है। (No staff for this filter.)")
                else:
                    slip_options = {f"{r['Name']} ({r['Role']}, {r['Center']}) - ID {r['ID']}": r['ID'] for _, r in slip_staff_pool.iterrows()}
                    slip_selected_label = st.selectbox("स्टाफ चुनें (Select Staff):", list(slip_options.keys()), key="slip_staff_select")
                    slip_staff_row = staff_df[staff_df['ID'] == slip_options[slip_selected_label]].iloc[0]

                    col_sl1, col_sl2 = st.columns(2)
                    with col_sl1:
                        slip_year = st.selectbox("साल चुनें (Select Year):", [str(y) for y in range(datetime.today().year - 2, datetime.today().year + 2)], index=2, key="slip_year")
                    with col_sl2:
                        slip_months_list = [("January", 1), ("February", 2), ("March", 3), ("April", 4), ("May", 5), ("June", 6), ("July", 7), ("August", 8), ("September", 9), ("October", 10), ("November", 11), ("December", 12)]
                        slip_month_label = st.selectbox("महीना चुनें (Select Month):", [m[0] for m in slip_months_list], index=datetime.today().month - 1, key="slip_month")
                        slip_month_num = next(m[1] for m in slip_months_list if m[0] == slip_month_label)

                    if st.button("🧾 सैलरी स्लिप जनरेट करें (Generate Salary Slip)"):
                        att_for_slip = load_cloud_data_fast("Attendance")
                        target_month_str = f"{slip_year}-{slip_month_num:02d}"
                        s_id_str = str(slip_staff_row['ID']).strip()
                        if not att_for_slip.empty and 'Staff_ID' in att_for_slip.columns:
                            match_att = att_for_slip[(att_for_slip['Staff_ID'].astype(str).str.strip() == s_id_str) & (att_for_slip['Date'].astype(str).str.startswith(target_month_str))]
                            present_days = len(match_att[match_att['Status'].str.lower() == 'present'])
                            absent_days = len(match_att[match_att['Status'].str.lower() == 'absent'])
                            leave_days = len(match_att[match_att['Status'].str.lower() == 'leave'])
                        else:
                            present_days = absent_days = leave_days = 0
                        total_days_in_month = calendar.monthrange(int(slip_year), slip_month_num)[1]
                        monthly_salary = int(slip_staff_row['Salary']) if str(slip_staff_row['Salary']).strip().isdigit() else 0
                        slip_pdf = generate_salary_slip_pdf(
                            slip_staff_row['Name'], slip_staff_row['Role'], slip_staff_row['Center'],
                            f"{slip_month_label} {slip_year}", monthly_salary, present_days, absent_days, leave_days, total_days_in_month
                        )
                        st.success(f"✅ {slip_month_label} {slip_year} की सैलरी स्लिप तैयार है (Salary slip ready) — उपस्थित (Present): {present_days}, अनुपस्थित (Absent): {absent_days}, अवकाश (Leave): {leave_days}")
                        st.download_button(
                            "📥 सैलरी स्लिप PDF डाउनलोड करें (Download PDF)",
                            data=slip_pdf,
                            file_name=f"SalarySlip_{slip_staff_row['Name']}_{target_month_str}.pdf",
                            mime="application/pdf",
                        )

        with tab5:
            st.markdown("### 🌴 लीव एप्लीकेशन व अप्रूवल (Leave Application & Approval)")
            leave_tab1, leave_tab2 = st.tabs(["📝 नई लीव एप्लीकेशन (New Leave Request)", "✅ अप्रूव / रिजेक्ट करें (Approve/Reject)"])

            with leave_tab1:
                if staff_df.empty:
                    st.info("कोई स्टाफ डेटा उपलब्ध नहीं है। (No staff data available.)")
                else:
                    if admin_view == "सभी सेंटर्स (All Centers)":
                        leave_staff_pool = staff_df
                    else:
                        leave_staff_pool = staff_df[staff_df['Center'] == admin_view]

                    if leave_staff_pool.empty:
                        st.info("इस फ़िल्टर पर कोई स्टाफ नहीं है। (No staff for this filter.)")
                    else:
                        leave_options = {f"{r['Name']} ({r['Role']}, {r['Center']}) - ID {r['ID']}": r['ID'] for _, r in leave_staff_pool.iterrows()}
                        leave_selected_label = st.selectbox("स्टाफ चुनें (Select Staff):", list(leave_options.keys()), key="leave_apply_staff")
                        leave_staff_row = staff_df[staff_df['ID'] == leave_options[leave_selected_label]].iloc[0]

                        col_lv1, col_lv2 = st.columns(2)
                        with col_lv1:
                            leave_from = st.date_input("लीव शुरू तारीख (Start Date):", datetime.today(), key="leave_from")
                        with col_lv2:
                            leave_to = st.date_input("लीव खत्म तारीख (End Date):", datetime.today(), key="leave_to")
                        leave_reason = st.text_input("कारण (Reason):", key="leave_reason")

                        if st.button("📤 लीव एप्लीकेशन सबमिट करें (Submit Leave Request)"):
                            if leave_to < leave_from:
                                st.warning("⚠️ End date, start date से पहले नहीं हो सकती। (End date cannot be before start date.)")
                            else:
                                try:
                                    leave_sheet = sh.worksheet("Leave_Requests")
                                except Exception:
                                    leave_sheet = sh.add_worksheet(title="Leave_Requests", rows="1000", cols="9")
                                    leave_sheet.update(range_name="A1:I1", values=[["ID", "Staff ID", "Staff Name", "Center", "From Date", "To Date", "Reason", "Status", "Applied On"]])
                                all_leave_rows = leave_sheet.get_all_values()
                                existing_leave_ids = [int(r[0]) for r in all_leave_rows[1:] if r and str(r[0]).strip().isdigit()]
                                next_leave_id = max(existing_leave_ids) + 1 if existing_leave_ids else 1
                                leave_sheet.append_row([
                                    next_leave_id, int(leave_staff_row['ID']), leave_staff_row['Name'], leave_staff_row['Center'],
                                    leave_from.strftime('%Y-%m-%d'), leave_to.strftime('%Y-%m-%d'), leave_reason, "Pending", today_date
                                ])
                                log_audit(current_actor(), "Apply Leave", f"{leave_staff_row['Name']} ({leave_from} to {leave_to})")
                                st.cache_data.clear()
                                st.success("🎉 लीव एप्लीकेशन सबमिट हो गई है, अप्रूवल का इंतज़ार है। (Leave request submitted, awaiting approval.)")
                                st.rerun()

            with leave_tab2:
                leave_requests_df = load_cloud_data_fast("Leave_Requests")
                if admin_view == "सभी सेंटर्स (All Centers)":
                    view_leave_df = leave_requests_df
                else:
                    view_leave_df = leave_requests_df[leave_requests_df['Center'] == admin_view] if not leave_requests_df.empty and 'Center' in leave_requests_df.columns else pd.DataFrame()

                if view_leave_df.empty:
                    st.info("कोई लीव एप्लीकेशन उपलब्ध नहीं है। (No leave requests available.)")
                else:
                    pending_df = view_leave_df[view_leave_df['Status'] == 'Pending']
                    st.markdown(f"**पेंडिंग एप्लीकेशन (Pending Requests): {len(pending_df)}**")
                    st.dataframe(view_leave_df[['ID', 'Staff Name', 'Center', 'From Date', 'To Date', 'Reason', 'Status']].sort_values('ID', ascending=False).reset_index(drop=True), use_container_width=True)

                    if not pending_df.empty:
                        st.markdown("---")
                        st.subheader("✅ पेंडिंग एप्लीकेशन पर एक्शन लें (Act on Pending Requests)")
                        leave_action_options = {f"ID {r['ID']} - {r['Staff Name']} ({r['From Date']} to {r['To Date']})": r['ID'] for _, r in pending_df.iterrows()}
                        leave_action_label = st.selectbox("एप्लीकेशन चुनें (Select Request):", list(leave_action_options.keys()), key="leave_action_select")
                        leave_action_row = pending_df[pending_df['ID'] == leave_action_options[leave_action_label]].iloc[0]

                        col_la1, col_la2 = st.columns(2)
                        with col_la1:
                            if st.button("✅ अप्रूव करें (Approve)"):
                                leave_sheet = sh.worksheet("Leave_Requests")
                                all_leave_rows = leave_sheet.get_all_values()
                                target_leave_id = str(leave_action_options[leave_action_label])
                                row_to_update = next((idx + 2 for idx, r in enumerate(all_leave_rows[1:]) if r and str(r[0]).strip() == target_leave_id), None)
                                if row_to_update:
                                    leave_sheet.update_cell(row_to_update, 8, "Approved")
                                    try:
                                        att_sheet = sh.worksheet("Attendance")
                                        att_rows = att_sheet.get_all_values()
                                        existing_att_ids = [int(r[0]) for r in att_rows[1:] if r and str(r[0]).strip().isdigit()]
                                        att_id_counter = max(existing_att_ids) + 1 if existing_att_ids else 1
                                        from_dt = datetime.strptime(str(leave_action_row['From Date']), '%Y-%m-%d')
                                        to_dt = datetime.strptime(str(leave_action_row['To Date']), '%Y-%m-%d')
                                        num_days = (to_dt - from_dt).days + 1
                                        for i in range(num_days):
                                            d_str = (from_dt + timedelta(days=i)).strftime('%Y-%m-%d')
                                            existing_row_idx = None
                                            for r_idx, row in enumerate(att_rows[1:], start=2):
                                                if len(row) >= 4 and str(row[1]).strip() == str(int(leave_action_row['Staff ID'])) and str(row[3]).strip() == d_str:
                                                    existing_row_idx = r_idx
                                                    break
                                            if existing_row_idx:
                                                att_sheet.update_cell(existing_row_idx, 5, "Leave")
                                            else:
                                                att_sheet.append_row([att_id_counter, int(leave_action_row['Staff ID']), leave_action_row['Staff Name'], d_str, "Leave", leave_action_row['Center']])
                                                att_rows.append([att_id_counter, int(leave_action_row['Staff ID']), leave_action_row['Staff Name'], d_str, "Leave", leave_action_row['Center']])
                                                att_id_counter += 1
                                    except Exception as e:
                                        logger.warning(f"Attendance auto-mark on leave approval failed: {e}")
                                    log_audit(current_actor(), "Approve Leave", leave_action_label)
                                    st.cache_data.clear()
                                    st.success("✅ लीव अप्रूव हो गई और अटेंडेंस अपडेट हो गई! (Leave approved and attendance updated!)")
                                    st.rerun()
                        with col_la2:
                            if st.button("❌ रिजेक्ट करें (Reject)"):
                                leave_sheet = sh.worksheet("Leave_Requests")
                                all_leave_rows = leave_sheet.get_all_values()
                                target_leave_id = str(leave_action_options[leave_action_label])
                                row_to_update = next((idx + 2 for idx, r in enumerate(all_leave_rows[1:]) if r and str(r[0]).strip() == target_leave_id), None)
                                if row_to_update:
                                    leave_sheet.update_cell(row_to_update, 8, "Rejected")
                                    log_audit(current_actor(), "Reject Leave", leave_action_label)
                                    st.cache_data.clear()
                                    st.success("❌ लीव रिजेक्ट कर दी गई है। (Leave request rejected.)")
                                    st.rerun()

    elif menu == "📅 दैनिक हाजिरी (Attendance)":
        st.markdown("<h2>📅 डिजिटल हाजिरी रजिस्टर (Digital Attendance Register)</h2>", unsafe_allow_html=True)
        staff_df = load_cloud_data_fast("Staff")
        if admin_view == "सभी सेंटर्स (All Centers)":
            att_center = st.selectbox("🎯 हाजिरी रजिस्टर ओपन करने के लिए सेंटर चुनें (Select Center):", actual_centers)
        else:
            att_center = admin_view
        center_staff = staff_df[staff_df['Center'] == att_center] if not staff_df.empty else pd.DataFrame()
        if center_staff.empty:
            st.warning(f"⚠️ {att_center} सेंटर पर कोई स्टाफ उपलब्ध नहीं है। (No staff available at this center.)")
        else:
            att_today_df = load_cloud_data_fast("Attendance")
            existing_status = {}
            if not att_today_df.empty and 'Staff_ID' in att_today_df.columns and 'Date' in att_today_df.columns:
                today_att = att_today_df[att_today_df['Date'].astype(str).str.strip() == str(today_date)]
                for _, r in today_att.iterrows():
                    existing_status[str(r['Staff_ID']).strip()] = r['Status']

            status_options = ["Present", "Absent", "Leave"]
            attendance_dict = {}
            for index, row in center_staff.iterrows():
                col_s, col_a = st.columns([2, 1])
                col_s.markdown(f"<p style='font-size: 15px; margin-top:5px;'>👤 <b>{row['Name']}</b> ({row['Role']})</p>", unsafe_allow_html=True)
                default_status = existing_status.get(str(row['ID']).strip(), "Present")
                default_index = status_options.index(default_status) if default_status in status_options else 0
                status = col_a.radio(f"Status for {row['Name']}", status_options, index=default_index, key=str(row['ID']), label_visibility="collapsed", horizontal=True)
                attendance_dict[row['ID']] = {"name": row['Name'], "status": status}
            if st.button("💾 अटेंडेंस LOCK और सबमिट करें (Lock & Submit Attendance)"):
                try:
                    att_sheet = sh.worksheet("Attendance")
                    all_rows = att_sheet.get_all_values()
                    existing_ids = [int(r[0]) for r in all_rows[1:] if r and str(r[0]).strip().isdigit()]
                    next_id_counter = max(existing_ids) + 1 if existing_ids else 1
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
                            next_id = next_id_counter
                            next_id_counter += 1
                            att_sheet.append_row([next_id, int(s_id), info['name'], today_date, info['status'], att_center])
                            all_rows.append([next_id, int(s_id), info['name'], today_date, info['status'], att_center])
                    log_audit(current_actor(), "Submit Attendance", f"{att_center} - {today_date} ({len(attendance_dict)} स्टाफ)")
                    st.cache_data.clear()
                    st.success(f"✅ {att_center} सेंटर का अटेंडेंस शीट डेटा lock हो गया है! (Attendance locked and saved!)")
                    st.rerun()
                except Exception as e:
                    st.error(f"एरर (Error): {e}")

    elif menu == "🧒 मरीज रजिस्ट्रेशन (Patient Entry)":
        st.markdown("<h2>🧒 मरीज डिजिटल एंट्री व संशोधन (Patient Entry & Edit)</h2>", unsafe_allow_html=True)
        tab_p1, tab_p2, tab_p3 = st.tabs(["🧒 नया मरीज रजिस्ट्रेशन (New Patient)", "✏️ मरीज विवरण एडिट करें (Edit Patient)", "📜 विज़िट हिस्ट्री (Visit History)"])
        patients_df = load_cloud_data_fast("Patients")
        staff_df_for_doctor = load_cloud_data_fast("Staff")
        if admin_view == "सभी सेंटर्स (All Centers)":
            center_patients = patients_df if not patients_df.empty else pd.DataFrame()
        else:
            center_patients = patients_df[patients_df['Center'] == admin_view] if not patients_df.empty else pd.DataFrame()
        with tab_p1:
            if st.session_state.get('last_receipt'):
                last_receipt_data = st.session_state['last_receipt']
                st.success(f"✅ {last_receipt_data['Child Name']} का रिकॉर्ड सुरक्षित है — रसीद डाउनलोड करें या WhatsApp पर भेजें: (Record saved — download receipt or send via WhatsApp:)")
                st.download_button(
                    "🧾 पिछली रसीद PDF डाउनलोड करें (Download Last Receipt PDF)",
                    data=generate_receipt_pdf(last_receipt_data),
                    file_name=f"Receipt_{last_receipt_data['ID']}.pdf",
                    mime="application/pdf",
                    key="last_receipt_download",
                )
                render_whatsapp_sender(last_receipt_data, key_prefix="new_patient")
                st.markdown("---")
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                c_name = st.text_input("🧒 विशेष बच्चे का नाम (Child's Name):")
                p_name = st.text_input("👨‍👩‍👦 माता या पिता का नाम (Parent's Name):")
                p_mobile = st.text_input("📞 अभिभावक का मोबाइल नंबर (Parent's Mobile):", max_chars=10)
                p_type = st.selectbox("📋 मरीज का प्रकार (Patient Type):", ["New Patient (नया)", "Old Patient (पुराना)"])
                if selected_center == "HR_Admin":
                    p_target_center = st.selectbox("🎯 किस सेंटर में मरीज एंट्री डालनी है? (Select Center):", actual_centers)
                else:
                    p_target_center = selected_center
            with col_p2:
                c_age = st.number_input("🎂 उम्र (Age):", min_value=1, max_value=18, value=6)
                c_cond = st.selectbox("🩺 मुख्य समस्या (Chief Complaint):", ["Autism (ऑटिज़्म)", "ADHD", "Cerebral Palsy", "Delayed Speech", "Other"])
                c_fees = st.number_input("💵 प्राप्त फीस राशि (Fees Received) (₹):", min_value=0, value=0, step=100)
                c_total_charge = st.number_input("🧾 कुल इलाज शुल्क (Total Charge) ₹:", min_value=0, value=0, step=100, help="अगर फीस पूरी नहीं मिली तो यहाँ पूरा शुल्क डालें, बाकी राशि 'बकाया फीस' रिपोर्ट में दिखेगी। (If full fee wasn't collected, enter the total charge here — the balance will show in the Due Fees report.)")
                doctor_options = staff_df_for_doctor[(staff_df_for_doctor['Center'] == p_target_center) & (staff_df_for_doctor['Role'] == 'Homeopathic Doctor')]['Name'].tolist() if not staff_df_for_doctor.empty else []
                if not doctor_options:
                    doctor_options = ["N/A (कोई डॉक्टर पंजीकृत नहीं)"]
                p_doctor = st.selectbox("🧑‍⚕️ डॉक्टर चुनें (Select Doctor):", doctor_options)
            if st.button("🎯 मरीज रिकॉर्ड सुरक्षित करें (Save Patient Record)"):
                if not c_name or not p_name or not p_mobile:
                    st.warning("⚠️ कृपया बच्चे का नाम, अभिभावक का नाम और मोबाइल नंबर भरें। (Please fill child's name, parent's name, and mobile number.)")
                elif not is_valid_mobile(p_mobile):
                    st.warning("⚠️ मोबाइल नंबर 10 अंकों का होना चाहिए। (Mobile number must be 10 digits.)")
                else:
                    p_sheet = sh.worksheet("Patients")
                    all_p_rows = p_sheet.get_all_values()
                    existing_p_ids = [int(r[0]) for r in all_p_rows[1:] if r and str(r[0]).strip().isdigit()]
                    next_p_id = max(existing_p_ids) + 1 if existing_p_ids else 1
                    effective_total_charge = c_total_charge if c_total_charge > 0 else c_fees
                    p_sheet.append_row([next_p_id, c_name, p_name, int(c_age), c_cond, str(p_mobile), p_target_center, today_date, int(c_fees), "", p_type, p_doctor, int(effective_total_charge)])
                    log_audit(current_actor(), "Add Patient", f"{c_name} s/o {p_name} added to {p_target_center}, ID {next_p_id}")
                    sync_total_fees_batch(sh, today_date, p_target_center)
                    sync_daily_collection_to_sheet(sh, today_date, p_target_center)
                    st.session_state['last_receipt'] = {
                        'ID': next_p_id, 'Date': today_date, 'Center': p_target_center,
                        'Child Name': c_name, 'Parent Name': p_name, 'Mobile': p_mobile,
                        'Age': c_age, 'Doctor': p_doctor, 'Fees': int(c_fees), 'Total Charge': int(effective_total_charge),
                    }
                    st.cache_data.clear()
                    st.success(f"🎯 रिकॉर्ड {p_target_center} सेंटर में सुरक्षित हो गया है! (Record saved!)")
                    st.rerun()
        with tab_p2:
            if center_patients.empty: st.info("कोई मरीज डेटा उपलब्ध नहीं है। (No patient data available.)")
            else:
                pat_search = st.text_input("🔍 बच्चे/अभिभावक का नाम या मोबाइल नंबर से खोजें (Search by Name/Mobile):", key="patient_search")
                search_patients = center_patients
                if pat_search:
                    mask = (
                        center_patients['Child Name'].str.contains(pat_search, case=False, na=False)
                        | center_patients['Parent Name'].str.contains(pat_search, case=False, na=False)
                        | center_patients['Mobile'].str.contains(pat_search, case=False, na=False)
                    )
                    search_patients = center_patients[mask]

                if search_patients.empty:
                    st.info("💡 खोज से मेल खाता कोई मरीज नहीं मिला। (No matching patient found.)")
                else:
                    patient_options = {f"[{row['Center']}] {row['Child Name']} s/o {row['Parent Name']} (ID: {row['ID']})": row['ID'] for _, row in search_patients.iterrows()}
                    selected_pat_label = st.selectbox("संशोधन के लिए मरीज चुनें (Select Patient to Edit):", list(patient_options.keys()))
                    pat_data = center_patients[center_patients['ID'] == patient_options[selected_pat_label]].iloc[0]
                    real_p_row_idx = patients_df[patients_df['ID'] == patient_options[selected_pat_label]].index[0] + 2
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        edit_c_name = st.text_input("बच्चे का नाम बदलें (Change Child's Name):", value=str(pat_data['Child Name']))
                        edit_p_name = st.text_input("अभिभावक का नाम बदलें (Change Parent's Name):", value=str(pat_data['Parent Name']))
                        edit_p_mobile = st.text_input("मोबाइल नंबर बदलें (Change Mobile):", value=str(pat_data['Mobile']), max_chars=10)
                        edit_p_type = st.selectbox("मरीज का प्रकार बदलें (Change Patient Type):", ["New Patient (नया)", "Old Patient (पुराना)"], index=0 if 'Patient Type' not in pat_data or pat_data['Patient Type'] == 'New Patient (नया)' else 1)
                    with col_e2:
                        edit_c_age = st.number_input("उम्र बदलें (Change Age):", min_value=1, max_value=18, value=int(pat_data['Age']))
                        cond_options = ["Autism (ऑटिज़्म)", "ADHD", "Cerebral Palsy", "Delayed Speech", "Other"]
                        current_cond = pat_data['Condition'] if 'Condition' in pat_data else None
                        edit_c_cond = st.selectbox("समस्या बदलें (Change Condition):", cond_options, index=cond_options.index(current_cond) if current_cond in cond_options else 0)
                        edit_c_fees = st.number_input("फीस राशि बदलें (Change Fees) (₹):", min_value=0, value=int(pat_data['Fees']) if 'Fees' in pat_data else 0, step=100)
                        default_total_charge = int(pat_data['Total Charge']) if 'Total Charge' in pat_data and str(pat_data['Total Charge']).strip() not in ("", "0") else int(pat_data['Fees']) if 'Fees' in pat_data else 0
                        edit_c_total_charge = st.number_input("🧾 कुल इलाज शुल्क बदलें (Change Total Charge) (₹):", min_value=0, value=default_total_charge, step=100)
                        edit_doctor_options = staff_df_for_doctor[(staff_df_for_doctor['Center'] == str(pat_data['Center'])) & (staff_df_for_doctor['Role'] == 'Homeopathic Doctor')]['Name'].tolist() if not staff_df_for_doctor.empty else []
                        if not edit_doctor_options:
                            edit_doctor_options = ["N/A (कोई डॉक्टर पंजीकृत नहीं)"]
                        current_doctor = pat_data['Doctor'] if 'Doctor' in pat_data else None
                        edit_doctor_index = edit_doctor_options.index(current_doctor) if current_doctor in edit_doctor_options else 0
                        edit_p_doctor = st.selectbox("🧑‍⚕️ डॉक्टर बदलें (Change Doctor):", edit_doctor_options, index=edit_doctor_index)

                    selected_patient_data = {
                        'ID': patient_options[selected_pat_label], 'Date': str(pat_data['Date']), 'Center': str(pat_data['Center']),
                        'Child Name': pat_data['Child Name'], 'Parent Name': pat_data['Parent Name'], 'Mobile': pat_data['Mobile'],
                        'Age': pat_data['Age'], 'Doctor': current_doctor or '', 'Fees': int(pat_data['Fees']) if 'Fees' in pat_data else 0,
                        'Total Charge': default_total_charge,
                    }
                    st.download_button(
                        "🧾 इस मरीज की रसीद PDF (Reprint)",
                        data=generate_receipt_pdf(selected_patient_data),
                        file_name=f"Receipt_{patient_options[selected_pat_label]}.pdf",
                        mime="application/pdf",
                        key="reprint_receipt_download",
                    )
                    render_whatsapp_sender(selected_patient_data, key_prefix=f"edit_patient_{patient_options[selected_pat_label]}")

                    col_upd, col_del = st.columns(2)
                    with col_upd:
                        if st.button("💾 मरीज डेटा अपडेट करें (Update Patient)"):
                            if not is_valid_mobile(edit_p_mobile):
                                st.warning("⚠️ मोबाइल नंबर 10 अंकों का होना चाहिए। (Mobile number must be 10 digits.)")
                            else:
                                p_sheet = sh.worksheet("Patients")
                                p_orig_center = str(pat_data['Center'])
                                p_sheet.update(range_name=f"A{real_p_row_idx}:M{real_p_row_idx}", values=[[int(patient_options[selected_pat_label]), edit_c_name, edit_p_name, int(edit_c_age), edit_c_cond, str(edit_p_mobile), p_orig_center, str(pat_data['Date']), int(edit_c_fees), "", edit_p_type, edit_p_doctor, int(edit_c_total_charge)]])
                                target_date = str(pat_data['Date'])
                                log_audit(current_actor(), "Edit Patient", f"ID {patient_options[selected_pat_label]} ({edit_c_name}) updated")
                                sync_total_fees_batch(sh, target_date, p_orig_center)
                                sync_daily_collection_to_sheet(sh, target_date, p_orig_center)
                                st.cache_data.clear()
                                st.success("📝 रिकॉर्ड सफलतापूर्वक बैच मोड में अपडेटेड! (Record updated!)")
                                st.rerun()
                    with col_del:
                        if st.button("🗑️ मरीज रिकॉर्ड डिलीट करें (Delete Patient)"):
                            p_sheet = sh.worksheet("Patients")
                            p_sheet.delete_rows(real_p_row_idx)
                            log_audit(current_actor(), "Delete Patient", f"ID {patient_options[selected_pat_label]} ({pat_data['Child Name']}) deleted")
                            st.cache_data.clear()
                            st.success("🗑️ मरीज रिकॉर्ड डिलीट हो गया है! (Patient record deleted!)")
                            st.rerun()

        with tab_p3:
            st.markdown("#### 📜 किसी भी मरीज की पूरी विज़िट हिस्ट्री देखें (View Full Visit History)")
            hist_search = st.text_input("🔍 मोबाइल नंबर या बच्चे का नाम डालें (Enter Mobile/Name):", key="history_search")
            if not hist_search:
                st.info("💡 खोजने के लिए ऊपर मोबाइल नंबर या नाम टाइप करें। (Type mobile number or name above to search.)")
            elif center_patients.empty:
                st.info("कोई मरीज डेटा उपलब्ध नहीं है। (No patient data available.)")
            else:
                hist_mask = (
                    center_patients['Mobile'].str.contains(hist_search, case=False, na=False)
                    | center_patients['Child Name'].str.contains(hist_search, case=False, na=False)
                )
                hist_matches = center_patients[hist_mask]
                if hist_matches.empty:
                    st.info("💡 खोज से मेल खाता कोई मरीज नहीं मिला। (No matching patient found.)")
                else:
                    hist_sorted = hist_matches.sort_values('Date', ascending=False)
                    st.markdown(f"**कुल विज़िट (Total Visits): {len(hist_sorted)}**")
                    hist_cols = [c for c in ['Date', 'Child Name', 'Parent Name', 'Age', 'Condition', 'Doctor', 'Fees', 'Total Charge', 'Patient Type', 'Center'] if c in hist_sorted.columns]
                    st.dataframe(hist_sorted[hist_cols].reset_index(drop=True), use_container_width=True)

    elif menu == "📊 रिपोर्ट सेंटर (Advanced Reports)":
        st.markdown("<h2>📊 क्लिनिक एडवांस्ड रिपोर्ट पैनल (Advanced Report Panel)</h2>", unsafe_allow_html=True)
        tab_report1, tab_report2, tab_report3, tab_report4, tab_report5, tab_report6 = st.tabs([
            "🧒 मरीज एवं कलेक्शन रिपोर्ट (Patient & Collection)", "👥 स्टाफ अटेंडेंस रिपोर्ट (Staff Attendance)", "🧑‍⚕️ डॉक्टर परफॉर्मेंस (Doctor Performance)",
            "⏳ बकाया फीस (Due Fees)", "📉 फॉलो-अप ट्रैकर (Follow-up Tracker)", "📅 वार्षिक/त्रैमासिक तुलना (Yearly/Quarterly)"
        ])
        with tab_report1:
            patients_df = load_cloud_data_fast("Patients")
            if not patients_df.empty:
                if admin_view == "सभी सेंटर्स (All Centers)": center_df = patients_df.reset_index(drop=True)
                else: center_df = patients_df[patients_df['Center'] == admin_view].reset_index(drop=True)
                if not center_df.empty:
                    col_f1, col_f2 = st.columns(2)
                    with col_f1: report_filter = st.selectbox("📅 रिपोर्ट फ़िल्टर मोड चुनें (Select Filter Mode):", ["आज का रिकॉर्ड (Today Only)", "किसी पुरानी तारीख का रिकॉर्ड (Past Date)", "शुरू से अब तक का पूरा रिकॉर्ड (All Time)"])
                    filtered_df = center_df.copy()
                    if report_filter == "आज का रिकॉर्ड (Today Only)": filtered_df = center_df[center_df['Date'] == today_date]
                    elif report_filter == "किसी पुरानी तारीख का रिकॉर्ड (Past Date)":
                        with col_f2: selected_report_date = st.date_input("📆 पुरानी तारीख चुनें (Select Past Date):", datetime.today())
                        date_str = selected_report_date.strftime('%Y-%m-%d')
                        filtered_df = center_df[center_df['Date'] == date_str]
                    report_search = st.text_input("🔍 बच्चे/अभिभावक का नाम या मोबाइल नंबर से खोजें (Search by Name/Mobile):", key="report_patient_search")
                    if report_search:
                        mask = (
                            filtered_df['Child Name'].str.contains(report_search, case=False, na=False)
                            | filtered_df['Parent Name'].str.contains(report_search, case=False, na=False)
                            | filtered_df['Mobile'].str.contains(report_search, case=False, na=False)
                        )
                        filtered_df = filtered_df[mask]

                    t_patients = len(filtered_df)
                    t_fees = filtered_df['Fees'].sum() if 'Fees' in filtered_df.columns else 0
                    st.markdown(f"##### 📈 चयनित व्यू अवधि का परफॉर्मेंस समरी (Performance Summary)")
                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric("🧒 कुल पंजीकृत मरीज (Total Patients)", t_patients)
                    col_m2.metric("💵 कुल प्राप्त फीस (Total Fees Received)", f"₹ {t_fees}/-")

                    if not filtered_df.empty:
                        csv = filtered_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 रिपोर्ट Excel (CSV) डाउनलोड करें (Download CSV)",
                            data=csv,
                            file_name=f'Clinic_Report_{admin_view}_{today_date}.csv',
                            mime='text/csv',
                        )

                    st.write("---")
                    cols_to_show = [c for c in ['ID', 'Child Name', 'Parent Name', 'Age', 'Condition', 'Mobile', 'Date', 'Fees', 'Total Fees', 'Center', 'Patient Type'] if c in filtered_df.columns]
                    if not filtered_df.empty:
                        st.dataframe(filtered_df[cols_to_show].reset_index(drop=True), use_container_width=True)
                        st.download_button(
                            label="📄 रिपोर्ट PDF डाउनलोड करें (Download PDF)",
                            data=generate_table_pdf(f"Clinic Report - {admin_view} - {today_date}", filtered_df[cols_to_show].reset_index(drop=True), cols_to_show),
                            file_name=f'Clinic_Report_{admin_view}_{today_date}.pdf',
                            mime='application/pdf',
                        )
                    else: st.info("💡 चयनित क्राइटेरिया के लिए कोई मरीज रिकॉर्ड मौजूद नहीं है। (No matching patient records.)")
                else: st.info("💡 इस व्यू मोड पर कोई डेटा नहीं मिला। (No data found for this view.)")
            else: st.error("❌ डेटाबेस लोड करने में समस्या आ रही है। (Problem loading database.)")
        with tab_report2:
            st.markdown("### 📅 स्टाफ वाइज मंथली अटेंडेंस कैलकुलेटर (Staff-wise Monthly Attendance)")
            staff_data_df = load_cloud_data_fast("Staff")
            att_data_df = load_cloud_data_fast("Attendance")

            if 'Staff_ID' not in att_data_df.columns:
                st.error("⚠️ अटेंडेंस शीट में 'Staff_ID' कॉलम नहीं मिल रहा। कृपया अपनी Google Sheet में हेडर चेक करें। ('Staff_ID' column not found in Attendance sheet — please check headers.)")
            elif staff_data_df.empty or att_data_df.empty:
                st.info("💡 अभी सिस्टम में स्टाफ या अटेंडेंस का कोई रिकॉर्ड उपलब्ध नहीं है। (No staff or attendance records yet.)")
            else:
                col_y1, col_y2 = st.columns(2)
                with col_y1:
                    current_year = datetime.today().year
                    year_options = [str(y) for y in range(current_year - 2, current_year + 2)]
                    selected_year = st.selectbox("📅 साल चुनें (Select Year):", year_options, index=year_options.index(str(current_year)))
                with col_y2:
                    months_list = [("January", "01"), ("February", "02"), ("March", "03"), ("April", "04"), ("May", "05"), ("June", "06"), ("July", "07"), ("August", "08"), ("September", "09"), ("October", "10"), ("November", "11"), ("December", "12")]
                    selected_month_label = st.selectbox("📆 महीना चुनें (Select Month):", [m[0] for m in months_list], index=int(datetime.today().month)-1)
                    selected_month_num = next(m[1] for m in months_list if m[0] == selected_month_label)
                target_month_str = f"{selected_year}-{selected_month_num}"
                month_year_label = f"{selected_month_label} {selected_year}"
                if admin_view == "सभी सेंटर्स (All Centers)": filtered_staff = staff_data_df.copy()
                else: filtered_staff = staff_data_df[staff_data_df['Center'] == admin_view]
                if filtered_staff.empty: st.warning(f"⚠️ चयनित व्यू ({admin_view}) में कोई स्टाफ सदस्य पंजीकृत नहीं है। (No staff registered for this view.)")
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
                    if sheet_synced: st.success(f"📊 {month_year_label} की रिपोर्ट लाइव सिंक हो गई है! (Report synced!)")
                    
                    # --- EXPORT BUTTON FOR STAFF ---
                    if not summary_df.empty:
                        csv_staff = summary_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 स्टाफ रिपोर्ट Excel (CSV) डाउनलोड करें (Download CSV)",
                            data=csv_staff,
                            file_name=f'Staff_Report_{admin_view}_{target_month_str}.csv',
                            mime='text/csv',
                        )

                    st.dataframe(summary_df.reset_index(drop=True), use_container_width=True)

        with tab_report3:
            st.markdown("### 🧑‍⚕️ डॉक्टर-वार परफॉर्मेंस रिपोर्ट (Doctor-wise Performance)")
            doc_patients_df = load_cloud_data_fast("Patients")
            if admin_view == "सभी सेंटर्स (All Centers)":
                doc_center_df = doc_patients_df
            else:
                doc_center_df = doc_patients_df[doc_patients_df['Center'] == admin_view] if not doc_patients_df.empty else pd.DataFrame()

            if doc_center_df.empty or 'Doctor' not in doc_center_df.columns:
                st.info("💡 अभी तक किसी मरीज एंट्री में डॉक्टर दर्ज नहीं है। (No doctor recorded on any patient entry yet.)")
            else:
                doc_period = st.selectbox("📅 अवधि चुनें (Select Period):", ["इस महीने (This Month)", "शुरू से अब तक (All Time)"], key="doc_perf_period")
                doc_df = doc_center_df
                if doc_period == "इस महीने (This Month)":
                    doc_df = doc_center_df[doc_center_df['Date'].astype(str).str.startswith(today_date[:7])]
                doc_df = doc_df[doc_df['Doctor'].astype(str).str.strip().str.len() > 0]
                doc_df = doc_df[~doc_df['Doctor'].astype(str).str.startswith("N/A")]
                if doc_df.empty:
                    st.info("💡 चयनित अवधि के लिए कोई डेटा नहीं मिला। (No data found for this period.)")
                else:
                    doc_summary = doc_df.groupby('Doctor').agg(**{"कुल मरीज (Total Patients)": ('ID', 'count'), "कुल फीस (Total Fees) (₹)": ('Fees', 'sum')}).reset_index().sort_values("कुल मरीज (Total Patients)", ascending=False)
                    st.dataframe(doc_summary, use_container_width=True, hide_index=True)
                    st.bar_chart(doc_summary.set_index('Doctor')["कुल मरीज (Total Patients)"])

        with tab_report4:
            st.markdown("### ⏳ बकाया फीस ट्रैकर (Pending/Due Fees)")
            due_patients_df = load_cloud_data_fast("Patients")
            if admin_view == "सभी सेंटर्स (All Centers)":
                due_center_df = due_patients_df
            else:
                due_center_df = due_patients_df[due_patients_df['Center'] == admin_view] if not due_patients_df.empty else pd.DataFrame()

            if due_center_df.empty or 'Total Charge' not in due_center_df.columns:
                st.info("💡 कोई मरीज डेटा उपलब्ध नहीं है। (No patient data available.)")
            else:
                effective_charge = due_center_df['Total Charge'].where(due_center_df['Total Charge'] > 0, due_center_df['Fees'])
                due_center_df = due_center_df.assign(**{"बकाया राशि (Due Amount) (₹)": (effective_charge - due_center_df['Fees']).clip(lower=0)})
                due_only_df = due_center_df[due_center_df["बकाया राशि (Due Amount) (₹)"] > 0]
                if due_only_df.empty:
                    st.success("🎉 सभी मरीजों की फीस पूरी वसूल हो चुकी है, कोई बकाया नहीं है! (All fees collected, no dues!)")
                else:
                    st.metric("कुल बकाया राशि (Total Due Amount)", f"₹ {int(due_only_df['बकाया राशि (Due Amount) (₹)'].sum())}/-")
                    cols_due = [c for c in ['ID', 'Child Name', 'Parent Name', 'Mobile', 'Center', 'Date', 'Fees', 'Total Charge', 'बकाया राशि (Due Amount) (₹)'] if c in due_only_df.columns]
                    st.dataframe(due_only_df[cols_due].sort_values("बकाया राशि (Due Amount) (₹)", ascending=False).reset_index(drop=True), use_container_width=True)

        with tab_report5:
            st.markdown("### 📉 फॉलो-अप / ड्रॉपआउट ट्रैकर (Follow-up/Dropout Tracker)")
            st.caption("जो 'पुराने मरीज (Old Patient)' पिछले N दिनों में दोबारा नहीं आए, उनकी सूची। (List of old patients who haven't returned in N days.)")
            drop_patients_df = load_cloud_data_fast("Patients")
            if admin_view == "सभी सेंटर्स (All Centers)":
                drop_center_df = drop_patients_df
            else:
                drop_center_df = drop_patients_df[drop_patients_df['Center'] == admin_view] if not drop_patients_df.empty else pd.DataFrame()

            if drop_center_df.empty or 'Patient Type' not in drop_center_df.columns:
                st.info("💡 कोई मरीज डेटा उपलब्ध नहीं है। (No patient data available.)")
            else:
                dropout_days = st.slider("कितने दिनों से नहीं आया मरीज मानें (Dropout Threshold - Days):", min_value=7, max_value=90, value=30, step=1)
                drop_center_df = drop_center_df.copy()
                drop_center_df['_ParsedDate'] = pd.to_datetime(drop_center_df['Date'], format='%Y-%m-%d', errors='coerce')
                last_visit = drop_center_df.groupby(['Child Name', 'Parent Name', 'Mobile', 'Center'])['_ParsedDate'].max().reset_index()
                last_visit['दिन हुए (Days Since Last Visit)'] = (pd.Timestamp(datetime.today().date()) - last_visit['_ParsedDate']).dt.days
                dropout_list = last_visit[last_visit['दिन हुए (Days Since Last Visit)'] >= dropout_days].sort_values('दिन हुए (Days Since Last Visit)', ascending=False)
                if dropout_list.empty:
                    st.success("🎉 फिलहाल कोई मरीज ड्रॉपआउट लिस्ट में नहीं है! (No dropouts currently!)")
                else:
                    st.warning(f"⚠️ {len(dropout_list)} मरीज पिछले {dropout_days} दिनों से नहीं आए। ({len(dropout_list)} patients haven't visited in {dropout_days} days.)")
                    show_cols = ['Child Name', 'Parent Name', 'Mobile', 'Center', 'दिन हुए (Days Since Last Visit)']
                    st.dataframe(dropout_list[show_cols].reset_index(drop=True), use_container_width=True)

        with tab_report6:
            st.markdown("### 📅 वार्षिक/त्रैमासिक तुलना (Yearly/Quarterly Comparison)")
            trend_patients_df = load_cloud_data_fast("Patients")
            if admin_view == "सभी सेंटर्स (All Centers)":
                trend_center_df = trend_patients_df
            else:
                trend_center_df = trend_patients_df[trend_patients_df['Center'] == admin_view] if not trend_patients_df.empty else pd.DataFrame()

            if trend_center_df.empty:
                st.info("💡 कोई मरीज डेटा उपलब्ध नहीं है। (No patient data available.)")
            else:
                trend_center_df = trend_center_df.copy()
                trend_center_df['_ParsedDate'] = pd.to_datetime(trend_center_df['Date'], format='%Y-%m-%d', errors='coerce')
                trend_center_df = trend_center_df.dropna(subset=['_ParsedDate'])
                trend_center_df['साल'] = trend_center_df['_ParsedDate'].dt.year
                trend_center_df['तिमाही'] = "Q" + trend_center_df['_ParsedDate'].dt.quarter.astype(str)
                trend_center_df['महीना'] = trend_center_df['_ParsedDate'].dt.strftime('%Y-%m')

                comp_mode = st.radio("तुलना मोड चुनें (Select Comparison Mode):", ["महीना-वार (Monthly)", "तिमाही-वार (Quarterly)", "साल-वार (Yearly)"], horizontal=True)
                if comp_mode == "महीना-वार (Monthly)":
                    group_col = 'महीना'
                elif comp_mode == "तिमाही-वार (Quarterly)":
                    trend_center_df['तिमाही'] = trend_center_df['साल'].astype(str) + " " + trend_center_df['तिमाही']
                    group_col = 'तिमाही'
                else:
                    group_col = 'साल'

                comp_summary = trend_center_df.groupby(group_col).agg(**{"कुल मरीज (Total Patients)": ('ID', 'count'), "कुल कलेक्शन (Total Collection) (₹)": ('Fees', 'sum')}).reset_index().sort_values(group_col)
                st.dataframe(comp_summary, use_container_width=True, hide_index=True)
                st.line_chart(comp_summary.set_index(group_col)["कुल कलेक्शन (Total Collection) (₹)"])
                st.bar_chart(comp_summary.set_index(group_col)["कुल मरीज (Total Patients)"])

    elif menu == "🔑 पासवर्ड व क्लिनिक मैनेजर (Password & Clinic Manager)":
        st.markdown("<h2>🔑 पासवर्ड व सेंटर मैनेजमेंट (Password & Center Management)</h2>", unsafe_allow_html=True)

        tab_pwd, tab_center, tab_users = st.tabs(["🔐 पासवर्ड मैनेजमेंट (Password)", "🏥 सेंटर मैनेजमेंट (Center)", "👤 यूज़र मैनेजमेंट (Individual Login)"])

        pwd_sheet = sh.worksheet("Passwords")
        p_records = pwd_sheet.get_all_records()

        with tab_pwd:
            edit_center = st.selectbox("सेंटर चुनें (Select Center):", list(PASSWORDS.keys()))
            new_pwd_input = st.text_input("नया पासवर्ड (New Password):", type="password")
            if st.button("💾 पासवर्ड अपडेट करें (Update Password)"):
                row_to_update = next((idx + 2 for idx, r in enumerate(p_records) if r['Center'] == edit_center), None)
                if row_to_update and new_pwd_input.strip():
                    pwd_sheet.update(range_name=f"B{row_to_update}", values=[[hash_password(new_pwd_input.strip())]])
                    log_audit(current_actor(), "Update Password", f"Password changed for {edit_center}")
                    st.cache_data.clear()
                    st.success("🎉 पासवर्ड अपडेट हो गया! (Password updated!)")
                    st.rerun()

            st.markdown("---")
            st.subheader("🔐 दो-चरणीय सुरक्षा (Two-Factor Authentication - 2FA) — सिर्फ HR_Admin लॉगिन के लिए")
            current_totp_secret = get_totp_secret("HR_Admin")
            if current_totp_secret:
                st.success("✅ 2FA अभी सक्रिय है — HR_Admin के तौर पर लॉगिन करने के लिए पासवर्ड के बाद Authenticator ऐप का कोड भी माँगा जाएगा। (2FA is active — an authenticator code will be required after the password.)")
                if st.button("🗑️ 2FA बंद करें (Disable 2FA)"):
                    set_totp_secret("HR_Admin", "")
                    log_audit(current_actor(), "Disable 2FA", "HR_Admin")
                    st.success("2FA बंद कर दिया गया है। (2FA disabled.)")
                    st.rerun()
            else:
                st.info("2FA अभी सक्रिय नहीं है। नीचे QR कोड को Google Authenticator/Authy ऐप से स्कैन करके सेटअप करें। (2FA is not active. Scan the QR code below to set it up.)")
                if 'new_totp_secret' not in st.session_state:
                    st.session_state['new_totp_secret'] = pyotp.random_base32()
                setup_secret = st.session_state['new_totp_secret']
                totp_uri = pyotp.TOTP(setup_secret).provisioning_uri(name="HR_Admin", issuer_name="Normal Child Clinic")
                qr_buf = io.BytesIO()
                qrcode.make(totp_uri).save(qr_buf, format="PNG")
                st.image(qr_buf.getvalue(), caption="Authenticator ऐप से स्कैन करें (Scan with Authenticator app)", width=200)
                st.code(setup_secret, language=None)
                confirm_otp = st.text_input("ऊपर स्कैन करने के बाद ऐप में दिखने वाला 6-अंकों कोड डालें (Enter 6-digit code):", key="confirm_totp_setup", max_chars=6)
                if st.button("✅ 2FA एक्टिवेट करें (Activate 2FA)"):
                    if confirm_otp and pyotp.TOTP(setup_secret).verify(confirm_otp, valid_window=1):
                        set_totp_secret("HR_Admin", setup_secret)
                        del st.session_state['new_totp_secret']
                        log_audit(current_actor(), "Enable 2FA", "HR_Admin")
                        st.success("🎉 2FA सफलतापूर्वक एक्टिवेट हो गया है! (2FA activated!)")
                        st.rerun()
                    else:
                        st.error("❌ गलत कोड, दोबारा कोशिश करें। (Invalid code, try again.)")

        with tab_center:
            st.subheader("➕ नया सेंटर जोड़ें (Add New Center)")
            new_center_name = st.text_input("नये सेंटर का नाम (New Center Name):")
            new_center_pwd = st.text_input("नये सेंटर का पासवर्ड (New Center Password):", type="password")
            if st.button("🚀 नया सेंटर जोड़ें (Add Center)"):
                if new_center_name and new_center_pwd:
                    pwd_sheet.append_row([new_center_name, hash_password(new_center_pwd)])
                    log_audit(current_actor(), "Add Center", f"Center '{new_center_name}' added")
                    st.cache_data.clear()
                    st.success(f"🎉 सेंटर '{new_center_name}' सफलतापूर्वक जुड़ गया! (Center added!)")
                    st.rerun()

            st.markdown("---")
            st.subheader("🗑️ सेंटर हटाएं (Delete Center)")
            del_center = st.selectbox("हटाने के लिए सेंटर चुनें (Select Center to Delete):", actual_centers)
            if st.button("❌ सेंटर डिलीट करें (Delete Center)"):
                staff_check_df = load_cloud_data_fast("Staff")
                patients_check_df = load_cloud_data_fast("Patients")
                staff_count = len(staff_check_df[staff_check_df['Center'] == del_center]) if not staff_check_df.empty and 'Center' in staff_check_df.columns else 0
                patient_count = len(patients_check_df[patients_check_df['Center'] == del_center]) if not patients_check_df.empty and 'Center' in patients_check_df.columns else 0
                if staff_count > 0 or patient_count > 0:
                    st.error(f"⚠️ '{del_center}' सेंटर डिलीट नहीं किया जा सकता — इसमें अभी भी {staff_count} स्टाफ और {patient_count} मरीज रिकॉर्ड मौजूद हैं। पहले उन्हें किसी दूसरे सेंटर में ट्रांसफर करें। (Cannot delete — {staff_count} staff and {patient_count} patient records still linked to this center.)")
                else:
                    row_idx = next((idx + 2 for idx, r in enumerate(p_records) if r['Center'] == del_center), None)
                    if row_idx:
                        pwd_sheet.delete_rows(row_idx)
                        log_audit(current_actor(), "Delete Center", f"Center '{del_center}' deleted")
                        st.cache_data.clear()
                        st.success(f"🗑️ सेंटर '{del_center}' हटा दिया गया है! (Center deleted!)")
                        st.rerun()

        with tab_users:
            st.caption("यहाँ से हर स्टाफ सदस्य के लिए अलग यूज़रनेम/पासवर्ड बनाएं ताकि वो सेंटर पासवर्ड के बजाय अपनी खुद की लॉगिन (सिर्फ उनके रोल जितनी एक्सेस के साथ) इस्तेमाल कर सके। (Create a separate username/password for each staff member for individual, role-limited login.)")
            user_role_options = ["Homeopathic Doctor", "Pharmacist (Medicine Maker)", "Receptionist", "Maid / Housekeeping"]
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                new_username = st.text_input("यूज़रनेम (Username):", key="new_username")
                new_user_fullname = st.text_input("पूरा नाम (Full Name):", key="new_user_fullname")
                new_user_role = st.selectbox("रोल (Role):", user_role_options, key="new_user_role")
            with col_u2:
                new_user_center = st.selectbox("सेंटर (Center):", actual_centers, key="new_user_center")
                new_user_password = st.text_input("पासवर्ड (Password):", type="password", key="new_user_password")
            if st.button("🚀 यूज़र बनाएं (Create User)"):
                if not new_username or not new_user_fullname or not new_user_password:
                    st.warning("⚠️ कृपया सभी फ़ील्ड भरें। (Please fill all fields.)")
                else:
                    try:
                        users_sheet = sh.worksheet("Users")
                    except Exception:
                        users_sheet = sh.add_worksheet(title="Users", rows="1000", cols="6")
                        users_sheet.update(range_name="A1:F1", values=[["ID", "Username", "Full Name", "Role", "Center", "PasswordHash"]])
                    all_user_rows = users_sheet.get_all_values()
                    if any(str(r[1]).strip().lower() == new_username.strip().lower() for r in all_user_rows[1:] if len(r) > 1):
                        st.error("❌ यह यूज़रनेम पहले से मौजूद है, कोई दूसरा चुनें। (Username already exists, choose another.)")
                    else:
                        existing_user_ids = [int(r[0]) for r in all_user_rows[1:] if r and str(r[0]).strip().isdigit()]
                        next_user_id = max(existing_user_ids) + 1 if existing_user_ids else 1
                        users_sheet.append_row([next_user_id, new_username.strip(), new_user_fullname, new_user_role, new_user_center, hash_password(new_user_password)])
                        log_audit(current_actor(), "Add User", f"{new_username} ({new_user_role}, {new_user_center})")
                        st.cache_data.clear()
                        st.success(f"🎉 यूज़र '{new_username}' बन गया है! (User created!)")
                        st.rerun()

            st.markdown("---")
            st.subheader("📋 मौजूदा यूज़र्स (Existing Users)")
            users_df = load_cloud_data_fast("Users")
            if users_df.empty:
                st.info("अभी कोई इंडिविजुअल यूज़र नहीं बना है। (No individual users created yet.)")
            else:
                st.dataframe(users_df[['ID', 'Username', 'Full Name', 'Role', 'Center']].reset_index(drop=True), use_container_width=True)
                st.subheader("🗑️ यूज़र हटाएं (Delete User)")
                del_user_options = {f"{r['Username']} - {r['Full Name']} ({r['Center']})": r['ID'] for _, r in users_df.iterrows()}
                del_user_label = st.selectbox("हटाने के लिए यूज़र चुनें (Select User to Delete):", list(del_user_options.keys()), key="del_user_select")
                if st.button("❌ यूज़र डिलीट करें (Delete User)"):
                    users_sheet = sh.worksheet("Users")
                    all_user_rows = users_sheet.get_all_values()
                    target_user_id = str(del_user_options[del_user_label])
                    row_to_delete = next((idx + 2 for idx, r in enumerate(all_user_rows[1:]) if r and str(r[0]).strip() == target_user_id), None)
                    if row_to_delete:
                        users_sheet.delete_rows(row_to_delete)
                        log_audit(current_actor(), "Delete User", del_user_label)
                        st.cache_data.clear()
                        st.success("🗑️ यूज़र डिलीट हो गया है! (User deleted!)")
                        st.rerun()

    elif menu == "💰 फाइनेंस (Finance)":
        st.markdown("<h2>💰 फाइनेंस मैनेजमेंट</h2>", unsafe_allow_html=True)
        tab_f1, tab_f2, tab_f3 = st.tabs(["➕ खर्च जोड़ें", "📋 खर्च सूची", "📊 रेवेन्यू vs एक्सपेंस"])
        expense_categories = ["Rent (किराया)", "Salary (सैलरी)", "Medicine Purchase (दवा खरीद)", "Electricity (बिजली)", "Maintenance (रखरखाव)", "Other (अन्य)"]

        with tab_f1:
            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                exp_date = st.date_input("📆 तारीख:", datetime.today(), key="exp_date")
                if selected_center == "HR_Admin":
                    exp_center = st.selectbox("🎯 सेंटर चुनें:", actual_centers, key="exp_center")
                else:
                    exp_center = selected_center
            with col_ex2:
                exp_category = st.selectbox("📂 श्रेणी:", expense_categories, key="exp_category")
                exp_amount = st.number_input("💵 राशि (₹):", min_value=0, value=0, step=100, key="exp_amount")
            exp_desc = st.text_input("📝 विवरण (Description):", key="exp_desc")
            if st.button("💾 खर्च सेव करें"):
                if exp_amount <= 0:
                    st.warning("⚠️ कृपया राशि 0 से ज्यादा डालें।")
                else:
                    try:
                        exp_sheet = sh.worksheet("Expenses")
                    except Exception:
                        exp_sheet = sh.add_worksheet(title="Expenses", rows="1000", cols="6")
                        exp_sheet.update(range_name="A1:F1", values=[["ID", "Date", "Center", "Category", "Amount", "Description"]])
                    all_exp_rows = exp_sheet.get_all_values()
                    existing_exp_ids = [int(r[0]) for r in all_exp_rows[1:] if r and str(r[0]).strip().isdigit()]
                    next_exp_id = max(existing_exp_ids) + 1 if existing_exp_ids else 1
                    exp_sheet.append_row([next_exp_id, exp_date.strftime('%Y-%m-%d'), exp_center, exp_category, int(exp_amount), exp_desc])
                    log_audit(current_actor(), "Add Expense", f"{exp_category} - ₹{int(exp_amount)} ({exp_center})")
                    st.cache_data.clear()
                    st.success("🎉 खर्च सफलतापूर्वक दर्ज हो गया!")
                    st.rerun()

        with tab_f2:
            expenses_df = load_cloud_data_fast("Expenses")
            if admin_view == "सभी सेंटर्स (All Centers)":
                view_exp_df = expenses_df
            else:
                view_exp_df = expenses_df[expenses_df['Center'] == admin_view] if not expenses_df.empty and 'Center' in expenses_df.columns else pd.DataFrame()

            if view_exp_df.empty:
                st.info("कोई खर्च डेटा उपलब्ध नहीं है।")
            else:
                st.metric("कुल खर्च", f"₹ {int(view_exp_df['Amount'].sum())}/-")
                st.dataframe(view_exp_df[['ID', 'Date', 'Center', 'Category', 'Amount', 'Description']].sort_values('Date', ascending=False).reset_index(drop=True), use_container_width=True)

                st.markdown("---")
                st.subheader("🗑️ खर्च एंट्री हटाएं")
                del_exp_options = {f"{r['Date']} - {r['Category']} - ₹{r['Amount']} ({r['Center']})": r['ID'] for _, r in view_exp_df.iterrows()}
                del_exp_label = st.selectbox("हटाने के लिए एंट्री चुनें:", list(del_exp_options.keys()), key="del_exp_select")
                if st.button("❌ खर्च डिलीट करें"):
                    exp_sheet = sh.worksheet("Expenses")
                    all_exp_rows = exp_sheet.get_all_values()
                    target_exp_id = str(del_exp_options[del_exp_label])
                    row_to_delete = next((idx + 2 for idx, r in enumerate(all_exp_rows[1:]) if r and str(r[0]).strip() == target_exp_id), None)
                    if row_to_delete:
                        exp_sheet.delete_rows(row_to_delete)
                        log_audit(current_actor(), "Delete Expense", del_exp_label)
                        st.cache_data.clear()
                        st.success("🗑️ खर्च एंट्री डिलीट हो गई है!")
                        st.rerun()

        with tab_f3:
            st.markdown("### 📊 रेवेन्यू vs एक्सपेंस रिपोर्ट")
            rev_period = st.selectbox("📅 अवधि चुनें:", ["इस महीने (This Month)", "शुरू से अब तक (All Time)"], key="rev_exp_period")
            rev_patients_df = load_cloud_data_fast("Patients")
            rev_expenses_df = load_cloud_data_fast("Expenses")
            rev_consultations_df = load_cloud_data_fast("Consultations")

            if admin_view == "सभी सेंटर्स (All Centers)":
                rev_p_df = rev_patients_df
                rev_e_df = rev_expenses_df
                rev_c_df = rev_consultations_df
            else:
                rev_p_df = rev_patients_df[rev_patients_df['Center'] == admin_view] if not rev_patients_df.empty else pd.DataFrame()
                rev_e_df = rev_expenses_df[rev_expenses_df['Center'] == admin_view] if not rev_expenses_df.empty and 'Center' in rev_expenses_df.columns else pd.DataFrame()
                rev_c_df = rev_consultations_df[rev_consultations_df['Center'] == admin_view] if not rev_consultations_df.empty else pd.DataFrame()

            if rev_period == "इस महीने (This Month)":
                if not rev_p_df.empty: rev_p_df = rev_p_df[rev_p_df['Date'].astype(str).str.startswith(today_date[:7])]
                if not rev_e_df.empty: rev_e_df = rev_e_df[rev_e_df['Date'].astype(str).str.startswith(today_date[:7])]
                if not rev_c_df.empty: rev_c_df = rev_c_df[rev_c_df['Date'].astype(str).str.startswith(today_date[:7])]

            total_revenue = (rev_p_df['Fees'].sum() if not rev_p_df.empty and 'Fees' in rev_p_df.columns else 0) + (rev_c_df['Total Fees'].sum() if not rev_c_df.empty and 'Total Fees' in rev_c_df.columns else 0)
            total_expense = rev_e_df['Amount'].sum() if not rev_e_df.empty and 'Amount' in rev_e_df.columns else 0
            net_profit = total_revenue - total_expense

            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1: st.metric("💵 कुल रेवेन्यू", f"₹ {int(total_revenue)}/-")
            with col_r2: st.metric("💸 कुल खर्च", f"₹ {int(total_expense)}/-")
            with col_r3: st.metric("📈 नेट प्रॉफिट", f"₹ {int(net_profit)}/-")

            if not rev_e_df.empty:
                st.markdown("##### 📂 श्रेणी-वार खर्च वितरण")
                st.bar_chart(rev_e_df.groupby('Category')['Amount'].sum())

            st.markdown("##### 📈 पिछले 6 महीनों का रेवेन्यू vs एक्सपेंस")
            months_back = [(datetime.today().replace(day=1) - timedelta(days=30 * i)).strftime('%Y-%m') for i in range(5, -1, -1)]
            all_p_for_trend = rev_patients_df if admin_view == "सभी सेंटर्स (All Centers)" else (rev_patients_df[rev_patients_df['Center'] == admin_view] if not rev_patients_df.empty else pd.DataFrame())
            all_e_for_trend = rev_expenses_df if admin_view == "सभी सेंटर्स (All Centers)" else (rev_expenses_df[rev_expenses_df['Center'] == admin_view] if not rev_expenses_df.empty and 'Center' in rev_expenses_df.columns else pd.DataFrame())
            all_c_for_trend = rev_consultations_df if admin_view == "सभी सेंटर्स (All Centers)" else (rev_consultations_df[rev_consultations_df['Center'] == admin_view] if not rev_consultations_df.empty else pd.DataFrame())
            monthly_rows = []
            for m in months_back:
                m_rev = all_p_for_trend[all_p_for_trend['Date'].astype(str).str.startswith(m)]['Fees'].sum() if not all_p_for_trend.empty else 0
                m_rev += all_c_for_trend[all_c_for_trend['Date'].astype(str).str.startswith(m)]['Total Fees'].sum() if not all_c_for_trend.empty and 'Total Fees' in all_c_for_trend.columns else 0
                m_exp = all_e_for_trend[all_e_for_trend['Date'].astype(str).str.startswith(m)]['Amount'].sum() if not all_e_for_trend.empty else 0
                monthly_rows.append({"महीना": m, "रेवेन्यू": int(m_rev), "खर्च": int(m_exp)})
            monthly_comp_df = pd.DataFrame(monthly_rows).set_index("महीना")
            st.line_chart(monthly_comp_df)

    elif menu == "🩺 परामर्श (Consultation)":
        st.markdown("<h2>🩺 परामर्श / कंसल्टेशन (Consultation)</h2>", unsafe_allow_html=True)
        tab_c1, tab_c2 = st.tabs(["➕ नया परामर्श जोड़ें (Add Consultation)", "📜 परामर्श इतिहास (Consultation History)"])

        with tab_c1:
            if st.session_state.get('last_consultation'):
                lc = st.session_state['last_consultation']
                st.success(f"🎉 {lc['Child Name']} का परामर्श सुरक्षित हो गया है ({lc['Date']})! (Consultation saved!)")
                st.download_button(
                    "📥 प्रिस्क्रिप्शन PDF डाउनलोड करें (Download Prescription PDF)",
                    data=generate_prescription_pdf(lc),
                    file_name=f"Prescription_{lc['ID']}.pdf",
                    mime="application/pdf",
                    key="prescription_pdf_download",
                )
                st.markdown("---")

            if selected_center == "HR_Admin":
                cons_center = st.selectbox("🎯 सेंटर चुनें (Select Center):", actual_centers, key="cons_center")
            else:
                cons_center = selected_center

            cons_patients_df = load_cloud_data_fast("Patients")
            cons_center_patients = cons_patients_df[cons_patients_df['Center'] == cons_center] if not cons_patients_df.empty else pd.DataFrame()
            cons_unique_patients = cons_center_patients.drop_duplicates(subset=['Child Name', 'Mobile']) if not cons_center_patients.empty else pd.DataFrame()

            if cons_unique_patients.empty:
                st.info("इस सेंटर में अभी कोई रजिस्टर्ड मरीज नहीं है। पहले 'मरीज रजिस्ट्रेशन' से मरीज जोड़ें। (No registered patients — add one via Patient Entry first.)")
            else:
                cons_patient_search = st.text_input("🔍 मरीज खोजें (नाम/मोबाइल) (Search Patient):", key="cons_patient_search")
                cons_search_pool = cons_unique_patients
                if cons_patient_search:
                    mask = (
                        cons_unique_patients['Child Name'].str.contains(cons_patient_search, case=False, na=False)
                        | cons_unique_patients['Mobile'].str.contains(cons_patient_search, case=False, na=False)
                    )
                    cons_search_pool = cons_unique_patients[mask]

                if cons_search_pool.empty:
                    st.info("💡 खोज से मेल खाता कोई मरीज नहीं मिला। (No matching patient found.)")
                else:
                    cons_patient_options = {f"{r['Child Name']} - {r['Mobile']}": (r['Child Name'], r['Parent Name'], r['Mobile']) for _, r in cons_search_pool.iterrows()}
                    cons_selected_label = st.selectbox("मरीज चुनें (Select Patient):", list(cons_patient_options.keys()), key="cons_patient_select")
                    cons_child_name, cons_parent_name, cons_mobile = cons_patient_options[cons_selected_label]

                    all_consultations_df = load_cloud_data_fast("Consultations")
                    patient_history = pd.DataFrame()
                    if not all_consultations_df.empty and 'Mobile' in all_consultations_df.columns:
                        patient_history = all_consultations_df[
                            (all_consultations_df['Mobile'] == cons_mobile) & (all_consultations_df['Child Name'] == cons_child_name)
                        ].sort_values('Date', ascending=False)

                    with st.expander(f"📜 {cons_child_name} का पिछला परामर्श इतिहास (Past Consultation History) ({len(patient_history)})", expanded=False):
                        if patient_history.empty:
                            st.caption("कोई पिछला परामर्श रिकॉर्ड नहीं है। (No past consultation records.)")
                        else:
                            hist_cols = [c for c in ['Date', 'Doctor', 'Chief Complaint', 'Prescription', 'Medicine Given', 'Weight (kg)', 'Total Fees', 'Next Follow-up Date'] if c in patient_history.columns]
                            st.dataframe(patient_history[hist_cols].reset_index(drop=True), use_container_width=True)

                    st.markdown("---")
                    st.markdown("#### 📝 नया परामर्श विवरण (New Consultation Details)")

                    staff_for_cons = load_cloud_data_fast("Staff")
                    doctor_list = staff_for_cons[(staff_for_cons['Center'] == cons_center) & (staff_for_cons['Role'] == 'Homeopathic Doctor')]['Name'].tolist() if not staff_for_cons.empty else []
                    if not doctor_list:
                        doctor_list = ["N/A (कोई डॉक्टर पंजीकृत नहीं)"]

                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        cons_date = st.date_input("📆 परामर्श तारीख (Consultation Date):", datetime.today(), key="cons_date")
                        cons_doctor = st.selectbox("🧑‍⚕️ डॉक्टर (Doctor):", doctor_list, key="cons_doctor")
                        cons_weight = st.number_input("⚖️ वजन (Weight) (kg):", min_value=0.0, value=0.0, step=0.1, key="cons_weight")
                        cons_followup = st.date_input("📅 अगली फॉलो-अप तारीख (Next Follow-up Date - Optional):", datetime.today() + timedelta(days=15), key="cons_followup")
                    with col_c2:
                        cons_consultation_charge = st.number_input("💵 कंसल्टेशन चार्ज (Consultation Charges) (₹):", min_value=0, value=0, step=50, key="cons_consultation_charge")
                        cons_medicine_charge = st.number_input("💊 मेडिसिन चार्ज (Medicine Charges) (₹):", min_value=0, value=0, step=50, key="cons_medicine_charge")
                        cons_total_fees = st.number_input(
                            "🧾 कुल प्राप्त फीस (Total Fees Collected) (₹):", min_value=0,
                            value=cons_consultation_charge + cons_medicine_charge, step=50, key="cons_total_fees",
                            help="डिफ़ॉल्ट = कंसल्टेशन + मेडिसिन चार्ज, ज़रूरत हो तो बदलें (डिस्काउंट/आंशिक भुगतान)। (Default = consultation + medicine charge, editable for discounts/partial payment.)",
                        )

                    cons_complaint = st.text_area("🩺 मुख्य शिकायत / निदान (Chief Complaint / Diagnosis):", key="cons_complaint")
                    cons_prescription = st.text_area("📋 प्रिस्क्रिप्शन (दवा व सलाह) (Prescription):", key="cons_prescription")
                    cons_medicine_given = st.text_area("💊 दी गई दवा (Medicine Given):", key="cons_medicine_given")
                    cons_notes = st.text_area("📝 अतिरिक्त नोट्स (Additional Notes - Optional):", key="cons_notes")

                    if st.button("💾 परामर्श सुरक्षित करें (Save Consultation)"):
                        try:
                            cons_sheet = sh.worksheet("Consultations")
                        except Exception:
                            cons_sheet = sh.add_worksheet(title="Consultations", rows="2000", cols="16")
                            cons_sheet.update(range_name="A1:P1", values=[[
                                "ID", "Date", "Center", "Doctor", "Child Name", "Parent Name", "Mobile",
                                "Chief Complaint", "Prescription", "Medicine Given", "Weight (kg)",
                                "Consultation Charges", "Medicine Charges", "Total Fees", "Next Follow-up Date", "Notes"
                            ]])
                        all_cons_rows = cons_sheet.get_all_values()
                        existing_cons_ids = [int(r[0]) for r in all_cons_rows[1:] if r and str(r[0]).strip().isdigit()]
                        next_cons_id = max(existing_cons_ids) + 1 if existing_cons_ids else 1
                        cons_date_str = cons_date.strftime('%Y-%m-%d')
                        cons_followup_str = cons_followup.strftime('%Y-%m-%d')
                        cons_sheet.append_row([
                            next_cons_id, cons_date_str, cons_center, cons_doctor, cons_child_name, cons_parent_name, cons_mobile,
                            cons_complaint, cons_prescription, cons_medicine_given, cons_weight,
                            int(cons_consultation_charge), int(cons_medicine_charge), int(cons_total_fees), cons_followup_str, cons_notes,
                        ])
                        log_audit(current_actor(), "Add Consultation", f"{cons_child_name} ({cons_center}) by {cons_doctor} on {cons_date_str}")
                        st.session_state['last_consultation'] = {
                            'ID': next_cons_id, 'Date': cons_date_str, 'Center': cons_center, 'Doctor': cons_doctor,
                            'Child Name': cons_child_name, 'Parent Name': cons_parent_name, 'Mobile': cons_mobile,
                            'Chief Complaint': cons_complaint, 'Prescription': cons_prescription, 'Medicine Given': cons_medicine_given,
                            'Weight (kg)': cons_weight, 'Consultation Charges': int(cons_consultation_charge),
                            'Medicine Charges': int(cons_medicine_charge), 'Total Fees': int(cons_total_fees),
                            'Next Follow-up Date': cons_followup_str, 'Notes': cons_notes,
                        }
                        st.cache_data.clear()
                        st.rerun()

        with tab_c2:
            hist_consultations_df = load_cloud_data_fast("Consultations")
            if admin_view == "सभी सेंटर्स (All Centers)":
                hist_cons_scope = hist_consultations_df
            else:
                hist_cons_scope = hist_consultations_df[hist_consultations_df['Center'] == admin_view] if not hist_consultations_df.empty else pd.DataFrame()

            if hist_cons_scope.empty:
                st.info("कोई परामर्श रिकॉर्ड उपलब्ध नहीं है। (No consultation records available.)")
            else:
                cons_hist_search = st.text_input("🔍 मरीज का नाम या मोबाइल नंबर खोजें (Search by Name/Mobile):", key="cons_hist_search")
                filtered_hist = hist_cons_scope
                if cons_hist_search:
                    mask = (
                        hist_cons_scope['Child Name'].str.contains(cons_hist_search, case=False, na=False)
                        | hist_cons_scope['Mobile'].str.contains(cons_hist_search, case=False, na=False)
                    )
                    filtered_hist = hist_cons_scope[mask]

                if filtered_hist.empty:
                    st.info("💡 खोज से मेल खाता कोई परामर्श नहीं मिला। (No matching consultation found.)")
                else:
                    filtered_hist = filtered_hist.sort_values('Date', ascending=False)
                    col_ch1, col_ch2 = st.columns(2)
                    col_ch1.metric("कुल परामर्श (Total Consultations)", len(filtered_hist))
                    col_ch2.metric("कुल कलेक्शन (Total Collection) (₹)", f"₹ {int(filtered_hist['Total Fees'].sum())}/-" if 'Total Fees' in filtered_hist.columns else "₹ 0/-")
                    show_cols = [c for c in ['Date', 'Child Name', 'Parent Name', 'Mobile', 'Doctor', 'Chief Complaint', 'Medicine Given', 'Consultation Charges', 'Medicine Charges', 'Total Fees', 'Next Follow-up Date', 'Center'] if c in filtered_hist.columns]
                    st.dataframe(filtered_hist[show_cols].reset_index(drop=True), use_container_width=True)

    elif menu == "🎫 अपॉइंटमेंट (Appointments)":
        st.markdown("<h2>🎫 अपॉइंटमेंट / टोकन बुकिंग (Appointment/Token Booking)</h2>", unsafe_allow_html=True)
        tab_ap1, tab_ap2 = st.tabs(["➕ नई अपॉइंटमेंट बुक करें (Book New)", "📋 आज की टोकन क्यू (Today's Queue)"])
        time_slots = []
        for hour in range(9, 19):
            for minute in (0, 30):
                if hour == 13:
                    continue  # लंच ब्रेक 1:00-2:00 PM
                if hour == 18 and minute == 30:
                    continue  # क्लिनिक 6:00 PM पर बंद
                time_slots.append(datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").strftime("%I:%M %p").lstrip("0"))

        with tab_ap1:
            if st.session_state.get('last_appointment'):
                last_appt = st.session_state['last_appointment']
                st.success(f"🎉 {last_appt['Name']} की अपॉइंटमेंट बुक हो गई! टोकन नंबर: #{last_appt['Token']} — WhatsApp पर भेजें:")
                render_appointment_whatsapp(last_appt['Name'], last_appt['Mobile'], last_appt['Center'], last_appt['Date'], last_appt['Time Slot'], last_appt['Token'])
                st.markdown("---")

            if selected_center == "HR_Admin":
                ap_center = st.selectbox("🎯 सेंटर चुनें:", actual_centers, key="ap_center")
            else:
                ap_center = selected_center

            patients_for_appt = load_cloud_data_fast("Patients")
            center_registered_patients = patients_for_appt[patients_for_appt['Center'] == ap_center] if not patients_for_appt.empty else pd.DataFrame()
            unique_patients = center_registered_patients.drop_duplicates(subset=['Child Name', 'Mobile']) if not center_registered_patients.empty else pd.DataFrame()

            entry_mode = st.radio("मरीज कैसे चुनें:", ["📋 रजिस्टर्ड मरीज चुनें", "✍️ नया नाम टाइप करें"], horizontal=True, key="ap_entry_mode")

            col_a1, col_a2 = st.columns(2)
            with col_a1:
                if entry_mode == "📋 रजिस्टर्ड मरीज चुनें":
                    if unique_patients.empty:
                        st.info("इस सेंटर में अभी कोई रजिस्टर्ड मरीज नहीं है। 'नया नाम टाइप करें' चुनें।")
                        ap_name, ap_mobile = "", ""
                    else:
                        patient_search_options = {f"{r['Child Name']} - {r['Mobile']}": (r['Child Name'], r['Mobile']) for _, r in unique_patients.iterrows()}
                        selected_patient_label = st.selectbox("🔍 मरीज खोजें/चुनें (टाइप करके सर्च करें):", list(patient_search_options.keys()), key="ap_patient_select")
                        ap_name, ap_mobile = patient_search_options[selected_patient_label]
                        st.caption(f"📞 मोबाइल: {ap_mobile}")
                else:
                    ap_name = st.text_input("🧒 बच्चे/मरीज का नाम:", key="ap_manual_name")
                    ap_mobile = st.text_input("📞 मोबाइल नंबर:", max_chars=10, key="ap_manual_mobile")
            with col_a2:
                ap_date = st.date_input("📆 अपॉइंटमेंट तारीख:", datetime.today(), key="ap_date")
                ap_slot = st.selectbox("⏰ टाइम स्लॉट चुनें:", time_slots)

            if st.button("🎯 अपॉइंटमेंट बुक करें"):
                if not ap_name or not ap_mobile:
                    st.warning("⚠️ कृपया नाम और मोबाइल नंबर भरें।")
                elif not is_valid_mobile(ap_mobile):
                    st.warning("⚠️ मोबाइल नंबर 10 अंकों का होना चाहिए।")
                else:
                    try:
                        ap_sheet = sh.worksheet("Appointments")
                    except Exception:
                        ap_sheet = sh.add_worksheet(title="Appointments", rows="1000", cols="8")
                        ap_sheet.update(range_name="A1:H1", values=[["ID", "Token", "Name", "Mobile", "Center", "Date", "Time Slot", "Status"]])
                    all_ap_rows = ap_sheet.get_all_values()
                    existing_ap_ids = [int(r[0]) for r in all_ap_rows[1:] if r and str(r[0]).strip().isdigit()]
                    next_ap_id = max(existing_ap_ids) + 1 if existing_ap_ids else 1
                    ap_date_str = ap_date.strftime('%Y-%m-%d')
                    same_day_tokens = [int(r[1]) for r in all_ap_rows[1:] if len(r) >= 6 and str(r[4]).strip() == ap_center and str(r[5]).strip() == ap_date_str and str(r[1]).strip().isdigit()]
                    next_token = max(same_day_tokens) + 1 if same_day_tokens else 1
                    ap_sheet.append_row([next_ap_id, next_token, ap_name, str(ap_mobile), ap_center, ap_date_str, ap_slot, "Booked"])
                    log_audit(current_actor(), "Book Appointment", f"{ap_name} ({ap_center}) - {ap_date_str} {ap_slot}, Token #{next_token}")
                    st.session_state['last_appointment'] = {
                        'Name': ap_name, 'Mobile': str(ap_mobile), 'Center': ap_center,
                        'Date': ap_date_str, 'Time Slot': ap_slot, 'Token': next_token,
                    }
                    st.cache_data.clear()
                    st.rerun()

        with tab_ap2:
            appointments_df = load_cloud_data_fast("Appointments")
            if admin_view == "सभी सेंटर्स (All Centers)":
                today_ap = appointments_df[appointments_df['Date'] == today_date] if not appointments_df.empty else pd.DataFrame()
            else:
                today_ap = appointments_df[(appointments_df['Center'] == admin_view) & (appointments_df['Date'] == today_date)] if not appointments_df.empty else pd.DataFrame()

            if today_ap.empty:
                st.info("💡 आज के लिए कोई अपॉइंटमेंट बुक नहीं है।")
            else:
                today_ap = today_ap.copy()
                today_ap['Token'] = pd.to_numeric(today_ap['Token'], errors='coerce')
                today_ap = today_ap.sort_values('Token')
                st.dataframe(today_ap[['Token', 'Name', 'Mobile', 'Time Slot', 'Status', 'Center']].reset_index(drop=True), use_container_width=True)

                st.markdown("---")
                st.subheader("✅ स्टेटस अपडेट करें")
                ap_status_options = {f"Token #{int(r['Token'])} - {r['Name']} ({r['Time Slot']})": r['ID'] for _, r in today_ap.iterrows()}
                ap_selected_label = st.selectbox("अपॉइंटमेंट चुनें:", list(ap_status_options.keys()), key="ap_status_select")
                new_ap_status = st.selectbox("नया स्टेटस:", ["Booked", "Completed", "Cancelled", "No Show"], key="ap_new_status")
                if st.button("💾 स्टेटस अपडेट करें"):
                    ap_sheet = sh.worksheet("Appointments")
                    all_ap_rows = ap_sheet.get_all_values()
                    target_ap_id = str(ap_status_options[ap_selected_label])
                    row_to_update = next((idx + 2 for idx, r in enumerate(all_ap_rows[1:]) if r and str(r[0]).strip() == target_ap_id), None)
                    if row_to_update:
                        ap_sheet.update_cell(row_to_update, 8, new_ap_status)
                        log_audit(current_actor(), "Update Appointment Status", f"{ap_selected_label} -> {new_ap_status}")
                        st.cache_data.clear()
                        st.success("✅ स्टेटस अपडेट हो गया!")
                        st.rerun()

else:
    st.info("🔒 कृपया डेटा एक्सेस करने के लिए पासवर्ड डालकर 'Login' बटन पर क्लिक करें।")
