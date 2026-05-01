from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from cloudinary_helper import upload_image as cloud_upload, delete_image as cloud_delete
import random
import time
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests
import shutil
from firestore_db import (
    db, get_firestore_client, initialize_firestore,
    get_user_by_username, get_user_by_id, get_user_by_email, get_user_by_email_and_role,
    create_user, update_user,
    get_products, get_product_by_id, create_product, update_product, delete_product,
    get_cart_items, add_to_cart as firestore_add_to_cart, update_cart_quantity as firestore_update_cart_quantity,
    remove_from_cart as firestore_remove_from_cart, clear_cart,
    create_order, get_order_by_id, get_orders, update_order,
    create_notification, get_notifications, mark_notification_read,
    users_ref, products_ref, orders_ref, cart_ref, notifications_ref, messages_ref,
    seller_applications_ref, rider_applications_ref, reviews_ref, product_images_ref
)
from firestore_helpers import (
    get_top_products, get_order_status_breakdown, get_order_status_summary,
    get_sales_chart_data, get_dashboard_summary
)
from google.cloud import firestore as firestore_module
from google.cloud.firestore import SERVER_TIMESTAMP
from checkout_routes import register_checkout_routes

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.secret_key = 'your_secret_key_here'

# ── Jinja2 helper: render image URL whether it's a Cloudinary URL or legacy filename ──
def _img(path, folder='products'):
    """Return a usable image src from either a full URL or a legacy filename."""
    if not path:
        return ''
    if str(path).startswith('http'):
        return path  # Already a full Cloudinary/external URL
    return f"/static/uploads/{folder}/{path}"  # Legacy local file

app.jinja_env.globals['img'] = _img  

# Uploads config
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024  # 4 MB limit
PRODUCTS_UPLOAD_SUBDIR = os.path.join('static', 'uploads', 'products')
DOCUMENTS_UPLOAD_SUBDIR = os.path.join('static', 'uploads', 'documents')

# Hardcoded admin credentials
ADMIN_CREDENTIALS = {
    'username': 'admin',
    'password': generate_password_hash('admin123')
}

# REMOVED: MySQL is no longer used - all data is in Firestore
# All database operations now use firestore_db.py functions


def format_public_order_id(order_id: int) -> str:
    """Return a 7-digit public order ID derived from the internal order id.

    This keeps the same internal id for lookups, but shows a friendlier,
    less predictable 7-digit value in the UI and notifications.
    """
    try:
        n = int(order_id)
    except (TypeError, ValueError):
        return str(order_id)

    MOD = 10_000_000  # 7 digits
    MULT = 7_393_913  # odd, not divisible by 5 -> coprime with MOD
    public_num = (n * MULT) % MOD
    return f"{public_num:07d}"


@app.template_filter('public_order_id')
def public_order_id_filter(order_id):
    return format_public_order_id(order_id)

# Role required decorator
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session or session.get('role') != role:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('login_page'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def ensure_upload_folder():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(PRODUCTS_UPLOAD_SUBDIR, exist_ok=True)
    os.makedirs(DOCUMENTS_UPLOAD_SUBDIR, exist_ok=True)

def allowed_file(filename):
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed

def init_database():
    """Initialize Firestore database"""
    initialize_firestore()
    print("Firestore initialized successfully!")

def send_email(to_email: str, subject: str, body: str):
    """Send an email using SendGrid if configured, otherwise SMTP.

    Priority:
    1. SENDGRID_API_KEY (+ SENDGRID_FROM/SMTP_FROM/SMTP_USER) via HTTP API
    2. SMTP_* environment variables
    3. Fallback: log email contents to the console
    """
    # --- Try SendGrid first ---
    sg_api_key = os.environ.get('SENDGRID_API_KEY')
    sg_from = os.environ.get('SENDGRID_FROM') or os.environ.get('SMTP_FROM') or os.environ.get('SMTP_USER')

    if sg_api_key and sg_from:
        try:
            payload = {
                "personalizations": [
                    {"to": [{"email": to_email}]}
                ],
                "from": {"email": sg_from},
                "subject": subject,
                "content": [
                    {"type": "text/plain", "value": body}
                ],
            }
            headers = {
                "Authorization": f"Bearer {sg_api_key}",
                "Content-Type": "application/json",
            }
            resp = requests.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers, timeout=10)
            if resp.status_code in (200, 202):
                print(f"[EMAIL sent via SendGrid] To: {to_email} | Subject: {subject}")
                return
            else:
                print(f"Error sending email via SendGrid: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Exception while sending email via SendGrid: {e}")

    # --- Fallback to SMTP ---
    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    from_email = os.environ.get('SMTP_FROM') or smtp_user

    if not smtp_host or not smtp_user or not smtp_password or not from_email:
        print(f"[EMAIL fallback] To: {to_email} | Subject: {subject}\n{body}")
        return

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        print(f"[EMAIL sent via SMTP] To: {to_email} | Subject: {subject}")
    except Exception as e:
        print(f"Error sending email via SMTP: {e}")
        print(f"[EMAIL fallback] To: {to_email} | Subject: {subject}\n{body}")

def get_stock_alerts():
    """Get low stock and out-of-stock alerts"""
    low_stock_threshold = 10
    
    all_products = get_products()
    out_of_stock_products = [p for p in all_products if p.get('stock_quantity', 0) == 0 and p.get('is_active', True)]
    low_stock_products = [p for p in all_products if 0 < p.get('stock_quantity', 0) <= low_stock_threshold and p.get('is_active', True)]
    
    return {
        'out_of_stock': out_of_stock_products,
        'low_stock': low_stock_products,
        'total_alerts': len(out_of_stock_products) + len(low_stock_products)
    }

def get_customer_communication_data():
    """Get customer reviews, messages, and support tickets data - Firestore version"""
    # TODO: Implement when reviews and support tickets are migrated
    return {
        'pending_reviews': [],
        'unread_messages': [],
        'open_tickets': [],
        'total_pending_reviews': 0,
        'total_unread_messages': 0,
        'total_open_tickets': 0
    }

def get_financial_health_data():
    """Get financial health data including balance and payout info"""
    # TODO: Implement wallet in Firestore
    next_payout = datetime.utcnow() + timedelta(days=15)
    
    return {
        'available_balance': 0.0,
        'pending_payouts': 0.0,
        'min_withdraw': 500.0,
        'next_payout_date': next_payout,
        'eligible_for_payout': False
    }

# ============================================================================
# ROUTES
# ============================================================================

@app.before_request
def init_folders():
    """Ensure upload folders exist"""
    ensure_upload_folder()

@app.route('/')
def guest_home():
    if 'username' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin'))
        elif role == 'seller':
            return redirect(url_for('shomepage'))
        elif role == 'rider':
            return redirect(url_for('rider_homepage'))
        return redirect(url_for('homepage'))

    # Fetch all products from Firestore
    products = []
    best_sellers = []
    new_arrivals = []
    best_deals = []
    
    try:
        from firestore_db import products_v2_ref, product_variations_ref
        
        # Fetch V2 products (same as user homepage)
        all_v2_products = products_v2_ref.stream()
        
        products_list = []
        for prod_doc in all_v2_products:
            prod_data = prod_doc.to_dict()
            
            # Get seller info and check if approved
            seller = get_user_by_username(prod_data.get('seller_username', ''))
            if not seller or not seller.get('seller_approved', False):
                continue
            
            store_name = seller.get('store_name', '') if seller else ''
            
            if prod_data.get('has_variations'):
                # Get all variations for this product
                variations_query = product_variations_ref.where('parent_product_id', '==', prod_doc.id).stream()
                variations_list = []
                total_stock = 0
                for var_doc in variations_query:
                    var_data = var_doc.to_dict()
                    variations_list.append({
                        'id': var_doc.id,
                        'name': var_data.get('variation_name', ''),
                        'price': var_data.get('price', 0),
                        'stock': var_data.get('stock', 0),
                        'description': var_data.get('description', ''),
                        'image': var_data.get('image', 'default.jpg')
                    })
                    total_stock += var_data.get('stock', 0)
                
                if variations_list and total_stock > 0:
                    # Use first variation as default
                    first_var = variations_list[0]
                    products_list.append({
                        'id': prod_doc.id,
                        'name': first_var['name'],
                        'price': first_var['price'],
                        'stock': total_stock,
                        'specifications': first_var['description'],
                        'image': first_var['image'],
                        'seller_username': prod_data.get('seller_username', ''),
                        'store_name': store_name,
                        'created_at': prod_data.get('created_at'),
                        'has_variations': True,
                        'variations': variations_list
                    })
            else:
                # Single product
                if prod_data.get('stock', 0) > 0:
                    products_list.append({
                        'id': prod_doc.id,
                        'name': prod_data.get('product_name', ''),
                        'price': prod_data.get('price', 0),
                        'stock': prod_data.get('stock', 0),
                        'specifications': prod_data.get('description', ''),
                        'image': prod_data.get('image', 'default.jpg'),
                        'seller_username': prod_data.get('seller_username', ''),
                        'store_name': store_name,
                        'created_at': prod_data.get('created_at'),
                        'has_variations': False,
                        'variations': []
                    })
        
        # Sort by created_at
        products_list.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        products = products_list
        print(f"Products fetched for guest: {len(products)}")
        
        # New Arrivals: 3 most recently added
        new_arrivals = products[:3] if len(products) >= 3 else products
        
        # Best Deals: 3 cheapest
        sorted_by_price = sorted(products, key=lambda x: x['price'])
        best_deals = sorted_by_price[:3] if len(sorted_by_price) >= 3 else sorted_by_price
        
        # Best Sellers: first 3
        best_sellers = products[:3] if len(products) >= 3 else products
        
    except Exception as e:
        print(f"Error fetching products: {e}")
        import traceback
        traceback.print_exc()
        products = []
        best_sellers = []
        new_arrivals = []
        best_deals = []
    
    return render_template('guest_homepage.html', products=products,
                           best_sellers=best_sellers,
                           new_arrivals=new_arrivals,
                           best_deals=best_deals)

@app.route('/search')
def search_products():
    """Search products by name and category - returns JSON for AJAX"""
    search_query = request.args.get('q', '').strip().lower()
    category = request.args.get('category', '').strip()
    sort = request.args.get('sort', '').strip()
    
    try:
        from firestore_db import products_v2_ref, product_variations_ref
        
        # Get all products from V2
        all_v2_products = products_v2_ref.stream()
        
        products = []
        for prod_doc in all_v2_products:
            prod_data = prod_doc.to_dict()
            seller_username = prod_data.get('seller_username', '')
            
            # Get seller info and check if approved
            seller = get_user_by_username(seller_username)
            if not seller or not seller.get('seller_approved', False):
                continue
            
            store_name = seller.get('store_name', '') if seller else ''
            
            if prod_data.get('has_variations'):
                # Get all variations for this product
                variations_query = product_variations_ref.where('parent_product_id', '==', prod_doc.id).stream()
                variations_list = []
                total_stock = 0
                for var_doc in variations_query:
                    var_data = var_doc.to_dict()
                    variations_list.append({
                        'id': var_doc.id,
                        'name': var_data.get('variation_name', ''),
                        'price': var_data.get('price', 0),
                        'stock': var_data.get('stock', 0),
                        'description': var_data.get('description', ''),
                        'image': var_data.get('image', 'default.jpg')
                    })
                    total_stock += var_data.get('stock', 0)
                
                if variations_list and total_stock > 0:
                    # Use first variation as default
                    first_var = variations_list[0]
                    product_name = first_var['name'].lower()
                    specifications = first_var['description'].lower()
                    
                    # Get stored category fields
                    product_main_category = prod_data.get('main_category', '').lower()
                    product_subcategory = prod_data.get('subcategory', '').lower()
                    
                    # Apply search filter
                    if search_query:
                        if not (search_query in product_name or 
                               search_query in specifications or 
                               search_query in store_name.lower() or 
                               search_query in seller_username.lower()):
                            continue
                    
                    # Apply category filter - check against stored category fields
                    if category:
                        # Handle "category:subcategory" format
                        if ':' in category:
                            main_cat, sub_cat = category.split(':', 1)
                            # Check if both main category and subcategory match the stored fields
                            if not (main_cat.lower() == product_main_category and 
                                   sub_cat.lower() == product_subcategory):
                                continue
                        else:
                            # Just main category - check if it matches the stored main_category
                            if category.lower() != product_main_category:
                                continue
                    
                    products.append({
                        'id': prod_doc.id,
                        'name': first_var['name'],
                        'price': float(first_var['price']),
                        'stock': total_stock,
                        'specifications': first_var['description'],
                        'image': first_var['image'],
                        'seller_username': seller_username,
                        'store_name': store_name,
                        'created_at': prod_data.get('created_at')
                    })
            else:
                # Single product
                stock = prod_data.get('stock', 0)
                if stock > 0:
                    product_name = prod_data.get('product_name', '').lower()
                    specifications = prod_data.get('description', '').lower()
                    
                    # Get stored category fields
                    product_main_category = prod_data.get('main_category', '').lower()
                    product_subcategory = prod_data.get('subcategory', '').lower()
                    
                    # Apply search filter
                    if search_query:
                        if not (search_query in product_name or 
                               search_query in specifications or 
                               search_query in store_name.lower() or 
                               search_query in seller_username.lower()):
                            continue
                    
                    # Apply category filter - check against stored category fields
                    if category:
                        # Handle "category:subcategory" format
                        if ':' in category:
                            main_cat, sub_cat = category.split(':', 1)
                            # Check if both main category and subcategory match the stored fields
                            if not (main_cat.lower() == product_main_category and 
                                   sub_cat.lower() == product_subcategory):
                                continue
                        else:
                            # Just main category - check if it matches the stored main_category
                            if category.lower() != product_main_category:
                                continue
                    
                    products.append({
                        'id': prod_doc.id,
                        'name': prod_data.get('product_name', ''),
                        'price': float(prod_data.get('price', 0)),
                        'stock': stock,
                        'specifications': prod_data.get('description', ''),
                        'image': prod_data.get('image', 'default.jpg'),
                        'seller_username': seller_username,
                        'store_name': store_name,
                        'created_at': prod_data.get('created_at')
                    })
        
        # Apply sorting
        if sort == 'price-asc':
            products.sort(key=lambda x: x['price'])
        elif sort == 'price-desc':
            products.sort(key=lambda x: x['price'], reverse=True)
        elif sort == 'name-asc':
            products.sort(key=lambda x: x['name'].lower())
        elif sort == 'name-desc':
            products.sort(key=lambda x: x['name'].lower(), reverse=True)
        elif sort == 'date-newest':
            products.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        elif sort == 'date-oldest':
            products.sort(key=lambda x: x.get('created_at') or datetime.min)
        else:
            # Default: newest first
            products.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
            # Default: newest first (already in order from Firestore)
            pass
        
        # Search sellers
        sellers = []
        if search_query:
            all_sellers = users_ref.where('role', '==', 'seller').stream()
            for seller_doc in all_sellers:
                seller_data = seller_doc.to_dict()
                username = seller_data.get('username', '').lower()
                store_name = seller_data.get('store_name', '').lower()
                
                if search_query in username or search_query in store_name:
                    sellers.append({
                        'username': seller_data.get('username', ''),
                        'store_name': seller_data.get('store_name', ''),
                        'store_profile': seller_data.get('store_profile', ''),
                        'store_category': seller_data.get('store_category', '')
                    })
                    if len(sellers) >= 8:
                        break
        
        return {
            'success': True,
            'products': products,
            'sellers': sellers,
            'count': len(products),
            'seller_count': len(sellers),
        }, 200
        
    except Exception as e:
        print(f"Error searching products: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'products': [], 'sellers': [], 'error': str(e)}, 500

@app.route('/login_page')
def login_page():
    error = request.args.get('error')
    return render_template('login.html', error=error)

@app.route('/login', methods=['POST'])
def handle_login():
    username = request.form['username']
    password = request.form['password']

    # Check for hardcoded admin
    if username == ADMIN_CREDENTIALS['username'] and check_password_hash(ADMIN_CREDENTIALS['password'], password):
        session['username'] = username
        session['role'] = 'admin'
        return redirect(url_for('admin'))

    # Check Firestore for user
    user = get_user_by_username(username)

    if user:
        # Check if password field is empty or None
        if not user.get('password'):
            return redirect(url_for('login_page', error='invalid'))
        
        if check_password_hash(user['password'], password) or user['password'] == password:
            # Check if account is deleted
            account_status = user.get('account_status', 'active')
            if account_status == 'deleted':
                delete_reason = user.get('delete_reason', 'inactive')
                return redirect(url_for('login_page', error=f'deleted_{delete_reason}'))

            # Check if account is banned
            if account_status == 'banned':
                ban_until = user.get('ban_until')
                ban_count = user.get('ban_count', 1)
                if ban_count >= 3:
                    return redirect(url_for('login_page', error='banned_permanent'))
                if ban_until:
                    from datetime import datetime as _dt
                    try:
                        ban_until_dt = ban_until if hasattr(ban_until, 'timestamp') else None
                        if ban_until_dt:
                            now_utc = _dt.utcnow()
                            ban_until_naive = ban_until_dt.replace(tzinfo=None)
                            if now_utc < ban_until_naive:
                                ban_days = (ban_until_naive - now_utc).days + 1
                                return redirect(url_for('login_page', error=f'banned_temp_{ban_days}'))
                            else:
                                # Ban expired — lift it
                                db.collection('users').document(username).update({'account_status': 'active', 'ban_until': None})
                        else:
                            return redirect(url_for('login_page', error='banned_temp_1'))
                    except Exception:
                        return redirect(url_for('login_page', error='banned_temp_1'))

            # Successful login
            session['username'] = username
            session['role'] = user['role']
            session['profile_picture'] = user.get('profile_picture')
            session['store_profile'] = user.get('store_profile')
            session['user_id'] = user['id']
            session.pop('_flashes', None)

            print(f"✅ User logged in: {username} (Role: {user['role']})")

            if user['role'] == 'rider':
                return redirect(url_for('login_page', error='rider_disabled'))
            if user['role'] == 'seller':
                return redirect(url_for('seller_dashboard'))
            else:
                return redirect(url_for('homepage'))
        else:
            return redirect(url_for('login_page', error='invalid'))
    else:
        return redirect(url_for('login_page', error='notfound'))


@app.route('/forgot-password', methods=['POST'])
def forgot_password_request():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()

    if not username:
        return jsonify({'success': False, 'message': 'Username is required.'}), 400

    try:
        # Look up user by username
        user = get_user_by_username(username)
        
        if not user:
            return jsonify({'success': False, 'message': 'No account found for that username.'}), 404

        user_id = user['id']
        user_email = user.get('email', '')

        # Generate 6-digit OTP
        otp = f"{random.randint(100000, 999999)}"
        expires_at = time.time() + 300  # 5 minutes

        session['password_reset'] = {
            'user_id': user_id,
            'email': user_email,
            'otp': otp,
            'expires_at': expires_at,
        }

        subject = "Verdant Password Reset Code"
        body = f"Your Verdant password reset code is: {otp}. This code will expire in 5 minutes."
        send_email(user_email, subject, body)

        return jsonify({'success': True, 'message': 'A verification code has been sent to the email on file for this username.'})

    except Exception as e:
        print(f"Error in forgot_password_request: {e}")
        return jsonify({'success': False, 'message': 'Failed to send verification code.'}), 500


@app.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    new_password = data.get('new_password') or ''

    payload = session.get('password_reset')
    if not payload:
        return jsonify({'success': False, 'message': 'No password reset request in progress.'}), 400

    if not code:
        return jsonify({'success': False, 'message': 'Verification code is required.'}), 400

    if not new_password:
        return jsonify({'success': False, 'message': 'New password is required.'}), 400

    # Check expiry
    if time.time() > payload.get('expires_at', 0):
        session.pop('password_reset', None)
        return jsonify({'success': False, 'message': 'Verification code has expired. Please request a new one.'}), 400

    # Check code
    if code != payload.get('otp'):
        return jsonify({'success': False, 'message': 'Invalid verification code.'}), 400

    user_id = payload.get('user_id')
    if not user_id:
        session.pop('password_reset', None)
        return jsonify({'success': False, 'message': 'Invalid reset session.'}), 400

    try:
        hashed = generate_password_hash(new_password)
        
        # Update password in Firestore
        users_ref.document(user_id).update({
            'password': hashed,
            'updated_at': firestore_module.SERVER_TIMESTAMP
        })

        session.pop('password_reset', None)

        return jsonify({'success': True, 'message': 'Your password has been updated. You can now log in with the new password.'})
    except Exception as e:
        print(f"Error in reset_password: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to update password.'}), 500

@app.route('/signup', methods=['POST'])
def handle_signup():
    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        username = request.form['username']
        email = request.form['email']
        phone = request.form.get('phone')
        password = generate_password_hash(request.form['password'])

        print(f"🔍 Attempting to create user: {username} with email: {email}")

        # Check if username already exists in Firestore
        existing_user = get_user_by_username(username)
        if existing_user:
            print(f"❌ Username '{username}' already exists")
            if is_ajax:
                return jsonify({
                    'success': False,
                    'field': 'username',
                    'message': 'This username is already taken. Please choose another one.'
                }), 400
            return redirect(url_for('login_page', error='username_exists'))
        
        # Check if email already exists FOR THE SAME ROLE (user)
        existing_email = get_user_by_email_and_role(email, 'user')
        if existing_email:
            print(f"❌ Email '{email}' already exists for role 'user' (username: {existing_email.get('username')})")
            if is_ajax:
                return jsonify({
                    'success': False,
                    'field': 'email',
                    'message': 'An account with this email already exists. Please login or use a different email.'
                }), 400
            return redirect(url_for('login_page', error='email_exists_user'))
        
        # Create user in Firestore with minimal info - account is unverified
        user_data = {
            'username': username,
            'email': email,
            'phone': phone,
            'password': password,
            'role': 'user',
            'is_active': True,
            'is_verified': False,  # New field to track verification status
            'country': 'Philippines'
        }
        
        print(f"📝 Creating user with data: {list(user_data.keys())}")
        user_id = create_user(user_data)
        print(f"✅ New unverified user created in Firestore: {username} (ID: {user_id})")

        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Account created successfully! Redirecting to login...',
                'redirect': url_for('login_page', signup='user')
            }), 200
        
        # Redirect back to login with signup flag for success notification
        return redirect(url_for('login_page', signup='user'))
        
    except Exception as e:
        print(f"❌ Error during signup: {str(e)}")
        import traceback
        traceback.print_exc()
        
        if is_ajax:
            return jsonify({
                'success': False,
                'message': f'Error creating account: {str(e)}'
            }), 500
        return redirect(url_for('login_page', error='signup_failed'))

