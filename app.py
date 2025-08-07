from flask import Flask, render_template, request, redirect, url_for, session, flash
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_secret_key')

# Define users with usernames and passwords
USERS = {
    'karim': '2425',
    'yomna': '3030',
    'admin': 'admin123',
    'user1': '4444',
    'user2': '5555',
    'user4': '9999',
    'user5': '1111'
}

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("creds.json", scopes=scope)
client = gspread.authorize(creds)
spreadsheet = client.open("Resala")

def get_sheet(name, expected_headers=None):
    try:
        ws = spreadsheet.worksheet(name)
        return ws.get_all_records(expected_headers=expected_headers)
    except gspread.exceptions.APIError as e:
        flash(f'خطأ في الوصول إلى ورقة {name}: {str(e)}', 'danger')
        logger.error(f"Error accessing sheet {name}: {str(e)}")
        return []
    except Exception as e:
        flash(f'حدث خطأ غير متوقع: {str(e)}', 'danger')
        logger.error(f"Unexpected error accessing sheet {name}: {str(e)}")
        return []

def calculate_spending(visits, products):
    user_spending = {}
    total_spent = 0
    sold_counts = {}
    product_columns = ['كراسة', 'كشكول', 'قلم رصاص', 'استيكة', 'مسطرة', 'قلم جاف', 'براية', 'ارنب', 'بطة', 'كلب']

    for visit in visits:
        user = visit.get('User', 'Unknown')
        if user not in user_spending:
            user_spending[user] = 0
        for product in products:
            name = product['Name']
            if name in product_columns:
                try:
                    qty = int(visit.get(name, 0))
                    price = float(product.get('Price', 0))
                    user_spending[user] += qty * price
                    total_spent += qty * price
                    sold_counts[name] = sold_counts.get(name, 0) + qty
                except ValueError:
                    logger.warning(f"Invalid quantity or price for product {name} in visit: {visit}")
                    continue

    return user_spending, total_spent, sold_counts

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').lower()
        password = request.form.get('password', '')
        if username in USERS and USERS[username] == password:
            session['username'] = username
            session['is_admin'] = (username == 'admin')
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('home'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح.', 'success')
    return redirect(url_for('login'))

@app.route('/home', methods=['GET', 'POST'])
def home():
    username = session.get('username', 'Unknown')
    is_admin = session.get('is_admin', False)
    families = get_sheet('Families')
    products = get_sheet('Products')

    search_results = []
    if request.method == 'POST':
        search_type = request.form.get('search_type', '')
        keyword = request.form.get('search', '').strip().lower()
        if keyword:
            for family in families:
                if search_type == 'name_number':
                    if (
                        keyword in str(family.get('FamilyNumber', '')).lower() or
                        keyword in str(family.get('Name', '')).lower()
                    ):
                        search_results.append(family)
                elif search_type == 'mobile_id':
                    if (
                        keyword in str(family.get('NationalID', '')).lower() or
                        keyword in str(family.get('MobileNumber', '')).lower()
                    ):
                        search_results.append(family)

    visits = get_sheet('Visits')
    user_spending, total_spent, _ = calculate_spending(visits, products)

    return render_template(
        'home.html',
        families=families,
        products=products,
        search_results=search_results,
        is_admin=is_admin,
        user_spending=user_spending,
        total_spent=total_spent
    )

@app.route('/visit/<int:family_number>', methods=['GET', 'POST'])
def visit(family_number):
    username = session.get('username', 'Unknown')
    products = get_sheet('Products')
    families = get_sheet('Families')

    family = None
    for f in families:
        family_number_value = f.get('FamilyNumber', '')
        try:
            if family_number_value and int(family_number_value) == family_number:
                family = f
                break
        except ValueError:
            logger.warning(f"Invalid FamilyNumber in Families sheet: {family_number_value}")
            continue

    if not family:
        flash(f'الأسرة رقم {family_number} غير موجودة أو تحتوي على بيانات غير صالحة.', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        try:
            product_columns = ['كراسة', 'كشكول', 'قلم رصاص', 'استيكة', 'مسطرة', 'قلم جاف', 'براية', 'ارنب', 'بطة', 'كلب']
            row = [str(family_number), username, datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
            for col in product_columns:
                qty = request.form.get(col, '0')
                try:
                    qty = int(qty)
                    if qty < 0:
                        raise ValueError
                except ValueError:
                    flash(f'الكمية لـ {col} يجب أن تكون رقمًا صحيحًا غير سالب.', 'danger')
                    return render_template('visit.html', family=family, products=products)
                row.append(str(qty))
            spreadsheet.worksheet('Visits').append_row(row)
            flash('تم تسجيل الزيارة بنجاح!', 'success')
            return redirect(url_for('home'))
        except gspread.exceptions.APIError as e:
            flash(f'خطأ في تسجيل الزيارة: {str(e)}', 'danger')
            logger.error(f"Error recording visit for family {family_number}: {str(e)}")
    return render_template('visit.html', family=family, products=products)

@app.route('/admin')
def admin():
    if not session.get('is_admin', False):
        flash('يجب أن تكون مسؤولًا للوصول إلى لوحة التحكم.', 'danger')
        return redirect(url_for('home'))

    products = get_sheet('Products')
    visits = get_sheet('Visits')

    user_spending, total_spent, sold_counts = calculate_spending(visits, products)

    product_availability = []
    for product in products:
        name = product['Name']
        total_qty = int(product.get('Quantity', 0))
        sold = sold_counts.get(name, 0)
        available = total_qty - sold
        product_availability.append({
            'name': name,
            'available': available,
        })

    return render_template('admin.html',
                           user_spending=user_spending,
                           total_spent=total_spent,
                           product_availability=product_availability)

@app.route('/add_family', methods=['GET', 'POST'])
def add_family():
    username = session.get('username')
    if not username:
        flash('يجب تسجيل الدخول لإضافة أسرة.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('Name')
        mobile = request.form.get('Mobile')
        national_id = request.form.get('NationalID')
        
        if not name:
            flash('الاسم مطلوب.', 'danger')
            return render_template('add_family.html')
        
        try:
            # Get all FamilyNumber values from Families sheet
            records = get_sheet('Families')
            family_numbers = []
            for record in records:
                try:
                    family_number = int(record.get('FamilyNumber', 0))
                    family_numbers.append(family_number)
                except (ValueError, TypeError):
                    continue
            # Generate new FamilyNumber (max + 1, or 1 if none exist)
            new_family_number = max(family_numbers, default=0) + 1
            
            # Append new family to Families sheet
            new_row = [str(new_family_number), name, national_id, mobile]
            spreadsheet.worksheet("Families").append_row(new_row)
            flash(f'تمت إضافة أسرة جديدة برقم {new_family_number}', 'success')
            return redirect(url_for('home'))
        except gspread.exceptions.APIError as e:
            flash(f'خطأ في إضافة الأسرة: {str(e)}', 'danger')
            logger.error(f"Error adding family: {str(e)}")
            return render_template('add_family.html')
    return render_template('add_family.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
