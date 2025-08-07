import os
import json
import base64
from flask import Flask, render_template, request, redirect, url_for, session, flash
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import gspread
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default-key')

# Hardcoded users (replace with database or hashed passwords later)
USERS = {'karim': '2425', 'admin': 'admin123','yomna': '3030'}

# Google API scopes
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Load Google credentials (works both locally and on Railway)
google_creds_env = os.getenv("GOOGLE_CREDENTIALS")

if google_creds_env:
    # Load from environment variable (Railway / prod)
    creds_json = base64.b64decode(google_creds_env).decode("utf-8")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
elif os.path.exists("creds.json"):
    # Load from local file (dev)
    creds = Credentials.from_service_account_file("creds.json", scopes=scope)
else:
    raise RuntimeError("Google credentials not found. Set GOOGLE_CREDENTIALS env variable or provide creds.json")

# Authorize Google Sheets
client = gspread.authorize(creds)
spreadsheet = client.open("Resala")

# Google Sheets setup
families_sheet = spreadsheet.worksheet("Families")
visits_sheet = spreadsheet.worksheet("Visits")
products_sheet = spreadsheet.worksheet("Products")

# Expected headers for validation
FAMILY_HEADERS = ["FamilyNumber", "Name", "NationalID", "MobileNumber"]
VISIT_HEADERS = ["FamilyNumber", "User", "Date", "كراسة", "كشكول", "قلم رصاص", "استيكة", "مسطرة", "قلم جاف", "براية", "ارنب", "بطة", "كلب"]
PRODUCT_HEADERS = ["Name", "Price", "Quantity"]

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS and USERS[username] == password:
            session['username'] = username
            return redirect(url_for('home'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    return render_template('login.html')

@app.route('/home', methods=['GET', 'POST'])
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    families = []
    if request.method == 'POST':
        if 'name_number_search' in request.form:
            query = request.form['name_number'].strip()
            if query:
                families = [row for row in families_sheet.get_all_records() 
                           if query.lower() in row['Name'].lower() or query == str(row['FamilyNumber'])]
        elif 'mobile_id_search' in request.form:
            query = request.form['mobile_id'].strip()
            if query:
                families = [row for row in families_sheet.get_all_records() 
                           if query == row['MobileNumber'] or query == row['NationalID']]
    
    return render_template('home.html', families=families, username=session['username'])

@app.route('/visit/<int:family_number>', methods=['GET', 'POST'])
def visit(family_number):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    family = next((row for row in families_sheet.get_all_records() 
                   if row['FamilyNumber'] == family_number), None)
    if not family:
        flash('العائلة غير موجودة', 'danger')
        return redirect(url_for('home'))
    
    products = products_sheet.get_all_records()
    product_columns = VISIT_HEADERS[3:]  # Skip FamilyNumber, User, Date
    
    if request.method == 'POST':
        row = [str(family_number), session['username'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        total_price = 0
        
        for col in product_columns:
            qty = request.form.get(col, '0')
            try:
                qty = int(qty)
                if qty < 0:
                    raise ValueError
                product = next((p for p in products if p['Name'] == col), None)
                if product:
                    total_price += qty * float(product['Price'])
                    # Update product quantity
                    product['Quantity'] = str(int(product.get('Quantity', 0)) - qty)
                    cell = products_sheet.find(product['Name'], in_column=1)
                    products_sheet.update_cell(cell.row, 3, product['Quantity'])
            except ValueError:
                flash(f'الكمية لـ {col} يجب أن تكون رقمًا صحيحًا غير سالب.', 'danger')
                return render_template('visit.html', family=family, products=products)
            row.append(str(qty))
        
        visits_sheet.append_row(row)
        flash(f'تم تسجيل الزيارة بنجاح! الإجمالي: {total_price:.2f} جنيه', 'success')
        return redirect(url_for('home'))
    
    return render_template('visit.html', family=family, products=products)

@app.route('/add_family', methods=['GET', 'POST'])
def add_family():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name'].strip()
        national_id = request.form['national_id'].strip()
        mobile_number = request.form['mobile_number'].strip()
        
        if not (name and national_id and mobile_number):
            flash('جميع الحقول مطلوبة', 'danger')
            return render_template('add_family.html')
        
        # Generate new FamilyNumber
        existing_numbers = [row['FamilyNumber'] for row in families_sheet.get_all_records()]
        new_number = max(existing_numbers, default=0) + 1
        
        # Append to Families sheet
        families_sheet.append_row([new_number, name, national_id, mobile_number])
        flash('تم إضافة العائلة بنجاح!', 'success')
        return redirect(url_for('home'))
    
    return render_template('add_family.html')

@app.route('/admin')
def admin():
    if 'username' not in session or session['username'] != 'admin':
        flash('غير مصرح لك بالدخول إلى لوحة التحكم', 'danger')
        return redirect(url_for('login'))
    
    visits = visits_sheet.get_all_records()
    products = products_sheet.get_all_records()
    
    # Calculate user spending
    user_spending = {}
    for visit in visits:
        user = visit['User']
        total = sum(int(visit.get(p['Name'], 0)) * float(p['Price']) for p in products)
        user_spending[user] = user_spending.get(user, 0) + total
    
    return render_template('admin.html', user_spending=user_spending, products=products)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