@app.route('/register_rider', methods=['POST'])
def register_rider():
    """Register a new rider account with basic info. Detailed docs go into rider_applications."""
    try:
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        username = request.form['rider_username']
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form['email']
        date_of_birth = request.form.get('date_of_birth')
        gender = request.form.get('gender')
        address = request.form.get('address', '')
        city = request.form.get('city', '')
        state_province = request.form.get('state_province', '')
        postal_code = request.form.get('postal_code', '')
        country = request.form.get('country', 'Philippines')
        phone = request.form.get('phone')
        alternate_phone = request.form.get('alternate_phone')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        vehicle_type = request.form.get('vehicle_type')
        vehicle_registration = request.form.get('vehicle_registration')
        license_number = request.form.get('license_number')
        password = generate_password_hash(request.form['password'])

        # Check if username already exists
        existing_user = get_user_by_username(username)
        if existing_user:
            if is_ajax:
                return jsonify({
                    'success': False,
                    'field': 'username',
                    'message': 'This username is already taken. Please choose another one.'
                }), 400
            return redirect(url_for('login_page', error='username_exists'))
        
        # Check if email already exists FOR THE SAME ROLE (rider)
        existing_email = get_user_by_email_and_role(email, 'rider')
        if existing_email:
            if is_ajax:
                return jsonify({
                    'success': False,
                    'field': 'email',
                    'message': 'A rider account with this email already exists. Please login or use a different email.'
                }), 400
            return redirect(url_for('login_page', error='email_exists_rider'))

        # Handle license image upload
        license_image_filename = None
        file = request.files.get('license_image')
        if file and file.filename:
            license_image_filename = cloud_upload(file, 'verdant/documents')

        # Create rider user in Firestore
        user_data = {
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'date_of_birth': date_of_birth,
            'gender': gender,
            'address': address,
            'city': city,
            'state_province': state_province,
            'postal_code': postal_code,
            'country': country,
            'phone': phone,
            'alternate_phone': alternate_phone,
            'latitude': float(latitude) if latitude else None,
            'longitude': float(longitude) if longitude else None,
            'vehicle_type': vehicle_type,
            'license_number': license_number,
            'password': password,
            'role': 'rider',
            'is_active': True,
            'is_approved': False
        }
        
        rider_user_id = create_user(user_data)

        # Create rider application for admin review
        full_name = f"{first_name or ''} {last_name or ''}".strip() or username
        rider_applications_ref.add({
            'username': username,
            'full_name': full_name,
            'address': address,
            'phone': phone,
            'email': email,
            'vehicle_type': vehicle_type or '',
            'vehicle_registration': vehicle_registration or '',
            'license_number': license_number or '',
            'license_image': license_image_filename,
            'status': 'pending',
            'created_at': firestore_module.SERVER_TIMESTAMP,
            'updated_at': firestore_module.SERVER_TIMESTAMP
        })

        print(f"✅ New rider created in Firestore: {username} (ID: {rider_user_id})")
        
        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Rider account created successfully! Redirecting to login...',
                'redirect': url_for('login_page', signup='rider')
            }), 200
        
        return redirect(url_for('login_page', signup='rider'))
    
    except Exception as e:
        print(f"❌ Error registering rider: {e}")
        import traceback
        traceback.print_exc()
        if is_ajax:
            return jsonify({
                'success': False,
                'field': 'general',
                'message': 'An error occurred during registration. Please try again.'
            }), 500
        return redirect(url_for('login_page', error='registration_failed', signup='rider'))

@app.route('/register_seller', methods=['POST'])
def register_seller():
    try:
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        username = request.form['seller_username']
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form['email']
        date_of_birth = request.form.get('date_of_birth')
        gender = request.form.get('gender')
        address = request.form.get('address', '')
        city = request.form.get('city', '')
        state_province = request.form.get('state_province', '')
        postal_code = request.form.get('postal_code', '')
        country = request.form.get('country', 'Philippines')
        phone = request.form.get('phone')
        alternate_phone = request.form.get('alternate_phone')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        password = generate_password_hash(request.form['password'])

        print(f"🔍 Attempting to register seller: {username}")

        # Check if username already exists
        existing_user = get_user_by_username(username)
        if existing_user:
            print(f"❌ Username already exists: {username}")
            if is_ajax:
                return jsonify({
                    'success': False,
                    'field': 'username',
                    'message': 'This username is already taken. Please choose another one.'
                }), 400
            return redirect(url_for('login_page', error='username_exists', signup='seller'))
        
        # Check if email already exists FOR THE SAME ROLE (seller)
        existing_email = get_user_by_email_and_role(email, 'seller')
        if existing_email:
            print(f"❌ Email already exists for seller role: {email}")
            if is_ajax:
                return jsonify({
                    'success': False,
                    'field': 'email',
                    'message': 'A seller account with this email already exists. Please login or use a different email.'
                }), 400
            return redirect(url_for('login_page', error='email_exists_seller', signup='seller'))
        
        # Create seller user in Firestore
        user_data = {
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'date_of_birth': date_of_birth,
            'gender': gender,
            'address': address,
            'city': city,
            'state_province': state_province,
            'postal_code': postal_code,
            'country': country,
            'phone': phone,
            'alternate_phone': alternate_phone,
            'latitude': float(latitude) if latitude else None,
            'longitude': float(longitude) if longitude else None,
            'password': password,
            'role': 'seller',
            'is_active': True,
            'seller_approved': False,
            'created_at': firestore_module.SERVER_TIMESTAMP,
            'updated_at': firestore_module.SERVER_TIMESTAMP
        }
        
        print(f"📝 Creating seller user in Firestore...")
        seller_user_id = create_user(user_data)
        print(f"✅ Seller created successfully: {username} (ID: {seller_user_id})")
        
        # Verify the user was created
        verify_user = get_user_by_username(username)
        if verify_user:
            print(f"✅ Verification successful: User {username} exists in Firestore")
        else:
            print(f"⚠️ Warning: User {username} not found after creation!")

        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Seller account created successfully! Redirecting to login...',
                'redirect': url_for('login_page', signup='seller')
            }), 200

        # Redirect back to login with signup flag for success notification
        return redirect(url_for('login_page', signup='seller'))
    
    except Exception as e:
        print(f"❌ Error registering seller: {e}")
        import traceback
        traceback.print_exc()
        if is_ajax:
            return jsonify({
                'success': False,
                'field': 'general',
                'message': 'An error occurred during registration. Please try again.'
            }), 500
        return redirect(url_for('login_page', error='registration_failed', signup='seller'))

@app.route('/homepage')
def homepage():
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page'))
    
    # Get user profile picture from Firestore
    user = get_user_by_username(session['username'])
    profile_picture = user.get('profile_picture') if user else None

    products = []
    best_sellers = []
    new_arrivals = []
    best_deals = []

    try:
        from firestore_db import products_v2_ref, product_variations_ref
        
        # Fetch V2 products
        all_v2_products = products_v2_ref.stream()
        
        products_list = []
        for prod_doc in all_v2_products:
            prod_data = prod_doc.to_dict()
            
            # Get seller info and check if approved
            seller = get_user_by_username(prod_data.get('seller_username', ''))
            if not seller or not seller.get('seller_approved', False):
                continue
            
            store_name = seller.get('store_name', '') if seller else ''
            
            if prod_data.get('has_variations'):
                # Get all variations for this product
                variations_query = product_variations_ref.where('parent_product_id', '==', prod_doc.id).stream()
                variations_list = []
                total_stock = 0
                for var_doc in variations_query:
                    var_data = var_doc.to_dict()
                    variations_list.append({
                        'id': var_doc.id,
                        'name': var_data.get('variation_name', ''),
                        'price': var_data.get('price', 0),
                        'stock': var_data.get('stock', 0),
                        'description': var_data.get('description', ''),
                        'image': var_data.get('image', 'default.jpg')
                    })
                    total_stock += var_data.get('stock', 0)
                
                if variations_list and total_stock > 0:
                    # Use first variation as default
                    first_var = variations_list[0]
                    products_list.append({
                        'id': prod_doc.id,
                        'name': first_var['name'],
                        'price': first_var['price'],
                        'stock': total_stock,
                        'specifications': first_var['description'],
                        'image': first_var['image'],
                        'seller_username': prod_data.get('seller_username', ''),
                        'store_name': store_name,
                        'created_at': prod_data.get('created_at'),
                        'has_variations': True,
                        'variations': variations_list
                    })
            else:
                # Single product
                if prod_data.get('stock', 0) > 0:
                    products_list.append({
                        'id': prod_doc.id,
                        'name': prod_data.get('product_name', ''),
                        'price': prod_data.get('price', 0),
                        'stock': prod_data.get('stock', 0),
                        'specifications': prod_data.get('description', ''),
                        'image': prod_data.get('image', 'default.jpg'),
                        'seller_username': prod_data.get('seller_username', ''),
                        'store_name': store_name,
                        'created_at': prod_data.get('created_at'),
                        'has_variations': False,
                        'variations': []
                    })
        
        # Sort by created_at
        products_list.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        products = products_list
        
        # New Arrivals: 3 most recently added
        new_arrivals = products[:3] if len(products) >= 3 else products
        
        # Best Deals: 3 cheapest
        sorted_by_price = sorted(products, key=lambda x: x['price'])
        best_deals = sorted_by_price[:3] if len(sorted_by_price) >= 3 else sorted_by_price
        
        # Best Sellers: first 3
        best_sellers = products[:3] if len(products) >= 3 else products
        
    except Exception as e:
        print(f"Error fetching products: {e}")
        import traceback
        traceback.print_exc()

    return render_template('user_homepage.html',
                           profile_picture=profile_picture,
                           products=products,
                           best_sellers=best_sellers,
                           new_arrivals=new_arrivals,
                           best_deals=best_deals)

@app.route('/add_to_cart/<product_id>', methods=['POST'])
def add_to_cart_route(product_id):
    """Add product to cart"""
    if 'username' not in session or session.get('role') != 'user':
        return {'success': False, 'message': 'Please login to add items to cart'}, 401
    
    try:
        from firestore_db import products_v2_ref, product_variations_ref
        
        # Get user
        user = get_user_by_username(session['username'])
        if not user:
            return {'success': False, 'message': 'User not found'}, 404
        
        user_id = user['id']
        
        # Get variation_id from request body if provided
        data = request.get_json() or {}
        variation_id = data.get('variation_id')
        
        # Check if product exists in V2 collection
        product_doc = products_v2_ref.document(product_id).get()
        
        if not product_doc.exists:
            return {'success': False, 'message': 'Product not found'}, 404
        
        product_data = product_doc.to_dict()
        
        # Check if product has variations
        has_variations = product_data.get('has_variations', False)
        
        if has_variations:
            # For products with variations, variation_id is required
            if not variation_id:
                return {'success': False, 'message': 'Please select a variation from the product page'}, 400
            
            # Get the specific variation
            variation_doc = product_variations_ref.document(variation_id).get()
            if not variation_doc.exists:
                return {'success': False, 'message': 'Variation not found'}, 404
            
            variation_data = variation_doc.to_dict()
            available_stock = variation_data.get('stock', 0)
            
            if available_stock <= 0:
                return {'success': False, 'message': 'This variation is out of stock'}, 400
            
            # Check if this specific variation is already in cart
            existing_cart = list(cart_ref.where('user_id', '==', user_id)
                                .where('product_id', '==', product_id)
                                .where('variation_id', '==', variation_id)
                                .limit(1).stream())
            
            if existing_cart:
                cart_doc = existing_cart[0]
                cart_data = cart_doc.to_dict()
                new_quantity = cart_data.get('quantity', 0) + 1
                
                if new_quantity > available_stock:
                    return {'success': False, 'message': f'Only {available_stock} items available in stock'}, 400
                
                cart_ref.document(cart_doc.id).update({
                    'quantity': new_quantity,
                    'updated_at': firestore_module.SERVER_TIMESTAMP
                })
            else:
                # Add new cart item with variation
                cart_ref.add({
                    'user_id': user_id,
                    'product_id': product_id,
                    'variation_id': variation_id,
                    'quantity': 1,
                    'created_at': firestore_module.SERVER_TIMESTAMP,
                    'updated_at': firestore_module.SERVER_TIMESTAMP
                })
        else:
            # For products without variations, check stock
            available_stock = product_data.get('stock', 0)
            
            if available_stock <= 0:
                return {'success': False, 'message': 'Product out of stock'}, 400
            
            # Check if item already in cart
            existing_cart = list(cart_ref.where('user_id', '==', user_id).where('product_id', '==', product_id).limit(1).stream())
            
            if existing_cart:
                cart_doc = existing_cart[0]
                cart_data = cart_doc.to_dict()
                new_quantity = cart_data.get('quantity', 0) + 1
                
                if new_quantity > available_stock:
                    return {'success': False, 'message': f'Only {available_stock} items available in stock'}, 400
                
                cart_ref.document(cart_doc.id).update({
                    'quantity': new_quantity,
                    'updated_at': firestore_module.SERVER_TIMESTAMP
                })
            else:
                # Add new cart item
                cart_ref.add({
                    'user_id': user_id,
                    'product_id': product_id,
                    'quantity': 1,
                    'created_at': firestore_module.SERVER_TIMESTAMP,
                    'updated_at': firestore_module.SERVER_TIMESTAMP
                })
        
        # Get updated cart count
        cart_items = list(cart_ref.where('user_id', '==', user_id).stream())
        cart_count = sum(item.to_dict().get('quantity', 0) for item in cart_items)
        
        return {'success': True, 'message': 'Item added to cart', 'cart_count': cart_count}, 200
        
    except Exception as e:
        print(f"Error adding to cart: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': 'Error adding item to cart'}, 500

@app.route('/api/product_variations/<product_id>')
def api_product_variations(product_id):
    """Get all variations for a product"""
    try:
        from firestore_db import product_variations_ref
        variations_docs = list(product_variations_ref.where('parent_product_id', '==', product_id).stream())
        variations = []
        for v in variations_docs:
            vd = v.to_dict()
            variations.append({
                'id': v.id,
                'name': vd.get('variation_name') or vd.get('name', ''),
                'price': float(vd.get('price', 0)),
                'stock': vd.get('stock', 0),
            })
        return jsonify({'success': True, 'variations': variations})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/update_cart_variation/<cart_item_id>', methods=['POST'])
def update_cart_variation(cart_item_id):
    """Update the variation of a cart item"""
    if 'username' not in session or session.get('role') != 'user':
        return {'success': False, 'message': 'Please login'}, 401
    try:
        from firestore_db import product_variations_ref
        data = request.get_json() or {}
        new_variation_id = data.get('variation_id')
        if not new_variation_id:
            return {'success': False, 'message': 'No variation specified'}, 400

        user = get_user_by_username(session['username'])
        if not user:
            return {'success': False, 'message': 'User not found'}, 404
        user_id = user['id']

        cart_doc = cart_ref.document(cart_item_id).get()
        if not cart_doc.exists:
            return {'success': False, 'message': 'Cart item not found'}, 404
        if cart_doc.to_dict().get('user_id') != user_id:
            return {'success': False, 'message': 'Unauthorized'}, 403

        # Verify variation exists and has stock
        var_doc = product_variations_ref.document(new_variation_id).get()
        if not var_doc.exists:
            return {'success': False, 'message': 'Variation not found'}, 404
        if var_doc.to_dict().get('stock', 0) <= 0:
            return {'success': False, 'message': 'This variation is out of stock'}, 400

        cart_ref.document(cart_item_id).update({
            'variation_id': new_variation_id,
            'updated_at': firestore_module.SERVER_TIMESTAMP
        })
        return {'success': True, 'message': 'Variation updated'}, 200
    except Exception as e:
        print(f"Error updating cart variation: {e}")
        return {'success': False, 'message': 'Error updating variation'}, 500


@app.route('/get_cart_count')
def get_cart_count():
    """Get current cart item count"""
    if 'username' not in session or session.get('role') != 'user':
        return {'cart_count': 0}, 200
    
    try:
        user = get_user_by_username(session['username'])
        if not user:
            return {'cart_count': 0}, 200
        
        user_id = user['id']
        cart_items = list(cart_ref.where('user_id', '==', user_id).stream())
        cart_count = sum(item.to_dict().get('quantity', 0) for item in cart_items)
        
        return {'cart_count': cart_count}, 200
    except Exception as e:
        print(f"Error getting cart count: {e}")
        return {'cart_count': 0}, 200

@app.route('/update_cart_quantity/<cart_item_id>', methods=['POST'])
def update_cart_quantity_route(cart_item_id):
    """Update quantity of item in cart"""
    if 'username' not in session or session.get('role') != 'user':
        return {'success': False, 'message': 'Please login'}, 401
    
    data = request.get_json()
    new_quantity = data.get('quantity', 1)
    
    if new_quantity < 1:
        return {'success': False, 'message': 'Quantity must be at least 1'}, 400
    
    try:
        user = get_user_by_username(session['username'])
        if not user:
            return {'success': False, 'message': 'User not found'}, 404
        
        user_id = user['id']
        
        # Get cart item
        cart_doc = cart_ref.document(cart_item_id).get()
        if not cart_doc.exists:
            return {'success': False, 'message': 'Cart item not found'}, 404
        
        cart_data = cart_doc.to_dict()
        if cart_data.get('user_id') != user_id:
            return {'success': False, 'message': 'Unauthorized'}, 403
        
        # Check product stock — check both v2 and variations
        product_id = cart_data.get('product_id')
        variation_id = cart_data.get('variation_id')

        from firestore_db import products_v2_ref, product_variations_ref as pv_ref
        if variation_id:
            var_doc = pv_ref.document(variation_id).get()
            if not var_doc.exists:
                return {'success': False, 'message': 'Variation not found'}, 404
            stock = var_doc.to_dict().get('stock', 0)
        else:
            prod_doc = products_v2_ref.document(product_id).get()
            if not prod_doc.exists:
                # fallback to old collection
                product = get_product_by_id(product_id)
                stock = product.get('stock', 0) if product else 0
            else:
                stock = prod_doc.to_dict().get('stock', 0)

        if new_quantity > stock:
            return {'success': False, 'message': f'Only {stock} items available in stock'}, 400
        
        # Update quantity
        cart_ref.document(cart_item_id).update({
            'quantity': new_quantity,
            'updated_at': firestore_module.SERVER_TIMESTAMP
        })
        
        # Get updated cart count
        cart_items = list(cart_ref.where('user_id', '==', user_id).stream())
        cart_count = sum(item.to_dict().get('quantity', 0) for item in cart_items)
        
        return {'success': True, 'message': 'Quantity updated', 'cart_count': cart_count}, 200
        
    except Exception as e:
        print(f"Error updating cart quantity: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': 'Error updating quantity'}, 500

@app.route('/remove_from_cart/<cart_item_id>', methods=['POST'])
def remove_from_cart_route(cart_item_id):
    """Remove item from cart"""
    if 'username' not in session or session.get('role') != 'user':
        return {'success': False, 'message': 'Please login'}, 401
    
    try:
        user = get_user_by_username(session['username'])
        if not user:
            return {'success': False, 'message': 'User not found'}, 404
        
        user_id = user['id']
        
        # Get cart item to verify ownership
        cart_doc = cart_ref.document(cart_item_id).get()
        if not cart_doc.exists:
            return {'success': False, 'message': 'Cart item not found'}, 404
        
        cart_data = cart_doc.to_dict()
        if cart_data.get('user_id') != user_id:
            return {'success': False, 'message': 'Unauthorized'}, 403
        
        # Delete cart item
        cart_ref.document(cart_item_id).delete()
        
        # Get updated cart count
        cart_items = list(cart_ref.where('user_id', '==', user_id).stream())
        cart_count = sum(item.to_dict().get('quantity', 0) for item in cart_items)
        
        return {'success': True, 'message': 'Item removed from cart', 'cart_count': cart_count}, 200
        
    except Exception as e:
        print(f"Error removing from cart: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': 'Error removing item'}, 500

@app.route('/cart')
def cart():
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page'))
    
    try:
        from firestore_db import products_v2_ref, product_variations_ref
        
        # Get user
        user = get_user_by_username(session['username'])
        if not user:
            return redirect(url_for('login_page'))
        
        user_id = user['id']
        profile_picture = user.get('profile_picture')
        shipping_address = user.get('address', '')
        
        # Fetch cart items
        cart_items_docs = list(cart_ref.where('user_id', '==', user_id).stream())
        
        cart_items = []
        total = 0
        for cart_doc in cart_items_docs:
            cart_data = cart_doc.to_dict()
            product_id = cart_data.get('product_id')
            variation_id = cart_data.get('variation_id')
            quantity = cart_data.get('quantity', 0)
            
            # Get product details from V2 collection
            product_doc = products_v2_ref.document(product_id).get()
            if not product_doc.exists:
                continue
            
            product_data = product_doc.to_dict()
            
            # If cart item has a variation, get variation details
            variation_data = {}
            if variation_id:
                variation_doc = product_variations_ref.document(variation_id).get()
                if not variation_doc.exists:
                    continue
                
                variation_data = variation_doc.to_dict()
                price = float(variation_data.get('price', 0))
                stock = variation_data.get('stock', 0)
                var_name = variation_data.get('variation_name') or variation_data.get('name', '')
                parent_name = product_data.get('product_name', '')
                # Show only the variation name in the cart
                name = var_name if var_name else parent_name
                image = variation_data.get('image', product_data.get('image', 'default.jpg'))
                seller_username = product_data.get('seller_username', '')
                all_variations_docs = list(product_variations_ref.where('parent_product_id', '==', product_id).stream())
                all_variations = [{'id': v.id, 'name': v.to_dict().get('variation_name') or v.to_dict().get('name', ''), 'price': float(v.to_dict().get('price', 0)), 'stock': v.to_dict().get('stock', 0)} for v in all_variations_docs]
            else:
                price = float(product_data.get('price', 0))
                stock = product_data.get('stock', 0)
                name = product_data.get('product_name', product_data.get('name', ''))
                image = product_data.get('image', 'default.jpg')
                seller_username = product_data.get('seller_username', '')
                all_variations = []

            item_total = price * quantity
            total += item_total

            # Safe created_at conversion
            raw_ts = cart_data.get('created_at')
            try:
                created_at = raw_ts.replace(tzinfo=None) if raw_ts else None
            except Exception:
                created_at = None

            cart_items.append({
                'id': cart_doc.id,
                'product_id': product_id,
                'variation_id': variation_id,
                'quantity': quantity,
                'name': name,
                'price': price,
                'image': image,
                'stock': stock,
                'seller_username': seller_username,
                'item_total': item_total,
                'specifications': variation_data.get('variation_name', variation_data.get('name', '')) if variation_id else '',
                'all_variations': all_variations,
                'created_at': created_at,
            })
        
        from datetime import datetime as dt, timedelta as td
        now_dt = dt.now()
        yesterday_dt = now_dt - td(days=1)
        today_str = now_dt.strftime('%Y-%m-%d')
        yesterday_str = yesterday_dt.strftime('%Y-%m-%d')

        return render_template('cart.html', profile_picture=profile_picture, cart_items=cart_items, total=total, shipping_address=shipping_address, today_str=today_str, yesterday_str=yesterday_str)
        
    except Exception as e:
        print(f"Error loading cart: {e}")
        import traceback
        traceback.print_exc()
        return render_template('cart.html', profile_picture=None, cart_items=[], total=0, shipping_address=None)

@app.route('/api/check_pending_orders', methods=['GET'])
def api_check_pending_orders():
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        # Count pending orders for this user
        orders_query = db.collection('orders')\
            .where('username', '==', session['username'])\
            .where('status', 'in', ['pending', 'processing', 'out_for_delivery'])\
            .stream()
        
        pending_count = sum(1 for _ in orders_query)
        
        return jsonify({
            'success': True,
            'has_pending_orders': pending_count > 0,
            'pending_count': pending_count
        })
        
    except Exception as e:
        print(f"Error checking pending orders: {e}")
        return jsonify({'success': False, 'message': 'Error checking orders'}), 500

@app.route('/api/cancel_order', methods=['POST'])
def api_cancel_order():
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        
        if not order_id:
            return jsonify({'success': False, 'message': 'Order ID is required'}), 400
        
        # Check if order exists and belongs to the user (order_id is already a string)
        order_ref = db.collection('orders').document(order_id)
        order_doc = order_ref.get()
        
        if not order_doc.exists:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order_data = order_doc.to_dict()
        
        # Verify order belongs to user
        if order_data.get('username') != session['username']:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        # Check if order can be cancelled (only pending orders can be cancelled)
        if order_data.get('status') != 'pending':
            return jsonify({'success': False, 'message': 'Order can only be cancelled when status is pending'}), 400
        
        # Delete the order
        order_ref.delete()
        
        # Also delete any order items
        items_query = db.collection('order_items').where('order_id', '==', order_id).stream()
        for item_doc in items_query:
            item_doc.reference.delete()
        
        return jsonify({
            'success': True, 
            'message': 'Order cancelled successfully'
        })
        
    except Exception as e:
        print(f"Error cancelling order: {e}")
        return jsonify({'success': False, 'message': 'Error cancelling order'}), 500

@app.route('/api/delete_account', methods=['POST'])
def api_delete_account():
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        # Double-check for pending orders
        orders_query = db.collection('orders')\
            .where('username', '==', session['username'])\
            .where('status', 'in', ['pending', 'processing', 'out_for_delivery'])\
            .stream()
        
        pending_count = sum(1 for _ in orders_query)
        
        if pending_count > 0:
            return jsonify({
                'success': False, 
                'message': 'Cannot delete account with pending orders'
            }), 400
        
        # Delete user's orders history
        orders_query = db.collection('orders').where('username', '==', session['username']).stream()
        for order_doc in orders_query:
            order_doc.reference.delete()
        
        # Delete user's cart items
        cart_query = db.collection('cart').where('username', '==', session['username']).stream()
        for cart_doc in cart_query:
            cart_doc.reference.delete()
        
        # Delete user's messages
        messages_query = db.collection('messages').stream()
        for msg_doc in messages_query:
            msg_data = msg_doc.to_dict()
            if msg_data.get('sender_username') == session['username'] or msg_data.get('receiver_username') == session['username']:
                msg_doc.reference.delete()
        
        # Delete the user
        db.collection('users').document(session['username']).delete()
        
        return jsonify({
            'success': True, 
            'message': 'Account deleted successfully'
        })
        
    except Exception as e:
        print(f"Error deleting account: {e}")
        return jsonify({'success': False, 'message': 'Error deleting account'}), 500

@app.route('/api/verify_current_password', methods=['POST'])
def api_verify_current_password():
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    current_password = data.get('current_password', '')
    
    if not current_password:
        return jsonify({'success': False, 'message': 'Current password is required'}), 400
    
    try:
        user = get_user_by_username(session['username'])
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        stored_password = user.get('password', '')
        
        # Verify password using check_password_hash
        if check_password_hash(stored_password, current_password):
            return jsonify({'success': True, 'message': 'Password verified'})
        else:
            return jsonify({'success': False, 'message': 'Incorrect password'})
            
    except Exception as e:
        print(f"Error verifying password: {e}")
        return jsonify({'success': False, 'message': 'Error verifying password'}), 500

@app.route('/api/get-user-email', methods=['GET'])
def api_get_user_email():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        user = get_user_by_username(session['username'])
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({'success': True, 'email': user.get('email', '')})
    except Exception as e:
        print(f"Error fetching user email: {e}")
        return jsonify({'success': False, 'message': 'Error fetching email'}), 500

@app.route('/api/verify-account', methods=['POST'])
def api_verify_account():
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        middle_initial = request.form.get('middle_initial', '').strip()
        date_of_birth = request.form.get('date_of_birth', '').strip()
        gender = request.form.get('gender', '').strip()
        email_code = request.form.get('email_code', '').strip()
        
        # Validate required fields
        if not all([first_name, last_name, date_of_birth, gender]):
            return jsonify({'success': False, 'message': 'Please fill in all required fields'}), 400
        
        # TODO: Validate email verification code when implemented
        # For now, we'll skip email verification
        
        # Get user document
        user = get_user_by_username(session['username'])
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Check if user already has a pending application
        existing_app = list(db.collection('user_applications')
                          .where('user_id', '==', user['id'])
                          .where('status', '==', 'pending')
                          .limit(1).stream())
        
        if existing_app:
            return jsonify({'success': False, 'message': 'You already have a pending application'}), 400
        
        # Create user application document
        application_data = {
            'user_id': user['id'],
            'username': session['username'],
            'email': user.get('email', ''),
            'phone': user.get('phone', ''),
            'first_name': first_name,
            'last_name': last_name,
            'date_of_birth': date_of_birth,
            'gender': gender,
            'status': 'pending',
            'submitted_at': firestore_module.SERVER_TIMESTAMP
        }
        
        # Only add middle_initial if provided
        if middle_initial:
            application_data['middle_initial'] = middle_initial
        
        db.collection('user_applications').add(application_data)
        
        # Update user to mark as verified but not approved
        user_ref = db.collection('users').document(user['id'])
        update_data = {
            'first_name': first_name,
            'last_name': last_name,
            'date_of_birth': date_of_birth,
            'gender': gender,
            'is_verified': True,
            'is_approved': False
        }
        
        if middle_initial:
            update_data['middle_initial'] = middle_initial
        
        user_ref.update(update_data)
        
        print(f"✅ User {session['username']} submitted verification application")
        
        return jsonify({'success': True, 'message': 'Application submitted! Please wait for admin approval.'}), 200
        
    except Exception as e:
        print(f"Error verifying account: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Error verifying account'}), 500

@app.route('/api/update_location', methods=['POST'])
def update_location():
    """Update user's or rider's location coordinates"""
    if 'username' not in session or session.get('role') not in ('user', 'rider'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if latitude is None or longitude is None:
            return jsonify({'success': False, 'message': 'Latitude and longitude are required'}), 400
        
        # Reverse geocoding to get place name
        address = f"Location updated at {latitude:.4f}, {longitude:.4f}"
        try:
            import requests
            geocoding_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&zoom=18&addressdetails=1"
            headers = {'User-Agent': 'HomeGardenEcommerce/1.0'}
            response = requests.get(geocoding_url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                geocoding_data = response.json()
                if geocoding_data and 'display_name' in geocoding_data:
                    address = geocoding_data['display_name']
        except Exception as geo_error:
            print(f"Geocoding error: {geo_error}")
        
        # Update user's location in Firestore
        user = get_user_by_username(session['username'])
        if user:
            users_ref.document(user['id']).update({
                'latitude': float(latitude),
                'longitude': float(longitude),
                'address': address,
                'updated_at': firestore_module.SERVER_TIMESTAMP
            })
        
        return jsonify({
            'success': True, 
            'message': 'Location updated successfully',
            'address': address
        })
        
    except Exception as e:
        print(f"Error updating location: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to update location'}), 500

@app.route('/rider/profile')
def rider_profile():
    if 'username' not in session or session.get('role') != 'rider':
        return redirect(url_for('login_page'))

    # Get rider info from Firestore
    user = get_user_by_username(session['username'])
    
    if user:
        user_info = {
            'username': user.get('username', 'N/A'),
            'email': user.get('email', 'N/A'),
            'address': user.get('address', 'N/A'),
            'phone': user.get('phone', 'N/A'),
            'profile_picture': user.get('profile_picture'),
            'created_at': user.get('created_at')
        }
    else:
        user_info = {
            'username': session.get('username', 'N/A'),
            'email': 'N/A',
            'address': 'N/A',
            'phone': 'N/A',
            'profile_picture': None,
            'created_at': None
        }

    return render_template('rider_profile.html', user=user_info)

@app.route('/rider/messages')
def rider_messages():
    if 'username' not in session or session.get('role') != 'rider':
        return redirect(url_for('login_page'))

    return render_template('rider_messages.html')

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'username' not in session or session.get('role') != 'user':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        return redirect(url_for('login_page'))
    
    # Get current user data
    user = get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    username_edited = user.get('username_edited', False)
    old_profile_picture = user.get('profile_picture')
    
    # Check if this is an AJAX request for profile picture update
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'profile_picture' in request.files:
        file = request.files['profile_picture']
        if file and file.filename:
            url = cloud_upload(file, 'verdant/profiles')
            if url:
                if old_profile_picture and 'cloudinary.com' in str(old_profile_picture):
                    cloud_delete(old_profile_picture)
                user_ref = db.collection('users').document(session['username'])
                user_ref.update({'profile_picture': url})
                session['profile_picture'] = url
                return jsonify({'success': True, 'message': 'Profile picture updated successfully', 'profile_picture': url})
            else:
                return jsonify({'success': False, 'message': 'Upload failed'}), 400
        else:
            return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    # Handle username update (only if not edited before)
    new_username = request.form.get('username')
    if new_username and new_username != session['username'] and not username_edited:
        # Check if new username already exists
        existing_user = get_user_by_username(new_username)
        if existing_user:
            return redirect(url_for('profile') + '?error=username_exists')
        
        # Update username and mark as edited
        user_ref = db.collection('users').document(session['username'])
        user_ref.update({
            'username': new_username,
            'username_edited': True
        })
        
        # Update document ID by creating new document and deleting old one
        old_username = session['username']
        user_data = user_ref.get().to_dict()
        user_data['username'] = new_username
        user_data['username_edited'] = True
        
        # Create new document with new username as ID
        db.collection('users').document(new_username).set(user_data)
        
        # Delete old document
        user_ref.delete()
        
        session['username'] = new_username
    
    # Handle profile picture upload
    if 'profile_picture' in request.files:
        file = request.files['profile_picture']
        if file and file.filename:
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            filename = file.filename
            if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                url = cloud_upload(file, 'verdant/profiles')
                if url:
                    if old_profile_picture and 'cloudinary.com' in str(old_profile_picture):
                        cloud_delete(old_profile_picture)
                    user_ref = db.collection('users').document(session['username'])
                    user_ref.update({'profile_picture': url})
                    session['profile_picture'] = url

    return redirect(url_for('profile'))

@app.route('/settings')
def settings():
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page'))
    
    # Get user from Firestore
    user = get_user_by_username(session['username'])
    
    if user:
        # Get user's order statistics
        user_id = user['id']
        all_orders = list(orders_ref.where('user_id', '==', user_id).stream())
        total_orders = len(all_orders)
        delivered_orders = sum(1 for o in all_orders if o.to_dict().get('status') == 'delivered')
        
        # Combine first_name and last_name
        first_name = user.get('first_name', '') or ''
        last_name = user.get('last_name', '') or ''
        full_name = f"{first_name} {last_name}".strip()
        
        user_info = {
            'username': user.get('username', 'N/A'),
            'email': user.get('email', 'N/A'),
            'full_name': full_name,
            'phone': user.get('phone'),
            'profile_picture': user.get('profile_picture'),
            'created_at': user.get('created_at'),
            'address': user.get('address'),
            'latitude': user.get('latitude'),
            'longitude': user.get('longitude'),
            'total_orders': total_orders,
            'delivered_orders': delivered_orders
        }
    else:
        user_info = {
            'username': session.get('username', 'N/A'),
            'email': 'N/A',
            'full_name': None,
            'phone': None,
            'profile_picture': None,
            'created_at': None,
            'address': None,
            'latitude': None,
            'longitude': None,
            'total_orders': 0,
            'delivered_orders': 0
        }
    
    return render_template('settings.html', user=user_info)


@app.route('/user/messages')
def user_messages():
    """Buyer messages page using the shared chat messaging backend."""
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page'))

    return render_template('user_messages.html', current_username=session['username'])

@app.route('/help')
def help_redirect():
    """Redirect user to messages with admin preselected."""
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page'))

    # Find admin user from Firestore
    admin_username = 'admin'
    try:
        admin_users = list(users_ref.where('role', '==', 'admin').limit(1).stream())
        if admin_users:
            admin_username = admin_users[0].to_dict().get('username', 'admin')
    except Exception as e:
        print(f"Error finding admin: {e}")

    return redirect(url_for('user_messages') + f"?with={admin_username}")

@app.route('/shomepage')
def shomepage():
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    return redirect(url_for('seller_dashboard'))

@app.route('/rider_homepage')
def rider_homepage():
    if 'username' not in session or session.get('role') != 'rider':
        return redirect(url_for('login_page'))

    # Get rider info from Firestore
    user = get_user_by_username(session['username'])
    is_approved = user.get('is_approved', False) if user else False
    
    if not is_approved:
        flash('Your rider application is pending approval. You can explore the dashboard and set your service area, but you cannot accept deliveries yet.', 'warning')

    return render_template('rider_dashboard.html', is_approved=is_approved)

@app.route('/admin')
def admin():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    session.pop('profile_picture', None)
    session.pop('user_id', None)
    return redirect(url_for('login_page'))

# ============================================================================
# SELLER DASHBOARD ROUTES
# ============================================================================

@app.route('/seller-dashboard')
def seller_dashboard():
    """Seller dashboard with application check"""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    
    # Get seller info from Firestore
    user = get_user_by_username(session['username'])
    if not user:
        return redirect(url_for('login_page'))
    
    seller_approved = user.get('seller_approved', False)
    user_id = user['id']
    
    # Get ban information
    account_status = user.get('account_status', 'active')
    ban_reason = user.get('ban_reason', '')
    ban_until = user.get('ban_until')
    ban_count = user.get('ban_count', 0)
    ban_permanent = user.get('ban_permanent', False)
    
    # Calculate remaining ban days
    ban_days_remaining = None
    if account_status == 'banned' and ban_until and not ban_permanent:
        from datetime import datetime as _dt
        try:
            ban_until_dt = ban_until if hasattr(ban_until, 'timestamp') else None
            if ban_until_dt:
                now_utc = _dt.utcnow()
                ban_until_naive = ban_until_dt.replace(tzinfo=None)
                if now_utc < ban_until_naive:
                    ban_days_remaining = (ban_until_naive - now_utc).days + 1
        except Exception:
            pass
    
    # Get latest application status
    application_status = None
    application_submitted_at = None
    
    try:
        # Query seller applications (removed order_by to avoid index requirement)
        apps = list(seller_applications_ref.where('user_id', '==', user_id).limit(1).stream())
        
        if apps:
            app_data = apps[0].to_dict()
            application_status = app_data.get('status')
            created_at = app_data.get('created_at')
            if created_at:
                application_submitted_at = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
    except Exception as e:
        print(f"Error fetching seller application: {e}")
        import traceback
        traceback.print_exc()

    return render_template('seller_dashboard.html', 
                         seller_approved=seller_approved, 
                         application_status=application_status, 
                         application_submitted_at=application_submitted_at,
                         account_status=account_status,
                         ban_reason=ban_reason,
                         ban_count=ban_count,
                         ban_permanent=ban_permanent,
                         ban_days_remaining=ban_days_remaining)

@app.route('/seller/messages')
def seller_messages():
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))

    # Get seller info from Firestore
    user = get_user_by_username(session['username'])
    seller_approved = user.get('seller_approved', False) if user else False

    return render_template(
        'seller_messages.html',
        seller_approved=seller_approved,
        current_username=session['username']
    )


@app.route('/api/messages/conversations')
def api_list_conversations():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    username = session['username']
    try:
        # Get all messages where user is sender or receiver
        messages_query = db.collection('messages')\
            .order_by('created_at', direction='DESCENDING')\
            .stream()

        conversations = {}
        order = []
        
        for msg_doc in messages_query:
            msg_data = msg_doc.to_dict()
            sender = msg_data.get('sender_username')
            receiver = msg_data.get('receiver_username')
            
            # Skip if user is not involved
            if sender != username and receiver != username:
                continue
            
            text = msg_data.get('message_text')
            created_at = msg_data.get('created_at')
            is_read = msg_data.get('is_read', False)
            
            other = receiver if sender == username else sender

            if other not in conversations:
                # Get profile picture for the other user
                other_user = get_user_by_username(other)
                profile_picture = other_user.get('profile_picture') if other_user else None
                last_seen = other_user.get('last_seen') if other_user else None
                is_online = other_user.get('is_online', False) if other_user else False

                conversations[other] = {
                    'other_username': other,
                    'profile_picture': profile_picture,
                    'is_online': bool(is_online),
                    'last_seen': last_seen.isoformat() if last_seen and hasattr(last_seen, 'isoformat') else None,
                    'last_message': text,
                    'last_message_time': created_at.isoformat() if created_at and hasattr(created_at, 'isoformat') else str(created_at),
                    'unread_count': 0,
                }
                order.append(other)

            # Count unread messages
            if sender == other and not is_read:
                conversations[other]['unread_count'] += 1

        # Sort conversations by most recent message
        sorted_conversations = []
        for other in order:
            sorted_conversations.append(conversations[other])

        sorted_conversations.sort(
            key=lambda c: c['last_message_time'], reverse=True
        )

        return jsonify({'success': True, 'conversations': sorted_conversations}), 200
    except Exception as e:
        print(f"Error loading conversations: {e}")
        return jsonify({'success': False, 'message': 'Error loading conversations'}), 500
@app.route('/api/messages/thread/<username>')
def api_message_thread(username):
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    current_username = session['username']
    other_username = username

    try:
        # Get all messages between these two users
        messages_query = db.collection('messages')\
            .order_by('created_at')\
            .stream()

        messages = []
        message_ids_to_mark_read = []
        
        for msg_doc in messages_query:
            msg_data = msg_doc.to_dict()
            sender = msg_data.get('sender_username')
            receiver = msg_data.get('receiver_username')
            
            # Check if message is between current user and other user
            if (sender == current_username and receiver == other_username) or \
               (sender == other_username and receiver == current_username):
                
                created_at = msg_data.get('created_at')
                messages.append({
                    'id': msg_doc.id,
                    'sender_username': sender,
                    'receiver_username': receiver,
                    'message_text': msg_data.get('message_text'),
                    'created_at': created_at.isoformat() if created_at and hasattr(created_at, 'isoformat') else str(created_at),
                })
                
                # Mark unread messages from other user as read
                if sender == other_username and not msg_data.get('is_read', False):
                    message_ids_to_mark_read.append(msg_doc.id)

        # Mark messages as read
        for msg_id in message_ids_to_mark_read:
            db.collection('messages').document(msg_id).update({'is_read': True})

        return jsonify({'success': True, 'messages': messages}), 200
    except Exception as e:
        print(f"Error loading message thread: {e}")
        return jsonify({'success': False, 'message': 'Error loading messages'}), 500


@app.route('/api/messages/send', methods=['POST'])
def api_send_message():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json() or {}
    sender = session['username']
    receiver = (data.get('receiver_username') or '').strip()
    text = (data.get('message_text') or '').strip()

    if not receiver or not text:
        return jsonify(
            {'success': False, 'message': 'Receiver and message are required.'}
        ), 400

    if receiver == sender:
        return jsonify(
            {'success': False, 'message': 'You cannot send a message to yourself.'}
        ), 400

    try:
        # Check if receiver exists
        receiver_user = get_user_by_username(receiver)
        if not receiver_user:
            return jsonify(
                {'success': False, 'message': 'Receiver not found.'}
            ), 404

        # Create message
        message_ref = db.collection('messages').document()
        message_data = {
            'sender_username': sender,
            'receiver_username': receiver,
            'message_text': text,
            'is_read': False,
            'created_at': SERVER_TIMESTAMP
        }
        message_ref.set(message_data)
        
        # Get the created message
        message_doc = message_ref.get()
        msg_data = message_doc.to_dict()
        created_at = msg_data.get('created_at')

        msg = {
            'id': message_ref.id,
            'sender_username': sender,
            'receiver_username': receiver,
            'message_text': text,
            'created_at': created_at.isoformat() if created_at and hasattr(created_at, 'isoformat') else str(created_at),
        }

        return jsonify({'success': True, 'message': msg}), 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return jsonify({'success': False, 'message': 'Error sending message.'}), 500
        cursor.close()
        conn.close()

@app.route('/submit_seller_application', methods=['POST'])
def submit_seller_application():
    """Handle seller application submission"""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    
    store_name = request.form.get('store_name')
    store_description = request.form.get('store_description')
    store_category = request.form.get('store_category')
    store_phone = request.form.get('store_phone')
    
    # Handle file uploads
    business_permit_filename = None
    valid_id_filename = None

    if 'business_permit' in request.files:
        file = request.files['business_permit']
        if file and file.filename:
            business_permit_filename = cloud_upload(file, 'verdant/documents')

    if 'valid_id' in request.files:
        file = request.files['valid_id']
        if file and file.filename:
            valid_id_filename = cloud_upload(file, 'verdant/documents')
    
    # Create seller application in Firestore
    application_ref = db.collection('seller_applications').document()
    application_ref.set({
        'username': session['username'],
        'store_name': store_name,
        'store_description': store_description,
        'store_category': store_category,
        'store_phone': store_phone,
        'business_permit': business_permit_filename,
        'valid_id': valid_id_filename,
        'status': 'pending',
        'created_at': firestore_module.SERVER_TIMESTAMP,
        'updated_at': firestore_module.SERVER_TIMESTAMP
    })
    
    # Update user record with store name (but don't approve yet)
    user_ref = db.collection('users').document(session['username'])
    user_ref.update({'store_name': store_name})
    
    flash('Your seller application has been submitted successfully! Please wait for admin approval.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/my-profile', methods=['GET', 'POST'])
def my_profile():
    """Seller profile route with database integration"""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    
    user = get_user_by_username(session['username'])
    if not user:
        return redirect(url_for('login_page'))
    
    user_id = user['id']
    
    if request.method == 'POST':
        # Update editable profile fields
        update_data = {
            'first_name': request.form.get('first_name') or None,
            'last_name': request.form.get('last_name') or None,
            'date_of_birth': request.form.get('birthdate') or None,
            'gender': request.form.get('gender') or None,
            'phone': request.form.get('phone') or None,
            'alternate_phone': request.form.get('alternate_phone') or None,
            'city': request.form.get('city') or None,
            'state_province': request.form.get('state_province') or None,
            'postal_code': request.form.get('postal_code') or None,
            'country': request.form.get('country') or None,
            'store_name': request.form.get('store_name') or None,
            'updated_at': firestore_module.SERVER_TIMESTAMP
        }

        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                filename = file.filename
                if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    url = cloud_upload(file, 'verdant/profiles')
                    if url:
                        if old_profile_picture and 'cloudinary.com' in str(old_profile_picture):
                            cloud_delete(old_profile_picture)
                        update_data['profile_picture'] = url
                        session['profile_picture'] = url        
        # Update in Firestore
        users_ref.document(user_id).update(update_data)
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('my_profile'))
    
    # GET request - fetch seller data
    seller_info = {
        'username': user.get('username', 'N/A'),
        'email': user.get('email', 'N/A'),
        'first_name': user.get('first_name'),
        'last_name': user.get('last_name'),
        'date_of_birth': user.get('date_of_birth'),
        'gender': user.get('gender'),
        'address': user.get('address'),
        'city': user.get('city'),
        'state_province': user.get('state_province'),
        'postal_code': user.get('postal_code'),
        'country': user.get('country', 'Philippines'),
        'phone': user.get('phone'),
        'alternate_phone': user.get('alternate_phone'),
        'latitude': user.get('latitude'),
        'longitude': user.get('longitude'),
        'profile_picture': user.get('profile_picture'),
        'store_name': user.get('store_name')
    }
    seller_approved = user.get('seller_approved', False)
    
    # Get application status
    application_status = None
    application_submitted_at = None
    try:
        apps = list(seller_applications_ref.where('user_id', '==', user_id).limit(1).stream())
        if apps:
            app_data = apps[0].to_dict()
            application_status = app_data.get('status')
            created_at = app_data.get('created_at')
            if created_at:
                application_submitted_at = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
    except Exception as e:
        print(f"Error fetching application: {e}")

    # Count products and orders
    product_count = len(list(products_ref.where('seller_username', '==', session['username']).stream()))
    order_count = len(list(orders_ref.where('seller_id', '==', user_id).stream()))

    return render_template('my_profile.html', seller=seller_info, seller_approved=seller_approved, application_status=application_status, application_submitted_at=application_submitted_at, product_count=product_count, order_count=order_count)

@app.route('/store/preview', methods=['GET', 'POST'])
def store_preview():
    """Store preview route with photo upload and About text editing"""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    
    # Check if seller is approved
    seller = get_user_by_username(session['username'])
    if not seller:
        flash('Seller account not found.', 'error')
        return redirect(url_for('login_page'))

    seller_approved = seller.get('seller_approved', False)
    
    if not seller_approved:
        flash('Your seller application is pending approval. You cannot access your store yet.', 'warning')
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        # Handle store photo uploads
        upload_folder = os.path.join('static', 'uploads', 'store')
        os.makedirs(upload_folder, exist_ok=True)
        photos_updated = False
        user_ref = db.collection('users').document(session['username'])
        update_data = {}

        # Handle cover photo
        if 'cover_photo' in request.files:
            file = request.files['cover_photo']
            if file and file.filename:
                url = cloud_upload(file, 'verdant/store')
                if url:
                    old_pic = seller.get('cover_photo')
                    if old_pic and 'cloudinary.com' in str(old_pic):
                        cloud_delete(old_pic)
                    update_data['cover_photo'] = url
                    photos_updated = True

        # Handle store profile photo
        if 'store_profile' in request.files:
            file = request.files['store_profile']
            if file and file.filename:
                url = cloud_upload(file, 'verdant/store')
                if url:
                    old_pic = seller.get('store_profile')
                    if old_pic and 'cloudinary.com' in str(old_pic):
                        cloud_delete(old_pic)
                    update_data['store_profile'] = url
                    update_data['profile_picture'] = url
                    session['store_profile'] = url
                    session['profile_picture'] = url
                    photos_updated = True

        # Update user photos if any
        if update_data:
            user_ref.update(update_data)

        # Handle About text edits (About form)
        about_text = request.form.get('about_text')
        about_updated = False
        if about_text is not None:
            # Update seller application description
            applications_query = db.collection('seller_applications')\
                .where('username', '==', session['username'])\
                .where('status', '==', 'approved')\
                .stream()
            
            for app_doc in applications_query:
                app_doc.reference.update({'store_description': about_text})
                about_updated = True

        if about_updated and photos_updated:
            flash('Store photos and About section updated.', 'success')
        elif about_updated:
            flash('Store About section updated.', 'success')
        elif photos_updated:
            flash('Store photos updated successfully!', 'success')

        return redirect(url_for('store_preview'))
    
    # Fetch store data, including latest approved description
    applications_query = db.collection('seller_applications')\
        .where('username', '==', session['username'])\
        .where('status', '==', 'approved')\
        .limit(1)\
        .stream()
    
    description = None
    for app_doc in applications_query:
        app_data = app_doc.to_dict()
        description = app_data.get('store_description')
        break
    
    # Fetch products for this seller
    products_query = db.collection('products')\
        .where('seller_username', '==', session['username'])\
        .stream()
    
    store = {
        'name': seller.get('store_name', 'My Store'),
        'cover_photo': seller.get('cover_photo'),
        'store_profile': seller.get('store_profile'),
        'description': description
    }
    
    # Fetch V2 products (with and without variations)
    from firestore_db import products_v2_ref, product_variations_ref
    
    products = []
    seen_ids = set()
    
    # Get V2 products for this seller
    v2_products_query = products_v2_ref.where('seller_username', '==', session['username']).stream()
    
    for product_doc in v2_products_query:
        product_id = product_doc.id
        if product_id in seen_ids:
            continue
        seen_ids.add(product_id)
        
        product_data = product_doc.to_dict()
        
        if product_data.get('has_variations'):
            # Product with variations - get all variations and group them
            variations_query = product_variations_ref.where('parent_product_id', '==', product_id).stream()
            variations_list = []
            for var_doc in variations_query:
                var_data = var_doc.to_dict()
                variations_list.append({
                    'id': var_doc.id,
                    'name': var_data.get('variation_name'),
                    'price': var_data.get('price'),
                    'stock': var_data.get('stock'),
                    'description': var_data.get('description'),
                    'image': var_data.get('image'),
                    'created_at': var_data.get('created_at')
                })
            
            # Sort variations by created_at to maintain order
            variations_list.sort(key=lambda x: x.get('created_at') or datetime.min)
            
            if variations_list:
                # Use first variation as default display
                first_var = variations_list[0]
                products.append({
                    'id': product_id,
                    'name': first_var['name'],
                    'price': first_var['price'],
                    'stock': first_var['stock'],
                    'specifications': first_var['description'],
                    'image': first_var['image'],
                    'has_variations': True,
                    'variations': variations_list,
                    'parent_id': product_id
                })
        else:
            # Single product without variations
            products.append({
                'id': product_id,
                'name': product_data.get('product_name'),
                'price': product_data.get('price'),
                'stock': product_data.get('stock'),
                'specifications': product_data.get('description'),
                'image': product_data.get('image'),
                'has_variations': False,
                'variations': []
            })
    
    print(f"📦 Store preview: Found {len(products)} products (V2) for {session['username']}")
    
    response = app.make_response(render_template('store_preview.html', store=store, products=products, seller_approved=seller_approved))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/add_product', methods=['POST'])
def add_product():
    """Handle adding new product with support for multiple images and a thumbnail."""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))

    product_name = request.form.get('product_name')
    price = request.form.get('price')
    stock = request.form.get('stock')
    specifications = request.form.get('specifications')

    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    upload_folder = os.path.join('static', 'uploads', 'products')
    os.makedirs(upload_folder, exist_ok=True)

    files = []
    if 'product_images' in request.files:
        files = request.files.getlist('product_images')
    elif 'product_image' in request.files:
        single_file = request.files['product_image']
        if single_file:
            files = [single_file]

    saved_filenames = []
    for file in files:
        if not file or not file.filename:
            continue
        filename = file.filename
        if '.' not in filename:
            continue
        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_extensions:
            continue
        url = cloud_upload(file, 'verdant/products')
        if url:
            saved_filenames.append(url)

    image_filename = saved_filenames[0] if saved_filenames else 'default.jpg'
    thumb_raw = request.form.get('thumbnail_index')
    try:
        thumb_index = int(thumb_raw) if thumb_raw is not None else 0
    except (TypeError, ValueError):
        thumb_index = 0
    if thumb_index < 0 or thumb_index >= len(saved_filenames):
        thumb_index = 0
    if saved_filenames:
        image_filename = saved_filenames[thumb_index]

    # Add product to Firestore (only once)
    product_data = {
        'seller_username': session['username'],
        'product_name': product_name,
        'price': float(price) if price else 0.0,
        'stock': int(stock) if stock else 0,
        'specifications': specifications or '',
        'image': image_filename,
        'is_active': True,
        'created_at': firestore_module.SERVER_TIMESTAMP,
        'updated_at': firestore_module.SERVER_TIMESTAMP
    }
    
    product_ref = products_ref.add(product_data)
    product_id = product_ref[1].id
    
    print(f"✅ Product added to Firestore: {product_name} (ID: {product_id})")

    # Add product images to Firestore
    if saved_filenames:
        for idx, filename in enumerate(saved_filenames):
            is_thumbnail = idx == thumb_index
            product_images_ref.add({
                'product_id': product_id,
                'filename': filename,
                'is_thumbnail': is_thumbnail,
                'sort_order': idx,
                'created_at': firestore_module.SERVER_TIMESTAMP
            })
        print(f"📸 Added {len(saved_filenames)} images for product {product_id}")

    # Don't use flash, we'll show notification via JavaScript
    return redirect(url_for('store_preview', product_added='1'))


@app.route('/add_product_v2', methods=['POST'])
def add_product_v2():
    """Handle adding new product with variations support (V2 system)"""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    
    try:
        # Get form data
        main_category = request.form.get('main_category')
        subcategory = request.form.get('subcategory')
        has_variations = request.form.get('has_variations') == 'yes'
        
        # Import the new collections
        from firestore_db import products_v2_ref, product_variations_ref
        
        if not has_variations:
            # Single product without variations
            product_name = request.form.get('product_name')
            description = request.form.get('description')
            price = float(request.form.get('price', 0))
            stock = int(request.form.get('stock', 0))
            
            # Handle image upload
            image_file = request.files.get('product_image')
            image_filename = None
            if image_file and image_file.filename:
                image_filename = cloud_upload(image_file, 'verdant/products')
            
            # Create product in products_v2
            product_data = {
                'seller_username': session['username'],
                'product_name': product_name,
                'main_category': main_category,
                'subcategory': subcategory,
                'has_variations': False,
                'description': description,
                'price': price,
                'stock': stock,
                'image': image_filename,
                'created_at': firestore_module.SERVER_TIMESTAMP,
                'updated_at': firestore_module.SERVER_TIMESTAMP
            }
            
            products_v2_ref.add(product_data)
            
        else:
            # Product with variations
            # The JavaScript creates form fields with names like variation_description_0, variation_price_0, etc.
            # We need to collect all the variation data from the form
            
            # First, figure out how many variations were submitted by checking form keys
            variation_count = 0
            for key in request.form.keys():
                if key.startswith('variation_description_'):
                    variation_count += 1
            
            if variation_count == 0:
                flash('No variations found. Please add at least one variation.', 'error')
                return redirect(url_for('store_preview'))
            
            # Create parent product
            parent_product_data = {
                'seller_username': session['username'],
                'product_name': request.form.get('product_name', ''),
                'main_category': main_category,
                'subcategory': subcategory,
                'has_variations': True,
                'variation_count': variation_count,
                'created_at': firestore_module.SERVER_TIMESTAMP,
                'updated_at': firestore_module.SERVER_TIMESTAMP
            }
            
            parent_ref = products_v2_ref.add(parent_product_data)
            parent_id = parent_ref[1].id
            
            print(f"✅ Created parent product V2 with {variation_count} variations (ID: {parent_id})")
            
            # Create each variation
            for idx in range(variation_count):
                variation_name = request.form.get(f'variation_name_{idx}', f'Variation {idx + 1}')
                description = request.form.get(f'variation_description_{idx}', '')
                price = float(request.form.get(f'variation_price_{idx}', 0))
                stock = int(request.form.get(f'variation_stock_{idx}', 0))
                
                # Handle variation image
                image_file = request.files.get(f'variation_image_{idx}')
                image_filename = None
                if image_file and image_file.filename:
                    image_filename = cloud_upload(image_file, 'verdant/products')
                
                variation_data = {
                    'parent_product_id': parent_id,
                    'seller_username': session['username'],
                    'variation_name': variation_name,
                    'description': description,
                    'price': price,
                    'stock': stock,
                    'image': image_filename,
                    'main_category': main_category,
                    'subcategory': subcategory,
                    'created_at': firestore_module.SERVER_TIMESTAMP,
                    'updated_at': firestore_module.SERVER_TIMESTAMP
                }
                product_variations_ref.add(variation_data)
                print(f"  ✅ Added variation: {variation_name} (Price: ₱{price}, Stock: {stock})")
        
        print(f"✅ Product V2 added successfully!")
        return redirect(url_for('store_preview', product_added='1'))
        
    except Exception as e:
        print(f"Error adding product v2: {e}")
        import traceback
        traceback.print_exc()
        flash('Error adding product. Please try again.', 'error')
        return redirect(url_for('store_preview'))


@app.route('/seller/products/bulk-delete', methods=['POST'])
def bulk_delete_products():
    """Bulk delete products for the logged-in seller (V2 with variations support)."""
    if 'username' not in session or session.get('role') != 'seller':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json() or {}
    raw_ids = data.get('product_ids', [])

    if not isinstance(raw_ids, list):
        return jsonify({'success': False, 'message': 'Invalid payload'}), 400

    # Sanitize IDs to strings (Firestore document IDs)
    product_ids = []
    for pid in raw_ids:
        try:
            product_ids.append(str(pid))
        except (TypeError, ValueError):
            continue

    if not product_ids:
        return jsonify({'success': False, 'message': 'No valid product IDs provided'}), 400

    try:
        from firestore_db import products_v2_ref, product_variations_ref
        
        deleted_count = 0
        for product_id in product_ids:
            print(f"🔍 Attempting to delete product V2: {product_id}")
            
            # Check if it's a V2 product
            product_doc = products_v2_ref.document(product_id).get()
            
            if not product_doc.exists:
                print(f"⚠️ Product {product_id} not found in products_v2")
                continue
            
            product_data = product_doc.to_dict()
            
            if product_data.get('seller_username') != session['username']:
                print(f"⚠️ Product {product_id} does not belong to {session['username']}")
                continue
            
            # If product has variations, delete all variations first
            if product_data.get('has_variations'):
                variations_query = product_variations_ref.where('parent_product_id', '==', product_id).stream()
                variation_count = 0
                for var_doc in variations_query:
                    var_doc.reference.delete()
                    variation_count += 1
                print(f"🗑️ Deleted {variation_count} variations for product {product_id}")
            
            # Delete the parent product
            products_v2_ref.document(product_id).delete()
            print(f"✅ Deleted product document {product_id}")
            
            deleted_count += 1
        
        print(f"✅ Total products deleted: {deleted_count}")
        return jsonify({'success': True, 'deleted_count': deleted_count}), 200
    except Exception as e:
        print(f"Error deleting products for seller {session.get('username')}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Error deleting products'}), 500

@app.route('/product/<product_id>')
def product_detail(product_id):
    """Product detail page accessible by guests, buyers, and sellers"""
    
    # Get product from Firestore V2
    from firestore_db import products_v2_ref, product_variations_ref
    
    product_doc_ref = products_v2_ref.document(product_id).get()
    
    if not product_doc_ref.exists:
        flash('Product not found', 'error')
        if 'username' in session:
            return redirect(url_for('homepage') if session.get('role') == 'user' else url_for('store_preview'))
        else:
            return redirect(url_for('guest_home'))
    
    product_doc = product_doc_ref.to_dict()

    # Get seller information
    seller = get_user_by_username(product_doc.get('seller_username', ''))
    store_name = seller.get('store_name', '') if seller else ''
    if not store_name and seller:
        store_name = f"{seller.get('first_name', '')} {seller.get('last_name', '')}".strip()
    
    # Handle products with variations
    if product_doc.get('has_variations'):
        # Get all variations
        variations_query = product_variations_ref.where('parent_product_id', '==', product_id).stream()
        variations = []
        total_stock = 0
        for var_doc in variations_query:
            var_data = var_doc.to_dict()
            variations.append({
                'id': var_doc.id,
                'name': var_data.get('variation_name', ''),
                'price': var_data.get('price', 0),
                'stock': var_data.get('stock', 0),
                'description': var_data.get('description', ''),
                'image': var_data.get('image', 'default.jpg')
            })
            total_stock += var_data.get('stock', 0)
        
        # Use first variation as default display
        first_var = variations[0] if variations else None
        product = {
            'id': product_id,
            'name': first_var['name'] if first_var else product_doc.get('product_name', ''),
            'price': first_var['price'] if first_var else 0,
            'stock': total_stock,
            'specifications': first_var['description'] if first_var else '',
            'image': first_var['image'] if first_var else 'default.jpg',
            'seller_username': product_doc.get('seller_username', ''),
            'created_at': product_doc.get('created_at'),
            'store_name': store_name,
            'store_profile': seller.get('store_profile', '') if seller else '',
            'has_variations': True,
            'variations': variations
        }
    else:
        # Single product
        product = {
            'id': product_id,
            'name': product_doc.get('product_name', ''),
            'price': product_doc.get('price', 0),
            'stock': product_doc.get('stock', 0),
            'specifications': product_doc.get('description', ''),
            'image': product_doc.get('image', 'default.jpg'),
            'seller_username': product_doc.get('seller_username', ''),
            'created_at': product_doc.get('created_at'),
            'store_name': store_name,
            'store_profile': seller.get('store_profile', '') if seller else '',
            'has_variations': False,
            'variations': []
        }

    profile_picture = None
    if 'username' in session:
        user = get_user_by_username(session['username'])
        profile_picture = user.get('profile_picture') if user else None

    # Get product images from Firestore (removed order_by to avoid index requirement)
    images_query = product_images_ref.where('product_id', '==', product_id).stream()
    images = []
    for img_doc in images_query:
        img_data = img_doc.to_dict()
        images.append({
            'id': img_doc.id,
            'filename': img_data.get('filename', ''),
            'is_thumbnail': img_data.get('is_thumbnail', False),
            'sort_order': img_data.get('sort_order', 0)
        })
    
    # Sort by sort_order in Python instead of Firestore
    images.sort(key=lambda x: x.get('sort_order', 0))
    
    # If no images, use main product image
    if not images and product.get('image'):
        images.append({
            'id': None,
            'filename': product['image'],
            'is_thumbnail': True,
            'sort_order': 0
        })

    is_guest = 'username' not in session
    is_seller = session.get('role') == 'seller' if 'username' in session else False
    is_owner = session.get('username') == product['seller_username'] if 'username' in session else False

    # Get reviews from Firestore
    reviews_query = db.collection('reviews')\
        .where('product_id', '==', product_id)\
        .where('status', '==', 'approved')\
        .stream()
    
    total_rating = 0
    total_reviews = 0
    for review_doc in reviews_query:
        review_data = review_doc.to_dict()
        total_reviews += 1
        total_rating += review_data.get('rating', 0)
    
    avg_rating = (total_rating / total_reviews) if total_reviews > 0 else 0.0
    
    # Check if user can review (has received this product)
    user_can_review = False
    if 'username' in session and session.get('role') == 'user':
        orders_query = db.collection('orders')\
            .where('username', '==', session['username'])\
            .where('status', '==', 'delivered')\
            .stream()
        
        for order_doc in orders_query:
            order_id = order_doc.id
            items_query = db.collection('order_items')\
                .where('order_id', '==', order_id)\
                .where('product_id', '==', product_id)\
                .limit(1)\
                .stream()
            
            if any(True for _ in items_query):
                user_can_review = True
                break

    return render_template(
        'product_detail.html',
        product=product,
        profile_picture=profile_picture,
        is_seller=is_seller,
        is_owner=is_owner,
        is_guest=is_guest,
        images=images,
        avg_rating=round(avg_rating, 1),
        total_reviews=total_reviews,
        user_can_review=user_can_review,
    )


@app.route('/product/<product_id>/reviews')
def get_product_reviews(product_id):
    """Return reviews summary and list for a product as JSON."""
    try:
        product_id_str = str(product_id)
        
        # Get all approved reviews for this product (without ordering to avoid index requirement)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reviews_query = db.collection('reviews')\
                .where('product_id', '==', product_id_str)\
                .where('status', '==', 'approved')\
                .stream()
        
        reviews_list = []
        total_rating = 0
        total_reviews = 0
        
        for review_doc in reviews_query:
            review_data = review_doc.to_dict()
            total_reviews += 1
            total_rating += review_data.get('rating', 0)
            
            # Get review photos
            photos_query = db.collection('review_photos')\
                .where('review_id', '==', review_doc.id)\
                .stream()
            photos = [photo_doc.to_dict().get('filename') for photo_doc in photos_query]
            
            created_at = review_data.get('created_at')
            reviews_list.append({
                'id': review_doc.id,
                'customer_name': review_data.get('customer_name'),
                'rating': review_data.get('rating'),
                'comment': review_data.get('comment'),
                'created_at': created_at,
                'created_at_str': created_at.strftime('%Y-%m-%d %H:%M') if created_at and hasattr(created_at, 'strftime') else '',
                'photos': photos,
            })
        
        # Sort by created_at in Python instead of Firestore
        from datetime import datetime
        reviews_list.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        
        # Remove the datetime object before sending JSON
        reviews_payload = []
        for review in reviews_list:
            review_copy = review.copy()
            review_copy.pop('created_at', None)
            reviews_payload.append(review_copy)
        
        avg_rating = (total_rating / total_reviews) if total_reviews > 0 else 0.0
        
        return jsonify({
            'success': True,
            'avg_rating': round(float(avg_rating), 1),
            'total_reviews': total_reviews,
            'reviews': reviews_payload,
        }), 200
    except Exception as e:
        print(f"Error loading reviews for product {product_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/product/<product_id>/reviews', methods=['POST'])
def submit_product_review(product_id):
    """Submit a new review for a product. Only delivered buyers can review."""
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    rating = int(request.form.get('rating', '0') or 0)
    comment = (request.form.get('comment') or '').strip()

    if rating < 1 or rating > 5:
        return jsonify({'success': False, 'error': 'Rating must be between 1 and 5.'}), 400

    try:
        product_id_str = str(product_id)
        
        # Check if user has received this product (delivered order)
        orders_query = db.collection('orders')\
            .where('username', '==', session['username'])\
            .where('status', '==', 'delivered')\
            .stream()
        
        has_received_product = False
        for order_doc in orders_query:
            order_id = order_doc.id
            # Check if this order contains the product
            items_query = db.collection('order_items')\
                .where('order_id', '==', order_id)\
                .where('product_id', '==', product_id_str)\
                .limit(1)\
                .stream()
            
            if any(True for _ in items_query):
                has_received_product = True
                break
        
        if not has_received_product:
            return jsonify({'success': False, 'error': 'You can only review products you have received.'}), 403
        
        # Create review in Firestore
        review_ref = db.collection('reviews').document()
        review_ref.set({
            'product_id': product_id_str,
            'customer_name': session['username'],
            'rating': rating,
            'comment': comment,
            'status': 'approved',
            'created_at': firestore_module.SERVER_TIMESTAMP
        })
        
        review_id = review_ref.id
        
        # Handle photo uploads
        files = request.files.getlist('photos') or []
        for f in files:
            if not f or not f.filename:
                continue
            url = cloud_upload(f, 'verdant/reviews')
            if url:
                db.collection('review_photos').document().set({
                    'review_id': review_id,
                    'url': url,
                    'created_at': firestore_module.SERVER_TIMESTAMP
                })

        return jsonify({'success': True}), 201
    except Exception as e:
        print(f"Error saving review for product {product_id}: {e}")
        return jsonify({'success': False, 'error': 'Failed to save review.'}), 500


@app.route('/store/<seller_username>')
def public_store(seller_username):
    """Public store profile page for a seller, visible to guests and logged-in users."""
    try:
        from firestore_db import products_v2_ref, product_variations_ref
        
        # Fetch basic seller store info
        seller = get_user_by_username(seller_username)
        
        print(f"DEBUG: Fetching store for username: {seller_username}")
        print(f"DEBUG: Seller data: {seller}")
        
        if not seller or seller.get('role') != 'seller':
            print(f"DEBUG: Seller not found or not a seller role")
            return render_template('store_public.html', store=None, products=[], not_found=True), 404

        seller_approved = seller.get('seller_approved', False)
        print(f"DEBUG: Seller approved status: {seller_approved}")

        # Only show approved stores publicly
        if not seller_approved:
            print(f"DEBUG: Seller not approved, returning 404")
            return render_template('store_public.html', store=None, products=[], not_found=True), 404

        # Get latest approved store description from seller applications
        applications_query = db.collection('seller_applications')\
            .where('username', '==', seller_username)\
            .where('status', '==', 'approved')\
            .limit(1)\
            .stream()
        
        description = None
        for app_doc in applications_query:
            app_data = app_doc.to_dict()
            description = app_data.get('store_description')
            break

        # Fetch products from V2 collection
        products_query = products_v2_ref.where('seller_username', '==', seller_username).stream()

        store = {
            'username': seller_username,
            'name': seller.get('store_name') or f"{seller_username}'s Store",
            'cover_photo': seller.get('cover_photo'),
            'store_profile': seller.get('store_profile'),
            'description': description,
        }

        products = []
        for product_doc in products_query:
            product_data = product_doc.to_dict()
            
            if product_data.get('has_variations'):
                # Get all variations for this product
                variations_query = product_variations_ref.where('parent_product_id', '==', product_doc.id).stream()
                variations_list = []
                total_stock = 0
                for var_doc in variations_query:
                    var_data = var_doc.to_dict()
                    variations_list.append({
                        'id': var_doc.id,
                        'name': var_data.get('variation_name', ''),
                        'price': var_data.get('price', 0),
                        'stock': var_data.get('stock', 0),
                        'description': var_data.get('description', ''),
                        'image': var_data.get('image', 'default.jpg')
                    })
                    total_stock += var_data.get('stock', 0)
                
                if variations_list and total_stock > 0:
                    # Use first variation as default
                    first_var = variations_list[0]
                    products.append({
                        'id': product_doc.id,
                        'name': first_var['name'],
                        'price': first_var['price'],
                        'stock': total_stock,
                        'specifications': first_var['description'],
                        'image': first_var['image'],
                    })
            else:
                # Single product
                stock = product_data.get('stock', 0)
                if stock > 0:
                    products.append({
                        'id': product_doc.id,
                        'name': product_data.get('product_name'),
                        'price': product_data.get('price'),
                        'stock': stock,
                        'specifications': product_data.get('description'),
                        'image': product_data.get('image'),
                    })

        return render_template('store_public.html', store=store, products=products, not_found=False)
    except Exception as e:
        print(f"Error loading public store for {seller_username}: {e}")
        import traceback
        traceback.print_exc()
        return render_template('store_public.html', store=None, products=[], error=str(e), not_found=True), 500

@app.route('/admin/cashouts')
def admin_cashouts():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    
    requests = CashOutRequest.query.order_by(CashOutRequest.created_at.desc()).all()
    return render_template('admin_cashouts.html', requests=requests)

@app.route('/admin/cashouts/<int:req_id>/approve', methods=['POST'])
def approve_cashout(req_id):
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    
    req = CashOutRequest.query.get_or_404(req_id)
    if req.status != 'Pending':
        flash('Request is not pending.', 'warning')
        return redirect(url_for('admin_cashouts'))
    acct = WalletAccount.query.first()
    req.status = 'Approved'
    req.reviewed_at = datetime.utcnow()
    # On approval, pending_payouts decreases; funds are considered paid out
    acct.pending_payouts = max(0.0, float(acct.pending_payouts or 0) - float(req.amount))
    # Record transaction (credit to payout)
    db.session.add(Transaction(type='credit', amount=float(req.amount), description='Cash out approved'))
    db.session.commit()
    # Email stub
    send_email_stub('seller@example.com', 'Cash Out Approved', f'Your cash out request #{req.id} for ₱{float(req.amount):,.2f} has been approved.')
    flash('Cash out approved.', 'success')
    return redirect(url_for('admin_cashouts'))

@app.route('/admin/cashouts/<int:req_id>/reject', methods=['POST'])
def reject_cashout(req_id):
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    
    req = CashOutRequest.query.get_or_404(req_id)
    if req.status != 'Pending':
        flash('Request is not pending.', 'warning')
        return redirect(url_for('admin_cashouts'))
    acct = WalletAccount.query.first()
    req.status = 'Rejected'
    req.reviewed_at = datetime.utcnow()
    # On rejection, return funds to balance and reduce pending
    acct.pending_payouts = max(0.0, float(acct.pending_payouts or 0) - float(req.amount))
    acct.balance = float(acct.balance or 0) + float(req.amount)
    # Record transaction (credit back to balance)
    db.session.add(Transaction(type='credit', amount=float(req.amount), description='Cash out rejected - funds returned'))
    db.session.commit()
    # Email stub
    send_email_stub('seller@example.com', 'Cash Out Rejected', f'Your cash out request #{req.id} for ₱{float(req.amount):,.2f} was rejected. Funds returned to balance.')
    flash('Cash out rejected and funds returned to balance.', 'info')
    return redirect(url_for('admin_cashouts'))

# ============================================================================
# ADMIN ROUTES - Seller Application Management
# ============================================================================

@app.route('/admin/dashboard')
def admin_dashboard():
    """Admin dashboard with high-level seller application metrics."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    try:
        # Get all seller applications
        applications_query = db.collection('seller_applications').stream()
        
        pending_count = 0
        approved_count = 0
        rejected_count = 0
        
        for app_doc in applications_query:
            app_data = app_doc.to_dict()
            status = app_data.get('status')
            if status == 'pending':
                pending_count += 1
            elif status == 'approved':
                approved_count += 1
            elif status == 'rejected':
                rejected_count += 1
        
        total_count = pending_count + approved_count + rejected_count
        approval_rate = (approved_count / total_count * 100.0) if total_count > 0 else 0.0
        
        return render_template(
            'admin_dashboard_v2.html',
            pending_count=pending_count,
            approved_count=approved_count,
            total_count=total_count,
            approval_rate=approval_rate
        )
    except Exception as e:
        print(f"Error loading admin dashboard: {e}")
        return render_template(
            'admin_dashboard_v2.html',
            pending_count=0,
            approved_count=0,
            total_count=0,
            approval_rate=0.0
        )


@app.route('/admin/seller-applications')
def admin_seller_applications():
    """List seller applications in a dedicated admin page."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    try:
        print("🔍 Loading seller applications...")
        
        # Get all seller applications (without ordering to avoid index requirement)
        applications_query = db.collection('seller_applications').stream()
        
        applications = []
        for app_doc in applications_query:
            app_data = app_doc.to_dict()
            
            print(f"📄 Found application: {app_doc.id} - {app_data.get('store_name')} - Status: {app_data.get('status')}")
            
            # Get user info including ban status
            user = get_user_by_username(app_data.get('username'))
            
            # Format created_at timestamp
            created_at = app_data.get('created_at')
            created_at_formatted = None
            if created_at:
                try:
                    if hasattr(created_at, 'strftime'):
                        created_at_formatted = created_at
                    else:
                        # It's a Firestore timestamp, convert it
                        created_at_formatted = created_at
                except Exception as e:
                    print(f"⚠️ Error formatting timestamp: {e}")
                    created_at_formatted = None
            
            applications.append({
                'id': app_doc.id,
                'user_id': app_data.get('username'),
                'store_name': app_data.get('store_name'),
                'store_category': app_data.get('store_category'),
                'store_phone': app_data.get('store_phone'),
                'status': app_data.get('status'),
                'created_at': created_at_formatted,
                'username': app_data.get('username'),
                'email': user.get('email') if user else '',
                'ban_count': user.get('ban_count', 0) if user else 0,
                'ban_permanent': user.get('ban_permanent', False) if user else False
            })
        
        # Sort in Python instead of Firestore
        applications.sort(key=lambda x: x.get('created_at') or '', reverse=True)
        
        pending_count = sum(1 for app in applications if app['status'] == 'pending')
        approved_count = sum(1 for app in applications if app['status'] == 'approved')
        total_count = len(applications)
        
        print(f"✅ Loaded {total_count} applications ({pending_count} pending, {approved_count} approved)")
        print(f"📋 Applications list: {[app['store_name'] for app in applications]}")
        
        return render_template(
            'admin_seller_applications.html',
            applications=applications,
            pending_count=pending_count,
            approved_count=approved_count,
            total_count=total_count
        )
    except Exception as e:
        print(f"❌ Error loading seller applications: {e}")
        import traceback
        traceback.print_exc()
        return render_template(
            'admin_seller_applications.html',
            applications=[],
            pending_count=0,
            approved_count=0,
            total_count=0
        )


@app.route('/admin/seller-applications/<application_id>')
def admin_seller_application_detail(application_id):
    """Detailed view of a single seller application."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    try:
        # Get application (application_id is already a string)
        app_doc = db.collection('seller_applications').document(application_id).get()
        
        if not app_doc.exists:
            flash('Seller application not found.', 'warning')
            return redirect(url_for('admin_seller_applications'))
        
        app_data = app_doc.to_dict()
        
        # Get user info
        user = get_user_by_username(app_data['username'])
        
        application = {
            'id': application_id,
            'user_id': app_data.get('username'),  # Using username as user_id
            'store_name': app_data.get('store_name'),
            'store_description': app_data.get('store_description'),
            'store_category': app_data.get('store_category'),
            'store_phone': app_data.get('store_phone'),
            'business_permit': app_data.get('business_permit'),
            'valid_id': app_data.get('valid_id'),
            'status': app_data.get('status'),
            'created_at': app_data.get('created_at'),
            'updated_at': app_data.get('updated_at'),
            'username': app_data.get('username'),
            'email': user.get('email') if user else '',
            'first_name': user.get('first_name') if user else '',
            'last_name': user.get('last_name') if user else '',
            'address': user.get('address') if user else '',
            'phone': user.get('phone') if user else ''
        }

        return render_template(
            'admin_seller_application_detail.html',
            application=application
        )
    except Exception as e:
        print(f"Error loading seller application detail: {e}")
        flash('Error loading application details.', 'error')
        return redirect(url_for('admin_seller_applications'))


@app.route('/admin/seller-application/<application_id>/<action>', methods=['POST'])
def handle_seller_application(application_id, action):
    """Approve or reject seller application"""
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
    
    try:
        # Get application (application_id is already a string)
        app_ref = db.collection('seller_applications').document(application_id)
        app_doc = app_ref.get()
        
        if not app_doc.exists:
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        
        app_data = app_doc.to_dict()
        username = app_data.get('username')
        
        if action == 'approve':
            # Update seller_applications status
            app_ref.update({'status': 'approved'})
            
            # Update user's seller_approved status
            user_ref = db.collection('users').document(username)
            user_ref.update({'seller_approved': True})
            
            message = 'Seller application approved successfully!'
        else:
            # Update seller_applications status
            app_ref.update({'status': 'rejected'})
            
            message = 'Seller application rejected!'
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        print(f"Error handling seller application: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/user-applications')
def admin_user_applications():
    """List user account verification applications."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    try:
        print("🔍 Loading user applications...")
        
        # Get all user applications (without ordering to avoid index requirement)
        applications_query = db.collection('user_applications').stream()
        
        applications = []
        for app_doc in applications_query:
            app_data = app_doc.to_dict()
            
            print(f"📄 Found user application: {app_doc.id} - {app_data.get('username')} - Status: {app_data.get('status')}")
            
            # Format submitted_at timestamp
            submitted_at = app_data.get('submitted_at')
            submitted_at_formatted = None
            if submitted_at:
                try:
                    if hasattr(submitted_at, 'strftime'):
                        submitted_at_formatted = submitted_at
                    else:
                        submitted_at_formatted = submitted_at
                except Exception as e:
                    print(f"⚠️ Error formatting timestamp: {e}")
                    submitted_at_formatted = None
            
            applications.append({
                'id': app_doc.id,
                'user_id': app_data.get('user_id'),
                'username': app_data.get('username'),
                'email': app_data.get('email'),
                'phone': app_data.get('phone'),
                'first_name': app_data.get('first_name'),
                'last_name': app_data.get('last_name'),
                'middle_initial': app_data.get('middle_initial', ''),
                'date_of_birth': app_data.get('date_of_birth'),
                'gender': app_data.get('gender'),
                'status': app_data.get('status'),
                'submitted_at': submitted_at_formatted
            })
        
        # Sort in Python instead of Firestore
        applications.sort(key=lambda x: x.get('submitted_at') or '', reverse=True)
        
        pending_count = sum(1 for app in applications if app['status'] == 'pending')
        approved_count = sum(1 for app in applications if app['status'] == 'approved')
        total_count = len(applications)
        
        print(f"✅ Loaded {total_count} user applications ({pending_count} pending, {approved_count} approved)")
        
        return render_template(
            'admin_user_applications.html',
            applications=applications,
            pending_count=pending_count,
            approved_count=approved_count,
            total_count=total_count
        )
    except Exception as e:
        print(f"❌ Error loading user applications: {e}")
        import traceback
        traceback.print_exc()
        return render_template(
            'admin_user_applications.html',
            applications=[],
            pending_count=0,
            approved_count=0,
            total_count=0
        )


@app.route('/admin/user-applications/<application_id>')
def admin_user_application_detail(application_id):
    """Detailed view of a single user application."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    try:
        # Get application
        app_doc = db.collection('user_applications').document(application_id).get()
        
        if not app_doc.exists:
            flash('User application not found.', 'warning')
            return redirect(url_for('admin_user_applications'))
        
        app_data = app_doc.to_dict()
        
        application = {
            'id': application_id,
            'user_id': app_data.get('user_id'),
            'username': app_data.get('username'),
            'email': app_data.get('email'),
            'phone': app_data.get('phone'),
            'first_name': app_data.get('first_name'),
            'last_name': app_data.get('last_name'),
            'middle_initial': app_data.get('middle_initial', ''),
            'date_of_birth': app_data.get('date_of_birth'),
            'gender': app_data.get('gender'),
            'status': app_data.get('status'),
            'submitted_at': app_data.get('submitted_at')
        }
        
        return render_template('admin_user_application_detail.html', application=application)
        
    except Exception as e:
        print(f"Error loading user application detail: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading application details.', 'danger')
        return redirect(url_for('admin_user_applications'))


@app.route('/admin/user-application/<application_id>/<action>', methods=['POST'])
def handle_user_application(application_id, action):
    """Approve or reject user application"""
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
    
    try:
        # Get application
        app_ref = db.collection('user_applications').document(application_id)
        app_doc = app_ref.get()
        
        if not app_doc.exists:
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        
        app_data = app_doc.to_dict()
        user_id = app_data.get('user_id')
        
        if action == 'approve':
            # Update user_applications status
            app_ref.update({'status': 'approved'})
            
            # Update user's is_approved status
            user_ref = db.collection('users').document(user_id)
            user_ref.update({'is_approved': True})

            # Send notification to user
            try:
                create_notification({
                    'user_id': user_id,
                    'type': 'account_approved',
                    'title': 'Account Approved!',
                    'message': 'Your account has been verified and approved. You can now place orders.',
                    'link': '/homepage',
                })
            except Exception as notif_err:
                print(f"Warning: Could not create notification: {notif_err}")
            
            message = 'User application approved successfully!'
        else:
            # Update user_applications status
            app_ref.update({'status': 'rejected'})
            
            # Update user's is_approved status to False
            user_ref = db.collection('users').document(user_id)
            user_ref.update({'is_approved': False})
            
            message = 'User application rejected!'
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        print(f"Error handling user application: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/rider-applications')
def admin_rider_applications():
    """List rider applications for admin review."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    try:
        # Get all rider applications
        applications_query = db.collection('rider_applications').order_by('created_at', direction='DESCENDING').stream()

        applications = []
        for app_doc in applications_query:
            app_data = app_doc.to_dict()
            applications.append({
                'id': app_doc.id,
                'user_id': app_data.get('username'),  # Using username as user_id
                'full_name': app_data.get('full_name'),
                'address': app_data.get('address'),
                'phone': app_data.get('phone'),
                'email': app_data.get('email'),
                'vehicle_type': app_data.get('vehicle_type'),
                'vehicle_registration': app_data.get('vehicle_registration'),
                'license_number': app_data.get('license_number'),
                'license_image': app_data.get('license_image'),
                'status': app_data.get('status'),
                'created_at': app_data.get('created_at'),
                'username': app_data.get('username'),
            })

        pending_count = sum(1 for app in applications if app['status'] == 'pending')
        approved_count = sum(1 for app in applications if app['status'] == 'approved')
        total_count = len(applications)

        return render_template(
            'admin_rider_applications.html',
            applications=applications,
            pending_count=pending_count,
            approved_count=approved_count,
            total_count=total_count,
        )
    except Exception as e:
        print(f"Error loading rider applications: {e}")
        return render_template(
            'admin_rider_applications.html',
            applications=[],
            pending_count=0,
            approved_count=0,
            total_count=0,
        )


@app.route('/admin/rider-applications/<application_id>')
def admin_rider_application_detail(application_id):
    """Detailed view of a single rider application."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    try:
        application_id_str = str(application_id)
        
        # Get application
        app_doc = db.collection('rider_applications').document(application_id_str).get()
        
        if not app_doc.exists:
            flash('Rider application not found.', 'warning')
            return redirect(url_for('admin_rider_applications'))
        
        app_data = app_doc.to_dict()
        
        application = {
            'id': application_id_str,
            'user_id': app_data.get('username'),  # Using username as user_id
            'full_name': app_data.get('full_name'),
            'address': app_data.get('address'),
            'phone': app_data.get('phone'),
            'email': app_data.get('email'),
            'vehicle_type': app_data.get('vehicle_type'),
            'vehicle_registration': app_data.get('vehicle_registration'),
            'license_number': app_data.get('license_number'),
            'license_image': app_data.get('license_image'),
            'status': app_data.get('status'),
            'created_at': app_data.get('created_at'),
            'updated_at': app_data.get('updated_at'),
            'username': app_data.get('username'),
        }

        return render_template('admin_rider_application_detail.html', application=application)
    except Exception as e:
        print(f"Error loading rider application detail: {e}")
        flash('Error loading application details.', 'error')
        return redirect(url_for('admin_rider_applications'))


@app.route('/admin/rider-application/<user_id>/<action>', methods=['POST'])
def handle_rider_application(user_id, action):
    """Approve or reject rider application and toggle users.is_approved."""
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

    try:
        # user_id is actually the application_id in this context
        application_id_str = str(user_id)
        
        # Get application
        app_ref = db.collection('rider_applications').document(application_id_str)
        app_doc = app_ref.get()
        
        if not app_doc.exists:
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        
        app_data = app_doc.to_dict()
        username = app_data.get('username')
        
        if action == 'approve':
            # Update rider_applications status
            app_ref.update({'status': 'approved'})
            
            # Update user's is_approved status
            user_ref = db.collection('users').document(username)
            user_ref.update({'is_approved': True})
        else:
            # Update rider_applications status
            app_ref.update({'status': 'rejected'})
            
            # Update user's is_approved status
            user_ref = db.collection('users').document(username)
            user_ref.update({'is_approved': False})

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error handling rider application: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/messaging')
def admin_messaging():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    return render_template('admin_messaging.html', current_username=session['username'])


# Rider Routes
@app.route('/rider/available-orders')
@role_required('rider')
def get_available_orders():
    """Get orders that are approved by sellers and available for delivery"""
    try:
        # Get orders that are accepted/shipped by sellers but not yet assigned to riders
        orders_query = db.collection('orders')\
            .where('status', 'in', ['accepted', 'shipped'])\
            .stream()
        
        orders = []
        for order_doc in orders_query:
            order_data = order_doc.to_dict()
            order_id = order_doc.id
            
            # Skip if already assigned to a rider
            if order_data.get('rider_username'):
                continue
            
            # Get customer info
            customer = get_user_by_username(order_data['username'])
            customer_latitude = customer.get('latitude') if customer else None
            customer_longitude = customer.get('longitude') if customer else None
            
            # Get seller info
            seller = get_user_by_username(order_data['seller_username'])
            seller_latitude = seller.get('latitude') if seller else None
            seller_longitude = seller.get('longitude') if seller else None
            
            # Get product names
            items_query = db.collection('order_items').where('order_id', '==', order_id).stream()
            product_names = []
            for item_doc in items_query:
                item_data = item_doc.to_dict()
                product = get_product_by_id(item_data['product_id'])
                if product:
                    product_names.append(product['product_name'])
            
            orders.append({
                'id': order_id,
                'public_id': format_public_order_id(order_id),
                'total_amount': float(order_data.get('total_amount', 0)),
                'status': order_data.get('status'),
                'order_date': order_data.get('order_date').isoformat() if order_data.get('order_date') else None,
                'customer_name': order_data.get('username'),
                'customer_latitude': float(customer_latitude) if customer_latitude is not None else None,
                'customer_longitude': float(customer_longitude) if customer_longitude is not None else None,
                'seller_name': order_data.get('seller_username'),
                'seller_latitude': float(seller_latitude) if seller_latitude is not None else None,
                'seller_longitude': float(seller_longitude) if seller_longitude is not None else None,
                'delivery_address': order_data.get('shipping_address', 'Address not provided'),
                'product_names': ', '.join(product_names)
            })
        
        return jsonify({'success': True, 'orders': orders})
        
    except Exception as e:
        print(f"Error getting available orders: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/rider/my-deliveries')
@role_required('rider')
def get_my_deliveries():
    """Get current active deliveries for the rider"""
    try:
        # Get current rider and check approval status
        rider = get_user_by_username(session['username'])
        if not rider:
            return jsonify({'success': False, 'message': 'Rider not found'}), 404

        is_approved = rider.get('is_approved', False)
        if not is_approved:
            return jsonify({'success': False, 'message': 'Rider not approved yet'}), 403

        # Get non-delivered, non-cancelled orders assigned to this rider
        orders_query = db.collection('orders')\
            .where('rider_username', '==', session['username'])\
            .stream()

        deliveries = []
        for order_doc in orders_query:
            order_data = order_doc.to_dict()
            order_id = order_doc.id
            
            # Skip delivered, cancelled, or rejected orders
            if order_data.get('status') in ('delivered', 'cancelled', 'rejected'):
                continue
            
            # Get customer info
            customer = get_user_by_username(order_data['username'])
            
            # Get seller info
            seller = get_user_by_username(order_data['seller_username'])
            
            # Get order items
            items_query = db.collection('order_items').where('order_id', '==', order_id).stream()
            items_list = []
            for item_doc in items_query:
                item_data = item_doc.to_dict()
                product = get_product_by_id(item_data['product_id'])
                if product:
                    items_list.append(f"{product['product_name']} × {item_data['quantity']}")
            
            items_summary = ", ".join(items_list)

            deliveries.append({
                'id': order_id,
                'public_id': format_public_order_id(order_id),
                'delivery_status': order_data.get('status'),
                'delivery_address': order_data.get('shipping_address', 'No address provided'),
                'customer_name': order_data.get('username'),
                'customer_phone': customer.get('phone') if customer else None,
                'customer_latitude': float(customer.get('latitude')) if customer and customer.get('latitude') is not None else None,
                'customer_longitude': float(customer.get('longitude')) if customer and customer.get('longitude') is not None else None,
                'seller_name': order_data.get('seller_username'),
                'seller_latitude': float(seller.get('latitude')) if seller and seller.get('latitude') is not None else None,
                'seller_longitude': float(seller.get('longitude')) if seller and seller.get('longitude') is not None else None,
                'items': items_summary
            })

        return jsonify({'success': True, 'deliveries': deliveries})
    except Exception as e:
        print(f"Error getting my deliveries: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/rider/delivery-history')
@role_required('rider')
def get_delivery_history():
    """Get rider's delivery history"""
    try:
        # Get current rider and check approval status
        rider = get_user_by_username(session['username'])
        if not rider:
            return jsonify({'success': False, 'message': 'Rider not found'}), 404

        is_approved = rider.get('is_approved', False)
        if not is_approved:
            return jsonify({'success': False, 'message': 'Rider not approved yet'}), 403
        
        # Get delivered orders for this rider
        orders_query = db.collection('orders')\
            .where('rider_username', '==', session['username'])\
            .where('status', '==', 'delivered')\
            .order_by('delivery_date', direction='DESCENDING')\
            .stream()
        
        deliveries = []
        for order_doc in orders_query:
            order_data = order_doc.to_dict()
            order_id = order_doc.id
            
            deliveries.append({
                'id': order_id,
                'public_id': format_public_order_id(order_id),
                'total_amount': float(order_data.get('total_amount', 0)),
                'delivered_at': order_data.get('delivery_date').isoformat() if order_data.get('delivery_date') else None,
                'customer_name': order_data.get('username')
            })
        
        # Return under both keys for compatibility with older JS
        return jsonify({'success': True, 'history': deliveries, 'deliveries': deliveries})
        
    except Exception as e:
        print(f"Error getting delivery history: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/rider/update-delivery-status/<order_id>', methods=['POST'])
@role_required('rider')
def update_delivery_status(order_id):
    """Update delivery status for an order and notify the customer"""
    try:
        data = request.get_json() or {}
        status = data.get('status')
        notes = (data.get('notes') or '').strip()

        if status not in ['out_for_delivery', 'delivered']:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400

        # Get order and ensure it belongs to this rider (order_id is already a string)
        order_ref = db.collection('orders').document(order_id)
        order_doc = order_ref.get()
        
        if not order_doc.exists:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order_data = order_doc.to_dict()
        
        if order_data.get('rider_username') != session['username']:
            return jsonify({'success': False, 'message': 'Order not found for this rider'}), 404

        customer_username = order_data.get('username')
        current_status = order_data.get('status')

        new_order_status = current_status
        send_notification = False
        notif_type = None
        notif_title = None
        notif_message = None
        public_id = format_public_order_id(order_id)

        if status == 'delivered':
            # Mark as delivered
            new_order_status = 'delivered'
            send_notification = True
            notif_type = 'order_delivered'
            notif_title = 'Order Delivered'
            notif_message = f"Your order ID {public_id} has been delivered. Thank you for shopping with us!"
        else:
            # Rider marks order as out for delivery
            if current_status != 'out_for_delivery':
                new_order_status = 'out_for_delivery'
                send_notification = True
                notif_type = 'order_shipped'
                notif_title = 'Order Out for Delivery'
                notif_message = f"Your order ID {public_id} is now out for delivery."

        # Update order record
        update_data = {'status': new_order_status}
        if notes:
            update_data['notes'] = notes
        if new_order_status == 'delivered':
            update_data['delivery_date'] = SERVER_TIMESTAMP
        
        order_ref.update(update_data)

        # Send notification to customer if needed
        if send_notification and notif_type:
            notification_ref = db.collection('notifications').document()
            notification_ref.set({
                'username': customer_username,
                'order_id': order_id,
                'type': notif_type,
                'title': notif_title,
                'message': notif_message,
                'is_read': False,
                'created_at': SERVER_TIMESTAMP
            })

        return jsonify({'success': True, 'message': 'Delivery status updated successfully'})
    except Exception as e:
        print(f"Error updating delivery status: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/rider/notifications')
@role_required('rider')
def get_rider_notifications_legacy():
    """Get rider notifications"""
    try:
        # Get notifications for this rider
        notifications_query = db.collection('notifications')\
            .where('username', '==', session['username'])\
            .order_by('created_at', direction='DESCENDING')\
            .limit(20)\
            .stream()
        
        notifications = []
        for notif_doc in notifications_query:
            notif_data = notif_doc.to_dict()
            created_at = notif_data.get('created_at')
            
            notifications.append({
                'message': notif_data.get('message'),
                'created_at': created_at.isoformat() if created_at else None,
                'read': notif_data.get('is_read', False)
            })
        
        return jsonify({'success': True, 'notifications': notifications})
        
    except Exception as e:
        print(f"Error getting rider notifications: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/rider/accept-order/<order_id>', methods=['POST'])
@role_required('rider')
def accept_order(order_id):
    """Accept an order for delivery"""
    try:
        # Check if order exists and is available (order_id is already a string)
        order_ref = db.collection('orders').document(order_id)
        order_doc = order_ref.get()
        
        if not order_doc.exists:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order_data = order_doc.to_dict()
        
        # Check if order is available
        if order_data.get('status') not in ('accepted', 'shipped') or order_data.get('rider_username'):
            return jsonify({'success': False, 'message': 'Order not available'}), 404
        
        customer_username = order_data.get('username')
        
        # Assign rider to order and update status
        order_ref.update({
            'rider_username': session['username'],
            'status': 'out_for_delivery',
            'accepted_at': SERVER_TIMESTAMP
        })
        
        # Send notification to customer
        public_id = format_public_order_id(order_id)
        notification_ref = db.collection('notifications').document()
        notification_ref.set({
            'username': customer_username,
            'order_id': order_id,
            'type': 'order_shipped',
            'title': 'Order Out for Delivery',
            'message': f"Great news! Your order ID {public_id} has been accepted by a rider and is out for delivery!",
            'is_read': False,
            'created_at': SERVER_TIMESTAMP
        })
        
        return jsonify({'success': True, 'message': 'Order accepted successfully!'})
        
    except Exception as e:
        print(f"Error accepting order: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/rider/reject-order/<order_id>', methods=['POST'])
@role_required('rider')
def reject_order(order_id):
    """Reject an order with reason"""
    try:
        data = request.get_json()
        reason = data.get('reason', '').strip()
        
        if not reason:
            return jsonify({'success': False, 'message': 'Rejection reason is required'}), 400
        
        # Ensure rider is approved before rejecting orders
        rider = get_user_by_username(session['username'])
        is_approved = rider.get('is_approved', False) if rider else False
        if not is_approved:
            return jsonify({'success': False, 'message': 'Rider not approved yet'}), 403
        
        # Check if order exists and is available (order_id is already a string)
        order_ref = db.collection('orders').document(order_id)
        order_doc = order_ref.get()
        
        if not order_doc.exists:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order_data = order_doc.to_dict()
        
        if order_data.get('status') != 'accepted' or order_data.get('rider_username'):
            return jsonify({'success': False, 'message': 'Order not available'}), 404
        
        customer_username = order_data.get('username')
        
        # Update order status and add rejection reason
        order_ref.update({
            'status': 'rejected',
            'rejection_reason': reason,
            'rejected_at': SERVER_TIMESTAMP
        })
        
        # Send notification to customer
        public_id = format_public_order_id(order_id)
        notification_ref = db.collection('notifications').document()
        notification_ref.set({
            'username': customer_username,
            'order_id': order_id_str,
            'type': 'order_rejected',
            'title': 'Order Rejected',
            'message': f"Sorry, your order ID {public_id} was rejected by the delivery service. Reason: {reason}",
            'is_read': False,
            'created_at': SERVER_TIMESTAMP
        })
        
        return jsonify({'success': True, 'message': 'Order rejected successfully'})
        
    except Exception as e:
        print(f"Error rejecting order: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# API Routes for Seller Order Management (for AJAX calls)
@app.route('/api/seller/orders')
@role_required('seller')
def api_get_seller_orders():
    """API endpoint to get orders for seller's products"""
    try:
        # Get orders for this seller (removed order_by to avoid index requirement)
        orders_query = db.collection('orders')\
            .where('seller_username', '==', session['username'])\
            .stream()
        
        orders = []
        for order_doc in orders_query:
            order_data = order_doc.to_dict()
            order_id = order_doc.id
            
            orders.append({
                'id': order_id,
                'total_amount': float(order_data.get('total_amount', 0)),
                'status': order_data.get('status'),
                'order_date': order_data.get('order_date'),
                'customer_name': order_data.get('username'),
                'delivery_address': order_data.get('shipping_address', 'Address not provided')
            })
        
        # Sort by order_date in Python instead of Firestore
        orders.sort(key=lambda x: x.get('order_date') or datetime.min, reverse=True)
        
        # Convert dates to ISO format after sorting
        for order in orders:
            if order['order_date'] and hasattr(order['order_date'], 'isoformat'):
                order['order_date'] = order['order_date'].isoformat()
            elif order['order_date']:
                order['order_date'] = str(order['order_date'])
        
        return jsonify({'success': True, 'orders': orders})
        
    except Exception as e:
        print(f"Error getting seller orders: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

def send_order_acceptance_message(customer_id, seller_username, order_id):
    """Send automated thank you message to customer when seller accepts order"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get customer username
        cursor.execute("SELECT username FROM users WHERE id = %s", (customer_id,))
        customer_result = cursor.fetchone()
        if not customer_result:
            print(f"Customer not found for ID: {customer_id}")
            return False
        
        customer_username = customer_result[0]
        print(f"Sending message from {seller_username} to {customer_username} for order {order_id}")
        
        # Get order details including product names and quantities
        cursor.execute("""
            SELECT oi.quantity, p.name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (order_id,))
        
        order_items = cursor.fetchall()
        
        # Create item details string
        items_text = ""
        if order_items:
            items_text = "\n\n📦 Order details:\n"
            for item in order_items:
                items_text += f"• {item[1]} (Qty: {item[0]})\n"
        
        # Create automated thank you message
        thank_you_message = f"""🎉 Thank you for your order, {customer_username}!

Your order #{format_public_order_id(order_id)} has been accepted and is being prepared for shipment.{items_text}
I'm here to help if you have any questions about your order or need assistance with anything. Feel free to message me anytime!"""
        
        # Insert message into chat_messages
        cursor.execute("""
            INSERT INTO chat_messages (sender_username, receiver_username, message_text, created_at, is_read)
            VALUES (%s, %s, %s, NOW(), FALSE)
        """, (seller_username, customer_username, thank_you_message))
        
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Successfully sent order acceptance message to {customer_username}")
        return True
        
    except Exception as e:
        print(f"Error sending order acceptance message: {e}")
        import traceback
        traceback.print_exc()
        return False

# DISABLED - Using Firestore version in checkout_routes.py instead
# @app.route('/seller/order/<order_id>/accept', methods=['POST'])
# @role_required('seller')
# def accept_seller_order(order_id):
#     """Accept an order as seller"""
#     try:
#         conn = get_db_connection()
#         cursor = conn.cursor()
#         
#         # Get current seller's ID
#         cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
#         seller_result = cursor.fetchone()
#         if not seller_result:
#             return jsonify({'success': False, 'message': 'Seller not found'}), 404
#         
#         seller_id = seller_result[0]
#         
#         # Check if order contains seller's products and is pending
#         cursor.execute("""
#             SELECT DISTINCT o.id, o.user_id, o.status
#             FROM orders o
#             JOIN order_items oi ON o.id = oi.order_id
#             JOIN products p ON oi.product_id = p.id
#             WHERE o.id = %s AND p.seller_username = %s AND o.status = 'pending'
#         """, (order_id, session['username']))
#         
#         order = cursor.fetchone()
#         if not order:
#             return jsonify({'success': False, 'message': 'Order not found or already processed'}), 404
#         
#         customer_id = order[1]
#         
#         # Update order status to accepted
#         cursor.execute("""
#             UPDATE orders 
#             SET status = 'accepted', accepted_at = NOW()
#             WHERE id = %s
#         """, (order_id,))
#         
#         # Send notification to customer
#         public_id = format_public_order_id(order_id)
#         cursor.execute("""
#             INSERT INTO notifications (user_id, order_id, type, title, message)
#             VALUES (%s, %s, %s, %s, %s)
#         """, (
#             customer_id,
#             order_id,
#             'order_accepted',
#             'Order Accepted',
#             f"Your order ID {public_id} has been approved by the seller and is now available for delivery!"
#         ))
#         
#         # Send automated thank you message to customer
#         print(f"Attempting to send order acceptance message to customer_id: {customer_id}")
#         message_sent = send_order_acceptance_message(customer_id, session['username'], order_id)
#         print(f"Message sending result: {message_sent}")
#         
#         conn.commit()
#         cursor.close()
#         conn.close()
#         
#         return jsonify({'success': True, 'message': 'Order approved successfully!'})
#         
#     except Exception as e:
#         return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/seller/approve-order/<order_id>', methods=['POST'])
@role_required('seller')
def api_approve_order(order_id):
    """API endpoint to approve an order"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current seller's ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        seller_result = cursor.fetchone()
        if not seller_result:
            return jsonify({'success': False, 'message': 'Seller not found'}), 404
        
        seller_id = seller_result[0]
        
        # Check if order contains seller's products and is pending
        cursor.execute("""
            SELECT DISTINCT o.id, o.user_id, o.status
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.id = %s AND p.seller_username = %s AND o.status = 'pending'
        """, (order_id, session['username']))
        
        order = cursor.fetchone()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found or already processed'}), 404
        
        customer_id = order[1]
        
        # Update order status to accepted
        cursor.execute("""
            UPDATE orders 
            SET status = 'accepted', accepted_at = NOW()
            WHERE id = %s
        """, (order_id,))
        
        # Send notification to customer
        public_id = format_public_order_id(order_id)
        cursor.execute("""
            INSERT INTO notifications (user_id, order_id, type, title, message)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            customer_id,
            order_id,
            'order_accepted',
            'Order Accepted',
            f"Your order ID {public_id} has been approved by the seller and is now available for delivery!"
        ))
        
        # Send automated thank you message to customer
        print(f"Attempting to send order acceptance message to customer_id: {customer_id}")
        message_sent = send_order_acceptance_message(customer_id, session['username'], order_id)
        print(f"Message sending result: {message_sent}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Order approved successfully!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/seller/reject-order/<order_id>', methods=['POST'])
@role_required('seller')
def api_reject_seller_order(order_id):
    """API endpoint to reject an order with reason"""
    try:
        data = request.get_json()
        reason = data.get('reason', '').strip()
        
        if not reason:
            return jsonify({'success': False, 'message': 'Rejection reason is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current seller's ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        seller_result = cursor.fetchone()
        if not seller_result:
            return jsonify({'success': False, 'message': 'Seller not found'}), 404
        
        seller_id = seller_result[0]
        
        # Check if order contains seller's products and is pending
        cursor.execute("""
            SELECT DISTINCT o.id, o.user_id, o.status
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.id = %s AND p.seller_username = %s AND o.status = 'pending'
        """, (order_id, session['username']))
        
        order = cursor.fetchone()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found or already processed'}), 404
        
        customer_id = order[1]
        
        # Update order status to rejected
        cursor.execute("""
            UPDATE orders 
            SET status = 'rejected', rejection_reason = %s, rejected_at = NOW()
            WHERE id = %s
        """, (reason, order_id))
        
        # Send notification to customer
        public_id = format_public_order_id(order_id)
        cursor.execute("""
            INSERT INTO notifications (user_id, order_id, type, title, message)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            customer_id,
            order_id,
            'order_rejected',
            'Order Rejected',
            f"Your order ID {public_id} was rejected by the seller. Reason: {reason}"
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Order rejected successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Register checkout routes (migrated to Firestore)
register_checkout_routes(app)

@app.route('/api/mobile/login', methods=['POST'])
def api_mobile_login():
    """Login endpoint for Flutter mobile app"""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'}), 400

    user = get_user_by_username(username)
    if not user:
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

    stored_pw = user.get('password', '')
    is_hashed = stored_pw.startswith('pbkdf2:') or stored_pw.startswith('scrypt:')

    if is_hashed:
        valid = check_password_hash(stored_pw, password)
    else:
        valid = stored_pw == password

    if not valid:
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

    return jsonify({
        'success': True,
        'username': username,
        'role': user.get('role', 'user'),
        'email': user.get('email', ''),
    })

@app.route('/admin/seller/manage/<username>', methods=['POST'])
def admin_manage_seller(username):
    """Ban or delete a seller account"""
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
        action = data.get('action')  # 'ban' or 'delete'
        reason = data.get('reason', '')

        user_ref = db.collection('users').document(username)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        user_data = user_doc.to_dict()

        if action == 'delete':
            user_ref.update({
                'account_status': 'deleted',
                'delete_reason': reason,
                'deleted_at': firestore_module.SERVER_TIMESTAMP,
                'seller_approved': False,
            })
            # Force logout by invalidating any active session
            # (Sessions are server-side; the user will be blocked on next request)
            message = f'Seller account @{username} has been deleted.'

        elif action == 'ban':
            ban_count = user_data.get('ban_count', 0) + 1
            from datetime import datetime as _dt, timedelta as _td
            if ban_count == 1:
                ban_days = 1
            elif ban_count == 2:
                ban_days = 3
            else:
                ban_days = None  # Permanent

            ban_until = None if ban_days is None else (_dt.utcnow() + _td(days=ban_days))

            user_ref.update({
                'account_status': 'banned',
                'ban_reason': reason,
                'ban_count': ban_count,
                'ban_until': ban_until,
                'ban_permanent': ban_days is None,
                'seller_approved': False if ban_days is None else user_data.get('seller_approved', False),
            })
            if ban_days is None:
                message = f'Seller @{username} permanently banned (3rd offence).'
            else:
                message = f'Seller @{username} banned for {ban_days} day(s) (ban #{ban_count}).'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400

        return jsonify({'success': True, 'message': message, 'ban_count': user_data.get('ban_count', 0) + 1 if action == 'ban' else None})

    except Exception as e:
        print(f"Error managing seller: {e}")
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/debug/products')
def debug_products():
    """Public debug endpoint - shows products and seller approval status"""
    try:
        from firestore_db import products_v2_ref, product_variations_ref
        result = []
        for prod_doc in products_v2_ref.stream():
            prod_data = prod_doc.to_dict()
            seller_username = prod_data.get('seller_username', '')
            seller = get_user_by_username(seller_username)
            result.append({
                'id': prod_doc.id,
                'product_name': prod_data.get('product_name', ''),
                'has_variations': prod_data.get('has_variations', False),
                'stock': prod_data.get('stock', 0),
                'seller_username': seller_username,
                'seller_exists': seller is not None,
                'seller_approved': seller.get('seller_approved', False) if seller else False,
            })
        return jsonify({'total': len(result), 'products': result})
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    # Initialize database tables before starting the app
    init_database()
    app.run(debug=True)
