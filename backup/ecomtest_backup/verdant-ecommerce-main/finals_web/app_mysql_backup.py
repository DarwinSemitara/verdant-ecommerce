from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import random
import time
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from functools import wraps
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests
import shutil
from db import initialize_database
from checkout_routes import register_checkout_routes

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  

# SQLAlchemy configuration for MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:@localhost/verdant'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Uploads config
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024  # 4 MB limit
PRODUCTS_UPLOAD_SUBDIR = os.path.join('static', 'uploads', 'products')
DOCUMENTS_UPLOAD_SUBDIR = os.path.join('static', 'uploads', 'documents')

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

# Hardcoded admin credentials
ADMIN_CREDENTIALS = {
    'username': 'admin',
    'password': generate_password_hash('admin123')
}

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",  # Set this if you configured a MySQL password
        database="verdant"
    )


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
# DATABASE MODELS
# ============================================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    first_name = db.Column(db.String(50))
    middle_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    birthdate = db.Column(db.Date)
    gender = db.Column(db.String(10))
    contact_number = db.Column(db.String(20))
    profile_picture = db.Column(db.String(200))
    role = db.Column(db.String(20), default='seller')
    last_login = db.Column(db.DateTime)
    last_login_location = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Store(db.Model):
    __tablename__ = 'stores'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    operating_hours = db.Column(db.String(100))
    payment_methods = db.Column(db.String(200))
    profile_image = db.Column(db.String(200))
    cover_image = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(100))
    image_path = db.Column(db.String(255))
    stock_quantity = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rider_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.Enum('pending', 'confirmed', 'shipped', 'delivered', 'cancelled'), default='pending')
    shipping_address = db.Column(db.Text, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_date = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='orders_as_customer')
    seller = db.relationship('User', foreign_keys=[seller_id], backref='orders_as_seller')
    rider = db.relationship('User', foreign_keys=[rider_id], backref='orders_as_rider')
    order_items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Relationships
    product = db.relationship('Product', backref='order_items')

class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    product = db.relationship('Product', backref='reviews')
    customer_name = db.Column(db.String(100))
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ReviewPhoto(db.Model):
    __tablename__ = 'review_photos'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    review = db.relationship('Review', backref='photos')

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    customer_email = db.Column(db.String(120))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default='unread')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    customer_email = db.Column(db.String(120))
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    subject = db.Column(db.String(200))
    description = db.Column(db.Text)
    priority = db.Column(db.String(20), default='medium')
    status = db.Column(db.String(20), default='open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WalletAccount(db.Model):
    __tablename__ = 'wallet_accounts'
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Float, default=0)
    pending_payouts = db.Column(db.Float, default=0)
    min_withdraw = db.Column(db.Float, default=500)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CashOutRequest(db.Model):
    __tablename__ = 'cashout_requests'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20))  # 'credit' or 'debit'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    """Initialize database tables"""
    # Initialize MySQL database and tables
    initialize_database()
    
    # Also create SQLAlchemy tables for seller dashboard
    with app.app_context():
        db.create_all()
        print("SQLAlchemy tables created successfully!")

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
    out_of_stock_products = Product.query.filter(Product.stock_quantity == 0, Product.is_active == True).all()
    low_stock_products = Product.query.filter(
        Product.stock_quantity > 0,
        Product.stock_quantity <= low_stock_threshold, 
        Product.is_active == True
    ).all()
    
    return {
        'out_of_stock': out_of_stock_products,
        'low_stock': low_stock_products,
        'total_alerts': len(out_of_stock_products) + len(low_stock_products)
    }

def get_top_products():
    """Get top 3 best-selling products by units sold in last 30 days"""
    from datetime import datetime, timedelta
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Get all completed orders from last 30 days
    recent_orders = Order.query.filter(
        Order.order_date >= thirty_days_ago,
        Order.status == 'completed'
    ).all()
    
    # Calculate product sales
    product_sales = {}
    for order in recent_orders:
        product_id = order.product_id
        if product_id not in product_sales:
            product_sales[product_id] = {
                'product': order.product,
                'total_quantity': 0,
                'total_revenue': 0,
                'order_count': 0
            }
        product_sales[product_id]['total_quantity'] += order.quantity
        product_sales[product_id]['total_revenue'] += float(order.total_amount)
        product_sales[product_id]['order_count'] += 1
    
    # Sort by total quantity sold and get top 3
    sorted_products = sorted(product_sales.values(), key=lambda x: x['total_quantity'], reverse=True)
    return sorted_products[:3]

def get_customer_communication_data():
    """Get customer reviews, messages, and support tickets data"""
    # Pending reviews
    pending_reviews = Review.query.filter_by(status='pending').order_by(Review.created_at.desc()).limit(5).all()
    
    # Unread messages
    unread_messages = Message.query.filter_by(status='unread').order_by(Message.created_at.desc()).limit(5).all()
    
    # Open support tickets
    open_tickets = SupportTicket.query.filter(
        SupportTicket.status.in_(['open', 'in_progress'])
    ).order_by(SupportTicket.created_at.desc()).limit(5).all()
    
    return {
        'pending_reviews': pending_reviews,
        'unread_messages': unread_messages,
        'open_tickets': open_tickets,
        'total_pending_reviews': Review.query.filter_by(status='pending').count(),
        'total_unread_messages': Message.query.filter_by(status='unread').count(),
        'total_open_tickets': SupportTicket.query.filter(SupportTicket.status.in_(['open', 'in_progress'])).count()
    }

def get_order_status_breakdown():
    """Get breakdown of order statuses"""
    status_counts = {}
    statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled', 'completed']
    
    for status in statuses:
        count = Order.query.filter_by(status=status).count()
        status_counts[status] = count
    
    return status_counts

def get_order_status_summary():
    """Aggregate order statuses into friendly groups for dashboard."""
    from datetime import datetime, timedelta

    delay_threshold_days = 7
    threshold_dt = datetime.utcnow() - timedelta(days=delay_threshold_days)

    pending_payment = Order.query.filter_by(status='pending').count()
    ready_to_ship = Order.query.filter_by(status='processing').count()
    delayed_exception = Order.query.filter(
        Order.order_date < threshold_dt,
        Order.status.in_(['pending', 'processing', 'shipped'])
    ).count()
    completed = Order.query.filter_by(status='completed').count()

    return {
        'pending_payment': pending_payment,
        'ready_to_ship': ready_to_ship,
        'delayed_exception': delayed_exception,
        'completed': completed,
        'delay_threshold_days': delay_threshold_days,
    }

def get_financial_health_data():
    """Get financial health data including balance and payout info"""
    wallet = WalletAccount.query.first()
    if not wallet:
        wallet = WalletAccount(balance=0, pending_payouts=0, min_withdraw=500)
        db.session.add(wallet)
        db.session.commit()
    
    # Get next payout date (simplified - assuming monthly payouts)
    from datetime import datetime, timedelta
    next_payout = datetime.utcnow() + timedelta(days=15)  # Simplified calculation
    
    return {
        'available_balance': float(wallet.balance or 0),
        'pending_payouts': float(wallet.pending_payouts or 0),
        'min_withdraw': float(wallet.min_withdraw or 0),
        'next_payout_date': next_payout,
        'eligible_for_payout': float(wallet.balance or 0) >= float(wallet.min_withdraw or 0)
    }

def get_sales_chart_data():
    """Get sales data for chart visualization over last 30 days"""
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    chart_data = []
    
    # Get daily sales for last 30 days
    for i in range(30):
        date = now - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        
        daily_orders = Order.query.filter(
            db.func.date(Order.order_date) == date.date(),
            Order.status == 'completed'
        ).all()
        
        daily_revenue = sum(float(order.total_amount) for order in daily_orders)
        daily_orders_count = len(daily_orders)
        
        chart_data.append({
            'date': date_str,
            'revenue': daily_revenue,
            'orders': daily_orders_count
        })
    
    # Reverse to get chronological order
    chart_data.reverse()
    
    # Calculate week-over-week growth
    current_week_revenue = sum(item['revenue'] for item in chart_data[-7:])
    previous_week_revenue = sum(item['revenue'] for item in chart_data[-14:-7])
    
    if previous_week_revenue > 0:
        week_growth = ((current_week_revenue - previous_week_revenue) / previous_week_revenue) * 100
    else:
        week_growth = 100.0 if current_week_revenue > 0 else 0.0
    
    return {
        'chart_data': chart_data,
        'week_growth': round(week_growth, 1),
        'current_week_revenue': current_week_revenue,
        'previous_week_revenue': previous_week_revenue
    }

def get_dashboard_summary():
    """Get comprehensive dashboard summary data"""
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    
    # Total sales/revenue
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.status == 'completed'
    ).scalar() or 0
    
    # Total orders
    total_orders = Order.query.count()
    
    # Pending orders
    pending_orders = Order.query.filter_by(status='pending').count()
    
    # Get oldest pending order ID
    oldest_pending_order = Order.query.filter_by(status='pending').order_by(Order.order_date.asc()).first()
    oldest_pending_order_id = oldest_pending_order.id if oldest_pending_order else None
    
    # Low stock alerts
    low_stock_count = Product.query.filter(
        Product.stock_quantity <= 10,
        Product.stock_quantity > 0,
        Product.is_active == True
    ).count()
    
    out_of_stock_count = Product.query.filter(
        Product.stock_quantity == 0,
        Product.is_active == True
    ).count()
    
    total_stock_alerts = low_stock_count + out_of_stock_count
    
    # Available wallet balance
    wallet = WalletAccount.query.first()
    available_balance = float(wallet.balance or 0) if wallet else 0.0
    
    # Recent activity (last 7 days)
    week_ago = now - timedelta(days=7)
    recent_orders = Order.query.filter(Order.order_date >= week_ago).count()
    recent_revenue = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.order_date >= week_ago,
        Order.status == 'completed'
    ).scalar() or 0
    
    return {
        'total_revenue': float(total_revenue),
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'oldest_pending_order_id': oldest_pending_order_id,
        'stock_alerts': total_stock_alerts,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'available_balance': available_balance,
        'recent_orders': recent_orders,
        'recent_revenue': float(recent_revenue)
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

    # Fetch all products from all sellers for guest users
    conn = get_db_connection()
    cursor = conn.cursor()

    products = []
    best_sellers = []
    new_arrivals = []
    best_deals = []
    
    try:
        # First check if there are any products at all
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]
        print(f"Total products in database: {total_products}")
        
        cursor.execute("""
            SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image, 
                   p.seller_username, u.store_name
            FROM products p
            JOIN users u ON p.seller_username COLLATE utf8mb4_unicode_ci = u.username COLLATE utf8mb4_unicode_ci
            WHERE p.stock > 0
            ORDER BY p.created_at DESC
        """)
        products_data = cursor.fetchall()
        print(f"Products fetched for guest: {len(products_data)}")
        
        if products_data:
            for p in products_data:
                products.append({
                    'id': p[0],
                    'name': p[1],
                    'price': p[2],
                    'stock': p[3],
                    'specifications': p[4],
                    'image': p[5],
                    'seller_username': p[6],
                    'store_name': p[7]
                })

        # ==============================
        # Featured Collections
        # ==============================

        # Best Sellers: top 3 products by total quantity sold
        cursor.execute("""
            SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
                   p.seller_username, u.store_name,
                   COALESCE(SUM(oi.quantity), 0) AS total_sold
            FROM products p
            JOIN users u ON p.seller_username COLLATE utf8mb4_unicode_ci = u.username COLLATE utf8mb4_unicode_ci
            LEFT JOIN order_items oi ON p.id = oi.product_id
            LEFT JOIN orders o ON oi.order_id = o.id
            WHERE p.stock > 0
            GROUP BY p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
                     p.seller_username, u.store_name
            ORDER BY total_sold DESC
            LIMIT 3
        """)
        best_sellers_data = cursor.fetchall()
        if best_sellers_data:
            for p in best_sellers_data:
                best_sellers.append({
                    'id': p[0],
                    'name': p[1],
                    'price': p[2],
                    'stock': p[3],
                    'specifications': p[4],
                    'image': p[5],
                    'seller_username': p[6],
                    'store_name': p[7]
                })

        # New Arrivals: 3 most recently added products
        cursor.execute("""
            SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
                   p.seller_username, u.store_name
            FROM products p
            JOIN users u ON p.seller_username COLLATE utf8mb4_unicode_ci = u.username COLLATE utf8mb4_unicode_ci
            WHERE p.stock > 0
            ORDER BY p.created_at DESC
            LIMIT 3
        """)
        new_arrivals_data = cursor.fetchall()
        if new_arrivals_data:
            for p in new_arrivals_data:
                new_arrivals.append({
                    'id': p[0],
                    'name': p[1],
                    'price': p[2],
                    'stock': p[3],
                    'specifications': p[4],
                    'image': p[5],
                    'seller_username': p[6],
                    'store_name': p[7]
                })

        # Best Deals: 3 cheapest products
        cursor.execute("""
            SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
                   p.seller_username, u.store_name
            FROM products p
            JOIN users u ON p.seller_username COLLATE utf8mb4_unicode_ci = u.username COLLATE utf8mb4_unicode_ci
            WHERE p.stock > 0
            ORDER BY p.price ASC
            LIMIT 3
        """)
        best_deals_data = cursor.fetchall()
        if best_deals_data:
            for p in best_deals_data:
                best_deals.append({
                    'id': p[0],
                    'name': p[1],
                    'price': p[2],
                    'stock': p[3],
                    'specifications': p[4],
                    'image': p[5],
                    'seller_username': p[6],
                    'store_name': p[7]
                })
    except Exception as e:
        print(f"Error fetching products: {e}")
        import traceback
        traceback.print_exc()
        products = []
        best_sellers = []
        new_arrivals = []
        best_deals = []
    finally:
        cursor.close()
        conn.close()
    
    return render_template('guest_homepage.html', products=products,
                           best_sellers=best_sellers,
                           new_arrivals=new_arrivals,
                           best_deals=best_deals)

@app.route('/search')
def search_products():
    """Search products by name and category - returns JSON for AJAX"""
    search_query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    sort = request.args.get('sort', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        base_query = """
            SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image, 
                   p.seller_username, u.store_name
            FROM products p
            JOIN users u ON p.seller_username COLLATE utf8mb4_unicode_ci = u.username COLLATE utf8mb4_unicode_ci
            WHERE p.stock > 0
        """

        where_clauses = []
        params = []

        if search_query:
            # Search by product name or specifications
            like_term = f"%{search_query}%"
            where_clauses.append(
                "(p.product_name LIKE %s OR p.specifications LIKE %s "
                "OR u.store_name LIKE %s OR u.username LIKE %s)"
            )
            params.extend([like_term, like_term, like_term, like_term])

        if category:
            category_like = f"%{category}%"
            where_clauses.append(
                "(p.specifications LIKE %s OR p.product_name LIKE %s)"
            )
            params.extend([category_like, category_like])

        if where_clauses:
            base_query += " AND " + " AND ".join(where_clauses)

        if sort == 'price-asc':
            base_query += " ORDER BY p.price ASC"
        elif sort == 'price-desc':
            base_query += " ORDER BY p.price DESC"
        else:
            base_query += " ORDER BY p.created_at DESC"

        cursor.execute(base_query, tuple(params))
        products_data = cursor.fetchall()
        
        products = []
        if products_data:
            for p in products_data:
                products.append({
                    'id': p[0],
                    'name': p[1],
                    'price': float(p[2]) if p[2] else 0,
                    'stock': p[3],
                    'specifications': p[4],
                    'image': p[5],
                    'seller_username': p[6],
                    'store_name': p[7]
                })

        sellers = []
        if search_query:
            seller_like = f"%{search_query}%"
            cursor.execute(
                """
                SELECT u.username, u.store_name, u.store_profile,
                       sa.store_category
                FROM users u
                LEFT JOIN seller_applications sa
                    ON sa.user_id = u.id AND sa.status = 'approved'
                WHERE u.role = 'seller'
                  AND (u.username LIKE %s OR u.store_name LIKE %s)
                GROUP BY u.username, u.store_name, u.store_profile, sa.store_category
                ORDER BY u.store_name IS NULL, u.store_name ASC
                LIMIT 8
                """,
                (seller_like, seller_like),
            )
            seller_rows = cursor.fetchall()
            if seller_rows:
                for s in seller_rows:
                    sellers.append({
                        'username': s[0],
                        'store_name': s[1],
                        'store_profile': s[2],
                        'store_category': s[3],
                    })
        
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
    finally:
        cursor.close()
        conn.close()

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

    # Check MySQL for user/seller
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user:
        # Check if password field is empty or None
        if not user['password']:
            return redirect(url_for('login_page', error='invalid'))
        
        if check_password_hash(user['password'], password):
            # Successful login: reset session and clear any old flash messages
            session['username'] = username
            session['role'] = user['role']
            session['profile_picture'] = user.get('profile_picture')
            session.pop('_flashes', None)

            if user['role'] == 'seller':
                return redirect(url_for('seller_dashboard'))
            elif user['role'] == 'rider':
                return redirect(url_for('rider_homepage'))
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

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Look up user by username (ensures reset targets a single, specific account)
        cursor.execute(
            "SELECT id, email FROM users WHERE username = %s LIMIT 1",
            (username,),
        )
        row = cursor.fetchone()

        if not row:
            return jsonify({'success': False, 'message': 'No account found for that username.'}), 404

        user_id = row[0]
        user_email = row[1]

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
    finally:
        cursor.close()
        conn.close()


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

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hashed = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user_id))
        # Auto-message the seller to inform pickup soon
        try:
            # Resolve usernames
            cursor.execute("SELECT username FROM users WHERE id = %s", (seller_id,))
            seller_row = cursor.fetchone()
            cursor.execute("SELECT username FROM users WHERE id = %s", (customer_id,))
            customer_row = cursor.fetchone()  # not used in message, but kept for potential future context

            seller_username = seller_row[0] if seller_row else None
            rider_username = session.get('username')
            if seller_username and rider_username:
                public_id = format_public_order_id(order_id)
                msg_text = f"Hi! This is {rider_username}. I've accepted order {public_id}. I will pick it up soon."
                cursor.execute(
                    """
                    INSERT INTO chat_messages (sender_username, receiver_username, message_text)
                    VALUES (%s, %s, %s)
                    """,
                    (rider_username, seller_username, msg_text),
                )
        except Exception as me:
            print(f"Warning: failed to auto-message seller for order {order_id}: {me}")

        conn.commit()
        session.pop('password_reset', None)

        return jsonify({'success': True, 'message': 'Your password has been updated. You can now log in with the new password.'})
    except Exception as e:
        print(f"Error in reset_password: {e}")
        return jsonify({'success': False, 'message': 'Failed to update password.'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/signup', methods=['POST'])
def handle_signup():
    username = request.form['username']
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form['email']
    date_of_birth = request.form.get('date_of_birth')
    gender = request.form.get('gender')
    # Address/location fields are now optional at signup; user will set delivery location at checkout.
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

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if username already exists
    cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        cursor.close()
        conn.close()
        return redirect(url_for('login_page', error='username_exists'))
    
    cursor.execute("""
        INSERT INTO users (username, first_name, last_name, email, date_of_birth, gender, 
                          address, city, state_province, postal_code, country, phone, 
                          alternate_phone, latitude, longitude, password, role) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (username, first_name, last_name, email, date_of_birth, gender, 
          address, city, state_province, postal_code, country, phone, 
          alternate_phone, latitude if latitude else None, longitude if longitude else None, 
          password, 'user'))
    conn.commit()
    cursor.close()
    conn.close()

    # Redirect back to login with signup flag for success notification
    return redirect(url_for('login_page', signup='user'))

@app.route('/register_rider', methods=['POST'])
def register_rider():
    """Register a new rider account with basic info. Detailed docs go into rider_applications."""
    username = request.form['rider_username']
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form['email']
    date_of_birth = request.form.get('date_of_birth')
    gender = request.form.get('gender')
    # Address/location fields are optional at signup; riders primarily provide contact and vehicle details.
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

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if username already exists
    cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
    existing_user = cursor.fetchone()
    if existing_user:
        cursor.close()
        conn.close()
        return redirect(url_for('login_page', error='username_exists'))

    cursor.execute(
        """
        INSERT INTO users (username, first_name, last_name, email, date_of_birth, gender,
                          address, city, state_province, postal_code, country, phone,
                          alternate_phone, latitude, longitude, vehicle_type, license_number,
                          password, role, is_approved)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'rider', FALSE)
        """,
        (
            username,
            first_name,
            last_name,
            email,
            date_of_birth,
            gender,
            address,
            city,
            state_province,
            postal_code,
            country,
            phone,
            alternate_phone,
            latitude if latitude else None,
            longitude if longitude else None,
            vehicle_type,
            license_number,
            password,
        ),
    )

    rider_user_id = cursor.lastrowid

    # Handle license image upload (ID card)
    license_image_filename = None
    file = request.files.get('license_image')
    if file and file.filename:
        filename = secure_filename(file.filename)
        docs_root = os.path.join(app.root_path, 'static', 'uploads', 'documents')
        os.makedirs(docs_root, exist_ok=True)
        file.save(os.path.join(docs_root, filename))
        license_image_filename = filename

    # Also create a rider_applications entry for admin review
    full_name = "{} {}".format(first_name or "", last_name or "").strip() or username
    cursor.execute(
        """
        INSERT INTO rider_applications (
            user_id, full_name, address, phone, email,
            vehicle_type, vehicle_registration, license_number, license_image, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """,
        (
            rider_user_id,
            full_name,
            address,
            phone,
            email,
            vehicle_type or '',
            vehicle_registration or '',
            license_number or '',
            license_image_filename,
        ),
    )

    conn.commit()
    cursor.close()
    conn.close()

    # Redirect back to login with signup flag for success notification
    return redirect(url_for('login_page', signup='rider'))

@app.route('/register_seller', methods=['POST'])
def register_seller():
    username = request.form['seller_username']
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form['email']
    date_of_birth = request.form.get('date_of_birth')
    gender = request.form.get('gender')
    # Address/location fields are optional at signup; detailed store info is handled in seller applications.
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

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if username already exists
    cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        cursor.close()
        conn.close()
        return redirect(url_for('login_page', error='username_exists'))
    
    cursor.execute("""
        INSERT INTO users (username, first_name, last_name, email, date_of_birth, gender, 
                          address, city, state_province, postal_code, country, phone, 
                          alternate_phone, latitude, longitude, password, role) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (username, first_name, last_name, email, date_of_birth, gender, 
          address, city, state_province, postal_code, country, phone, 
          alternate_phone, latitude if latitude else None, longitude if longitude else None, 
          password, 'seller'))
    conn.commit()
    cursor.close()
    conn.close()

    # Redirect back to login with signup flag for success notification
    return redirect(url_for('login_page', signup='seller'))

@app.route('/homepage')
def homepage():
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch profile picture
    cursor.execute("SELECT profile_picture FROM users WHERE username = %s", (session['username'],))
    user_data = cursor.fetchone()
    profile_picture = user_data[0] if user_data else None

    products = []
    best_sellers = []
    new_arrivals = []
    best_deals = []

    # Fetch all products from all sellers
    cursor.execute("""
        SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image, 
               p.seller_username, u.store_name
        FROM products p
        JOIN users u ON p.seller_username = u.username
        WHERE p.stock > 0
        ORDER BY p.created_at DESC
    """)
    products_data = cursor.fetchall()

    if products_data:
        for p in products_data:
            products.append({
                'id': p[0],
                'name': p[1],
                'price': p[2],
                'stock': p[3],
                'specifications': p[4],
                'image': p[5],
                'seller_username': p[6],
                'store_name': p[7]
            })

    # ==============================
    # Featured Collections
    # ==============================

    # Best Sellers: top 3 products by total quantity sold
    cursor.execute("""
        SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
               p.seller_username, u.store_name,
               COALESCE(SUM(oi.quantity), 0) AS total_sold
        FROM products p
        JOIN users u ON p.seller_username = u.username
        LEFT JOIN order_items oi ON p.id = oi.product_id
        LEFT JOIN orders o ON oi.order_id = o.id
        WHERE p.stock > 0
        GROUP BY p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
                 p.seller_username, u.store_name
        ORDER BY total_sold DESC
        LIMIT 3
    """)
    best_sellers_data = cursor.fetchall()
    if best_sellers_data:
        for p in best_sellers_data:
            best_sellers.append({
                'id': p[0],
                'name': p[1],
                'price': p[2],
                'stock': p[3],
                'specifications': p[4],
                'image': p[5],
                'seller_username': p[6],
                'store_name': p[7]
            })

    # New Arrivals: 3 most recently added products
    cursor.execute("""
        SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
               p.seller_username, u.store_name
        FROM products p
        JOIN users u ON p.seller_username = u.username
        WHERE p.stock > 0
        ORDER BY p.created_at DESC
        LIMIT 3
    """)
    new_arrivals_data = cursor.fetchall()
    if new_arrivals_data:
        for p in new_arrivals_data:
            new_arrivals.append({
                'id': p[0],
                'name': p[1],
                'price': p[2],
                'stock': p[3],
                'specifications': p[4],
                'image': p[5],
                'seller_username': p[6],
                'store_name': p[7]
            })

    # Best Deals: 3 cheapest products
    cursor.execute("""
        SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
               p.seller_username, u.store_name
        FROM products p
        JOIN users u ON p.seller_username = u.username
        WHERE p.stock > 0
        ORDER BY p.price ASC
        LIMIT 3
    """)
    best_deals_data = cursor.fetchall()
    if best_deals_data:
        for p in best_deals_data:
            best_deals.append({
                'id': p[0],
                'name': p[1],
                'price': p[2],
                'stock': p[3],
                'specifications': p[4],
                'image': p[5],
                'seller_username': p[6],
                'store_name': p[7]
            })

    cursor.close()
    conn.close()

    return render_template('user_homepage.html',
                           profile_picture=profile_picture,
                           products=products,
                           best_sellers=best_sellers,
                           new_arrivals=new_arrivals,
                           best_deals=best_deals)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    """Add product to cart"""
    if 'username' not in session or session.get('role') != 'user':
        return {'success': False, 'message': 'Please login to add items to cart'}, 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get user ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        user_data = cursor.fetchone()
        if not user_data:
            return {'success': False, 'message': 'User not found'}, 404
        
        user_id = user_data[0]
        
        # Check if product exists and has stock
        cursor.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
        product_data = cursor.fetchone()
        if not product_data or product_data[0] <= 0:
            return {'success': False, 'message': 'Product out of stock'}, 400
        
        available_stock = product_data[0]
        
        # Check if item already in cart
        cursor.execute("SELECT id, quantity FROM cart WHERE user_id = %s AND product_id = %s", (user_id, product_id))
        cart_item = cursor.fetchone()
        
        if cart_item:
            # Check if adding one more would exceed stock
            new_quantity = cart_item[1] + 1
            if new_quantity > available_stock:
                return {'success': False, 'message': f'Only {available_stock} items available in stock'}, 400
            cursor.execute("UPDATE cart SET quantity = %s WHERE id = %s", (new_quantity, cart_item[0]))
        else:
            # Insert new cart item
            cursor.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (%s, %s, 1)", (user_id, product_id))
        
        conn.commit()
        
        # Get updated cart count
        cursor.execute("SELECT SUM(quantity) FROM cart WHERE user_id = %s", (user_id,))
        cart_count = cursor.fetchone()[0] or 0
        
        return {'success': True, 'message': 'Item added to cart', 'cart_count': cart_count}, 200
        
    except Exception as e:
        print(f"Error adding to cart: {e}")
        conn.rollback()
        return {'success': False, 'message': 'Error adding item to cart'}, 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_cart_count')
def get_cart_count():
    """Get current cart item count"""
    if 'username' not in session or session.get('role') != 'user':
        return {'cart_count': 0}, 200
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        user_data = cursor.fetchone()
        if not user_data:
            return {'cart_count': 0}, 200
        
        user_id = user_data[0]
        cursor.execute("SELECT SUM(quantity) FROM cart WHERE user_id = %s", (user_id,))
        cart_count = cursor.fetchone()[0] or 0
        
        return {'cart_count': cart_count}, 200
    except Exception as e:
        print(f"Error getting cart count: {e}")
        return {'cart_count': 0}, 200
    finally:
        cursor.close()
        conn.close()

@app.route('/update_cart_quantity/<int:cart_item_id>', methods=['POST'])
def update_cart_quantity(cart_item_id):
    """Update quantity of item in cart"""
    if 'username' not in session or session.get('role') != 'user':
        return {'success': False, 'message': 'Please login'}, 401
    
    data = request.get_json()
    new_quantity = data.get('quantity', 1)
    
    if new_quantity < 1:
        return {'success': False, 'message': 'Quantity must be at least 1'}, 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get user ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        user_data = cursor.fetchone()
        if not user_data:
            return {'success': False, 'message': 'User not found'}, 404
        
        user_id = user_data[0]
        
        # Get cart item and product stock
        cursor.execute("""
            SELECT c.product_id, p.stock 
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.id = %s AND c.user_id = %s
        """, (cart_item_id, user_id))
        cart_data = cursor.fetchone()
        
        if not cart_data:
            return {'success': False, 'message': 'Cart item not found'}, 404
        
        product_id, stock = cart_data
        
        # Check if requested quantity exceeds stock
        if new_quantity > stock:
            return {'success': False, 'message': f'Only {stock} items available in stock'}, 400
        
        # Update quantity
        cursor.execute("UPDATE cart SET quantity = %s WHERE id = %s", (new_quantity, cart_item_id))
        conn.commit()
        
        # Get updated cart count
        cursor.execute("SELECT SUM(quantity) FROM cart WHERE user_id = %s", (user_id,))
        cart_count = cursor.fetchone()[0] or 0
        
        return {'success': True, 'message': 'Quantity updated', 'cart_count': cart_count}, 200
        
    except Exception as e:
        print(f"Error updating cart quantity: {e}")
        conn.rollback()
        return {'success': False, 'message': 'Error updating quantity'}, 500
    finally:
        cursor.close()
        conn.close()

@app.route('/remove_from_cart/<int:cart_item_id>', methods=['POST'])
def remove_from_cart(cart_item_id):
    """Remove item from cart"""
    if 'username' not in session or session.get('role') != 'user':
        return {'success': False, 'message': 'Please login'}, 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get user ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        user_data = cursor.fetchone()
        if not user_data:
            return {'success': False, 'message': 'User not found'}, 404
        
        user_id = user_data[0]
        
        # Delete cart item
        cursor.execute("DELETE FROM cart WHERE id = %s AND user_id = %s", (cart_item_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return {'success': False, 'message': 'Cart item not found'}, 404
        
        # Get updated cart count
        cursor.execute("SELECT SUM(quantity) FROM cart WHERE user_id = %s", (user_id,))
        cart_count = cursor.fetchone()[0] or 0
        
        return {'success': True, 'message': 'Item removed from cart', 'cart_count': cart_count}, 200
        
    except Exception as e:
        print(f"Error removing from cart: {e}")
        conn.rollback()
        return {'success': False, 'message': 'Error removing item'}, 500
    finally:
        cursor.close()
        conn.close()

@app.route('/cart')
def cart():
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get user ID and address
        cursor.execute("SELECT id, profile_picture, address FROM users WHERE username = %s", (session['username'],))
        user_data = cursor.fetchone()
        if not user_data:
            return redirect(url_for('login_page'))
        
        user_id = user_data[0]
        profile_picture = user_data[1]
        shipping_address = user_data[2]
        
        # Fetch cart items with product details
        cursor.execute("""
            SELECT c.id, c.product_id, c.quantity, p.product_name, p.price, p.image, p.stock
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = %s
        """, (user_id,))
        cart_items_data = cursor.fetchall()
        
        cart_items = []
        total = 0
        for item in cart_items_data:
            item_total = item[4] * item[2]  # price * quantity
            total += item_total
            cart_items.append({
                'id': item[0],
                'product_id': item[1],
                'quantity': item[2],
                'name': item[3],
                'price': item[4],
                'image': item[5],
                'stock': item[6],
                'item_total': item_total
            })
        
        return render_template('cart.html', profile_picture=profile_picture, cart_items=cart_items, total=total, shipping_address=shipping_address)
        
    except Exception as e:
        print(f"Error loading cart: {e}")
        return render_template('cart.html', profile_picture=None, cart_items=[], total=0, shipping_address=None)
    finally:
        cursor.close()
        conn.close()

@app.route('/api/check_pending_orders', methods=['GET'])
def api_check_pending_orders():
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT COUNT(*) as pending_count 
            FROM orders 
            WHERE user_id = (SELECT id FROM users WHERE username = %s) 
            AND status IN ('pending', 'processing', 'out_for_delivery')
        """, (session['username'],))
        
        result = cursor.fetchone()
        pending_count = result[0] if result else 0
        
        return jsonify({
            'success': True,
            'has_pending_orders': pending_count > 0,
            'pending_count': pending_count
        })
        
    except Exception as e:
        print(f"Error checking pending orders: {e}")
        return jsonify({'success': False, 'message': 'Error checking orders'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/cancel_order', methods=['POST'])
def api_cancel_order():
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        
        if not order_id:
            return jsonify({'success': False, 'message': 'Order ID is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if order exists and belongs to the user
        cursor.execute("""
            SELECT id, status, user_id 
            FROM orders 
            WHERE id = %s AND user_id = (SELECT id FROM users WHERE username = %s)
        """, (order_id, session['username']))
        
        order = cursor.fetchone()
        
        if not order:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order_db_id, status, user_id = order
        
        # Check if order can be cancelled (only pending orders can be cancelled)
        if status != 'pending':
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Order can only be cancelled when status is pending'}), 400
        
        # Delete the order
        cursor.execute("DELETE FROM orders WHERE id = %s", (order_db_id,))
        
        # Also delete any order items if there's a separate table for them
        cursor.execute("DELETE FROM order_items WHERE order_id = %s", (order_db_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
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
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Double-check for pending orders
        cursor.execute("""
            SELECT COUNT(*) as pending_count 
            FROM orders 
            WHERE user_id = (SELECT id FROM users WHERE username = %s) 
            AND status IN ('pending', 'processing', 'out_for_delivery')
        """, (session['username'],))
        
        result = cursor.fetchone()
        pending_count = result[0] if result else 0
        
        if pending_count > 0:
            return jsonify({
                'success': False, 
                'message': 'Cannot delete account with pending orders'
            }), 400
        
        # Delete user's orders history
        cursor.execute("DELETE FROM orders WHERE user_id = (SELECT id FROM users WHERE username = %s)", (session['username'],))
        
        # Delete user's cart items
        cursor.execute("DELETE FROM cart WHERE user_id = (SELECT id FROM users WHERE username = %s)", (session['username'],))
        
        # Delete user's messages
        cursor.execute("DELETE FROM chat_messages WHERE sender_username = %s OR receiver_username = %s", 
                      (session['username'], session['username']))
        
        # Delete the user
        cursor.execute("DELETE FROM users WHERE username = %s", (session['username'],))
        
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Account deleted successfully'
        })
        
    except Exception as e:
        print(f"Error deleting account: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Error deleting account'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/verify_current_password', methods=['POST'])
def api_verify_current_password():
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    current_password = data.get('current_password', '')
    
    if not current_password:
        return jsonify({'success': False, 'message': 'Current password is required'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT password FROM users WHERE username = %s", (session['username'],))
        user_data = cursor.fetchone()
        
        if not user_data:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        stored_password = user_data[0]
        
        # Verify password (assuming plain text for now, should use bcrypt in production)
        if current_password == stored_password:
            return jsonify({'success': True, 'message': 'Password verified'})
        else:
            return jsonify({'success': False, 'message': 'Incorrect password'})
            
    except Exception as e:
        print(f"Error verifying password: {e}")
        return jsonify({'success': False, 'message': 'Error verifying password'}), 500
    finally:
        cursor.close()
        conn.close()

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
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Reverse geocoding to get place name first
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
        
        # Update user's location in database
        cursor.execute("""
            UPDATE users 
            SET latitude = %s, longitude = %s, address = %s 
            WHERE username = %s
        """, (latitude, longitude, address, session['username']))
        
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': 'Location updated successfully',
            'address': address
        })
        
    except Exception as e:
        print(f"Error updating location: {e}")
        return jsonify({'success': False, 'message': 'Failed to update location'}), 500

@app.route('/rider/profile')
def rider_profile():
    if 'username' not in session or session.get('role') != 'rider':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT username, email, address, phone, profile_picture, created_at
        FROM users WHERE username = %s
    """, (session['username'],))
    user_data = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if user_data:
        user_info = {
            'username': user_data[0],
            'email': user_data[1],
            'address': user_data[2],
            'phone': user_data[3],
            'profile_picture': user_data[4],
            'created_at': user_data[5]
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
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current user data
    cursor.execute("SELECT username_edited, profile_picture FROM users WHERE username = %s", (session['username'],))
    current_data = cursor.fetchone()
    username_edited = current_data[0] if current_data and len(current_data) > 0 else False
    old_profile_picture = current_data[1] if current_data and len(current_data) > 1 else None
    
    # Check if this is an AJAX request for profile picture update
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'profile_picture' in request.files:
        # Handle profile picture upload only
        file = request.files['profile_picture']
        if file and file.filename:
            # Validate file
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            filename = file.filename
            if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                # Generate unique filename
                import uuid
                ext = filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{session['username']}_{uuid.uuid4().hex[:8]}.{ext}"
                
                # Save file
                upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')
                os.makedirs(upload_folder, exist_ok=True)
                file_path = os.path.join(upload_folder, unique_filename)
                file.save(file_path)
                
                # Delete old profile picture if exists
                if old_profile_picture:
                    old_filepath = os.path.join(upload_folder, old_profile_picture)
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)
                
                # Update database
                cursor.execute("UPDATE users SET profile_picture = %s WHERE username = %s", 
                              (unique_filename, session['username']))
                # Update session so nav dropdown reflects new picture
                session['profile_picture'] = unique_filename
                
                conn.commit()
                cursor.close()
                conn.close()
                
                return jsonify({
                    'success': True, 
                    'message': 'Profile picture updated successfully',
                    'profile_picture': unique_filename
                })
            else:
                return jsonify({'success': False, 'message': 'Invalid file type'}), 400
        else:
            return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    # Handle username update (only if not edited before)
    new_username = request.form.get('username')
    if new_username and new_username != session['username'] and not username_edited:
        # Check if new username already exists
        cursor.execute("SELECT username FROM users WHERE username = %s", (new_username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect(url_for('profile') + '?error=username_exists')
        
        # Update username and mark as edited
        cursor.execute("UPDATE users SET username = %s, username_edited = TRUE WHERE username = %s", 
                      (new_username, session['username']))
        session['username'] = new_username
    
    # Handle profile picture upload
    if 'profile_picture' in request.files:
        file = request.files['profile_picture']
        if file and file.filename:
            # Validate file
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            filename = file.filename
            if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                # Generate unique filename
                import uuid
                ext = filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{session['username']}_{uuid.uuid4().hex[:8]}.{ext}"
                
                # Save file
                upload_folder = os.path.join('static', 'uploads', 'profiles')
                os.makedirs(upload_folder, exist_ok=True)
                filepath = os.path.join(upload_folder, unique_filename)
                file.save(filepath)
                
                # Delete old profile picture if exists
                if old_profile_picture:
                    old_filepath = os.path.join(upload_folder, old_profile_picture)
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)
                
                # Update database
                cursor.execute("UPDATE users SET profile_picture = %s WHERE username = %s", 
                              (unique_filename, session['username']))
                # Update session so nav dropdown reflects new picture
                session['profile_picture'] = unique_filename
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('profile'))

@app.route('/settings')
def settings():
    if 'username' not in session or session.get('role') != 'user':
        return redirect(url_for('login_page'))
    
    # Fetch user data
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username, email, first_name, last_name, phone, profile_picture, created_at, address, latitude, longitude
        FROM users WHERE username = %s
    """, (session['username'],))
    user_data = cursor.fetchone()
    
    # Fetch user's order statistics
    cursor.execute("""
        SELECT COUNT(*) as total_orders,
               SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_orders
        FROM orders WHERE user_id = (SELECT id FROM users WHERE username = %s)
    """, (session['username'],))
    order_stats = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if user_data:
        # Combine first_name and last_name to create full_name
        first_name = user_data[2] or ''
        last_name = user_data[3] or ''
        full_name = f"{first_name} {last_name}".strip()
        
        user_info = {
            'username': user_data[0],
            'email': user_data[1],
            'full_name': full_name,
            'phone': user_data[4],
            'profile_picture': user_data[5],
            'created_at': user_data[6],
            'address': user_data[7],
            'latitude': user_data[8],
            'longitude': user_data[9],
            'total_orders': order_stats[0] if order_stats else 0,
            'delivered_orders': order_stats[1] if order_stats else 0
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

    admin_username = 'admin'
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE role = 'admin' ORDER BY id ASC LIMIT 1")
        row = cursor.fetchone()
        if row and row[0]:
            admin_username = row[0]
        cursor.close(); conn.close()
    except Exception:
        try:
            cursor.close(); conn.close()
        except Exception:
            pass

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

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_approved FROM users WHERE username = %s", (session['username'],))
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    is_approved = result[0] if result and result[0] is not None else False
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
    return redirect(url_for('login_page'))

# ============================================================================
# SELLER DASHBOARD ROUTES
# ============================================================================

@app.route('/seller-dashboard')
def seller_dashboard():
    """Seller dashboard with application check"""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    
    # Check if seller has completed application
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT seller_approved FROM users WHERE username = %s", (session['username'],))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    seller_approved = result[0] if result and result[0] is not None else False
    # Determine latest application status for this seller
    application_status = None
    application_submitted_at = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        u = cursor.fetchone()
        if u:
            user_id = u[0]
            try:
                cursor.execute(
                    """
                    SELECT status, created_at
                    FROM seller_applications
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
                row = cursor.fetchone()
                if row:
                    application_status = row[0]
                    created_at = row[1] if len(row) > 1 else None
                    if created_at is not None:
                        application_submitted_at = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
            except Exception:
                # Fallback if created_at column does not exist
                cursor.execute(
                    """
                    SELECT status
                    FROM seller_applications
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
                row = cursor.fetchone()
                if row:
                    application_status = row[0]
        cursor.close()
        conn.close()
    except Exception:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

    return render_template('seller_dashboard.html', seller_approved=seller_approved, application_status=application_status, application_submitted_at=application_submitted_at)

@app.route('/seller/messages')
def seller_messages():
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT seller_approved FROM users WHERE username = %s", (session['username'],))
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    seller_approved = result[0] if result and result[0] is not None else False

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
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, sender_username, receiver_username, message_text, created_at, is_read
            FROM chat_messages
            WHERE sender_username = %s OR receiver_username = %s
            ORDER BY created_at DESC, id DESC
            """,
            (username, username),
        )
        rows = cursor.fetchall()

        conversations = {}
        order = []
        for row in rows:
            msg_id, sender, receiver, text, created_at, is_read = row
            other = receiver if sender == username else sender

            if other not in conversations:
                # Get profile picture for the other user (handle missing columns gracefully)
                try:
                    cursor.execute(
                        """
                        SELECT profile_picture, last_seen, is_online 
                        FROM users 
                        WHERE username = %s
                        """, 
                        (other,)
                    )
                    user_data = cursor.fetchone()
                    profile_picture = user_data[0] if user_data else None
                    last_seen = user_data[1] if user_data and len(user_data) > 1 else None
                    is_online = user_data[2] if user_data and len(user_data) > 2 else False
                except Exception as e:
                    # Fallback if columns don't exist
                    cursor.execute("SELECT profile_picture FROM users WHERE username = %s", (other,))
                    user_data = cursor.fetchone()
                    profile_picture = user_data[0] if user_data else None
                    last_seen = None
                    is_online = False

                conversations[other] = {
                    'other_username': other,
                    'profile_picture': profile_picture,
                    'is_online': bool(is_online),
                    'last_seen': last_seen.isoformat() if last_seen else None,
                    'last_message': text,
                    'last_message_time': created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at),
                    'unread_count': 0,
                }
                order.append(other)

            # Update last message if this message is newer
            current_time = created_at
            existing_time = conversations[other]['last_message_time']
            if isinstance(existing_time, str):
                from datetime import datetime
                existing_time = datetime.fromisoformat(existing_time.replace('Z', '+00:00') if existing_time.endswith('Z') else existing_time)
            if current_time > existing_time:
                conversations[other]['last_message'] = text
                conversations[other]['last_message_time'] = current_time.isoformat() if hasattr(current_time, 'isoformat') else str(current_time)

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
    finally:
        cursor.close()
        conn.close()
@app.route('/api/messages/thread/<username>')
def api_message_thread(username):
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    current_username = session['username']
    other_username = username

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, sender_username, receiver_username, message_text, created_at
            FROM chat_messages
            WHERE (sender_username = %s AND receiver_username = %s)
               OR (sender_username = %s AND receiver_username = %s)
            ORDER BY created_at ASC, id ASC
            """,
            (current_username, other_username, other_username, current_username),
        )
        rows = cursor.fetchall()

        messages = []
        for row in rows:
            msg_id, sender, receiver, text, created_at = row
            messages.append(
                {
                    'id': msg_id,
                    'sender_username': sender,
                    'receiver_username': receiver,
                    'message_text': text,
                    'created_at': created_at.isoformat()
                    if hasattr(created_at, 'isoformat')
                    else str(created_at),
                }
            )

        cursor.execute(
            """
            UPDATE chat_messages
            SET is_read = TRUE
            WHERE sender_username = %s AND receiver_username = %s AND is_read = FALSE
            """,
            (other_username, current_username),
        )
        conn.commit()

        return jsonify({'success': True, 'messages': messages}), 200
    except Exception as e:
        print(f"Error loading message thread: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Error loading messages'}), 500
    finally:
        cursor.close()
        conn.close()


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

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT username FROM users WHERE username = %s", (receiver,)
        )
        if not cursor.fetchone():
            return jsonify(
                {'success': False, 'message': 'Receiver not found.'}
            ), 404

        cursor.execute(
            """
            INSERT INTO chat_messages (sender_username, receiver_username, message_text)
            VALUES (%s, %s, %s)
            """,
            (sender, receiver, text),
        )
        message_id = cursor.lastrowid

        cursor.execute(
            """
            SELECT id, sender_username, receiver_username, message_text, created_at
            FROM chat_messages
            WHERE id = %s
            """,
            (message_id,),
        )
        row = cursor.fetchone()
        conn.commit()

        if not row:
            return jsonify({'success': True, 'message': None}), 200

        msg = {
            'id': row[0],
            'sender_username': row[1],
            'receiver_username': row[2],
            'message_text': row[3],
            'created_at': row[4].isoformat()
            if hasattr(row[4], 'isoformat')
            else str(row[4]),
        }

        return jsonify({'success': True, 'message': msg}), 200
    except Exception as e:
        print(f"Error sending message: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Error sending message.'}), 500
    finally:
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
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user ID
    cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
    user_result = cursor.fetchone()
    if not user_result:
        flash('User not found', 'error')
        return redirect(url_for('seller_dashboard'))
    user_id = user_result[0]
    
    # Handle file uploads
    upload_folder = os.path.join('static', 'uploads', 'documents')
    os.makedirs(upload_folder, exist_ok=True)
    
    business_permit_filename = None
    valid_id_filename = None
    
    if 'business_permit' in request.files:
        file = request.files['business_permit']
        if file and file.filename:
            import uuid
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'pdf'
            business_permit_filename = f"{session['username']}_permit_{uuid.uuid4().hex[:8]}.{ext}"
            file.save(os.path.join(upload_folder, business_permit_filename))
    
    if 'valid_id' in request.files:
        file = request.files['valid_id']
        if file and file.filename:
            import uuid
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'pdf'
            valid_id_filename = f"{session['username']}_id_{uuid.uuid4().hex[:8]}.{ext}"
            file.save(os.path.join(upload_folder, valid_id_filename))
    
    # Insert into seller_applications table
    cursor.execute("""
        INSERT INTO seller_applications 
        (user_id, store_name, store_description, store_category, store_phone, business_permit, valid_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
    """, (user_id, store_name, store_description, store_category, store_phone, business_permit_filename, valid_id_filename))
    
    # Update user record with store name (but don't approve yet)
    cursor.execute("""
        UPDATE users 
        SET store_name = %s
        WHERE username = %s
    """, (store_name, session['username']))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Your seller application has been submitted successfully! Please wait for admin approval.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/my-profile', methods=['GET', 'POST'])
def my_profile():
    """Seller profile route with database integration"""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        # Update editable profile fields (username, street address, and location remain unchanged here)
        first_name = request.form.get('first_name') or None
        last_name = request.form.get('last_name') or None
        birthdate = request.form.get('birthdate') or None
        gender = request.form.get('gender') or None
        phone = request.form.get('phone') or None
        alternate_phone = request.form.get('alternate_phone') or None
        city = request.form.get('city') or None
        state_province = request.form.get('state_province') or None
        postal_code = request.form.get('postal_code') or None
        country = request.form.get('country') or None
        store_name = request.form.get('store_name') or None

        cursor.execute("""
            UPDATE users SET
                first_name = %s,
                last_name = %s,
                date_of_birth = %s,
                gender = %s,
                phone = %s,
                alternate_phone = %s,
                city = %s,
                state_province = %s,
                postal_code = %s,
                country = %s,
                store_name = %s
            WHERE username = %s
        """, (
            first_name,
            last_name,
            birthdate,
            gender,
            phone,
            alternate_phone,
            city,
            state_province,
            postal_code,
            country,
            store_name,
            session['username']
        ))

        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                filename = file.filename
                if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    import uuid
                    ext = filename.rsplit('.', 1)[1].lower()
                    unique_filename = f"{session['username']}_{uuid.uuid4().hex[:8]}.{ext}"
                    
                    upload_folder = os.path.join('static', 'uploads', 'profiles')
                    os.makedirs(upload_folder, exist_ok=True)
                    filepath = os.path.join(upload_folder, unique_filename)
                    file.save(filepath)
                    # Also copy to profiles folder so header/profile uses correct path
                    profiles_folder = os.path.join('static', 'uploads', 'profiles')
                    os.makedirs(profiles_folder, exist_ok=True)
                    try:
                        shutil.copyfile(filepath, os.path.join(profiles_folder, unique_filename))
                    except Exception:
                        pass
                    
                    # Delete old profile picture if exists
                    cursor.execute("SELECT profile_picture FROM users WHERE username = %s", (session['username'],))
                    old_pic = cursor.fetchone()
                    if old_pic and old_pic[0]:
                        old_filepath = os.path.join(upload_folder, old_pic[0])
                        if os.path.exists(old_filepath):
                            os.remove(old_filepath)
                    
                    cursor.execute("UPDATE users SET profile_picture = %s WHERE username = %s", 
                                  (unique_filename, session['username']))
                    # Keep session in sync so navbar dropdown shows latest image
                    session['profile_picture'] = unique_filename
        
        conn.commit()
        flash('Profile updated successfully!', 'success')
        cursor.close()
        conn.close()
        return redirect(url_for('my_profile'))
    
    # Fetch seller data
    cursor.execute("""
        SELECT username, email, first_name, last_name, date_of_birth, gender, 
               address, city, state_province, postal_code, country, phone, 
               alternate_phone, latitude, longitude, profile_picture, store_name,
               seller_approved
        FROM users WHERE username = %s
    """, (session['username'],))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user_data:
        seller_info = {
            'username': user_data[0],
            'email': user_data[1],
            'first_name': user_data[2],
            'last_name': user_data[3],
            'date_of_birth': user_data[4],
            'gender': user_data[5],
            'address': user_data[6],
            'city': user_data[7],
            'state_province': user_data[8],
            'postal_code': user_data[9],
            'country': user_data[10],
            'phone': user_data[11],
            'alternate_phone': user_data[12],
            'latitude': user_data[13],
            'longitude': user_data[14],
            'profile_picture': user_data[15],
            'store_name': user_data[16]
        }
        seller_approved = bool(user_data[17])
    else:
        seller_info = {
            'username': session.get('username', 'N/A'),
            'email': 'N/A',
            'first_name': None,
            'last_name': None,
            'date_of_birth': None,
            'gender': None,
            'address': None,
            'city': None,
            'state_province': None,
            'postal_code': None,
            'country': 'Philippines',
            'phone': None,
            'alternate_phone': None,
            'latitude': None,
            'longitude': None,
            'profile_picture': None,
            'store_name': None
        }
        seller_approved = False
    
    application_status = None
    application_submitted_at = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        u = cursor.fetchone()
        if u:
            user_id = u[0]
            try:
                cursor.execute(
                    """
                    SELECT status, created_at
                    FROM seller_applications
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
                row = cursor.fetchone()
                if row:
                    application_status = row[0]
                    created_at = row[1] if len(row) > 1 else None
                    if created_at is not None:
                        application_submitted_at = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
            except Exception:
                cursor.execute(
                    """
                    SELECT status
                    FROM seller_applications
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
                row = cursor.fetchone()
                if row:
                    application_status = row[0]
        cursor.close()
        conn.close()
    except Exception:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

    # Compute seller product and order counts
    product_count = 0
    order_count = 0
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Get seller id
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        u = cursor.fetchone()
        seller_id = u[0] if u else None
        # Count products by seller_username
        cursor.execute("SELECT COUNT(*) FROM products WHERE seller_username = %s", (session['username'],))
        pc = cursor.fetchone()
        if pc and pc[0] is not None:
            product_count = int(pc[0])
        # Count orders linked to this seller
        if seller_id is not None:
            cursor.execute("SELECT COUNT(*) FROM orders WHERE seller_id = %s", (seller_id,))
            oc = cursor.fetchone()
            if oc and oc[0] is not None:
                order_count = int(oc[0])
        cursor.close()
        conn.close()
    except Exception:
        try:
            cursor.close(); conn.close()
        except Exception:
            pass

    return render_template('my_profile.html', seller=seller_info, seller_approved=seller_approved, application_status=application_status, application_submitted_at=application_submitted_at, product_count=product_count, order_count=order_count)

@app.route('/store/preview', methods=['GET', 'POST'])
def store_preview():
    """Store preview route with photo upload and About text editing"""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if seller is approved and get user id
    cursor.execute("SELECT id, seller_approved FROM users WHERE username = %s", (session['username'],))
    result = cursor.fetchone()
    if not result:
        cursor.close()
        conn.close()
        flash('Seller account not found.', 'error')
        return redirect(url_for('login_page'))

    user_id = result[0]
    seller_approved = result[1] if result[1] is not None else False
    
    if not seller_approved:
        cursor.close()
        conn.close()
        flash('Your seller application is pending approval. You cannot access your store yet.', 'warning')
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        # Handle store photo uploads (hidden form)
        upload_folder = os.path.join('static', 'uploads', 'store')
        os.makedirs(upload_folder, exist_ok=True)

        photos_updated = False
        
        # Handle cover photo
        if 'cover_photo' in request.files:
            file = request.files['cover_photo']
            if file and file.filename:
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                filename = file.filename
                if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    import uuid
                    ext = filename.rsplit('.', 1)[1].lower()
                    unique_filename = f"{session['username']}_cover_{uuid.uuid4().hex[:8]}.{ext}"
                    filepath = os.path.join(upload_folder, unique_filename)
                    file.save(filepath)
                    
                    # Delete old cover photo if exists
                    cursor.execute("SELECT cover_photo FROM users WHERE username = %s", (session['username'],))
                    old_pic = cursor.fetchone()
                    if old_pic and old_pic[0]:
                        old_filepath = os.path.join(upload_folder, old_pic[0])
                        if os.path.exists(old_filepath):
                            os.remove(old_filepath)
                    
                    cursor.execute("UPDATE users SET cover_photo = %s WHERE username = %s", 
                                  (unique_filename, session['username']))
                    photos_updated = True
        
        # Handle store profile photo
        if 'store_profile' in request.files:
            file = request.files['store_profile']
            if file and file.filename:
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                filename = file.filename
                if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    import uuid
                    ext = filename.rsplit('.', 1)[1].lower()
                    unique_filename = f"{session['username']}_store_{uuid.uuid4().hex[:8]}.{ext}"
                    filepath = os.path.join(upload_folder, unique_filename)
                    file.save(filepath)
                    
                    # Delete old store profile if exists
                    cursor.execute("SELECT store_profile FROM users WHERE username = %s", (session['username'],))
                    old_pic = cursor.fetchone()
                    if old_pic and old_pic[0]:
                        old_filepath = os.path.join(upload_folder, old_pic[0])
                        if os.path.exists(old_filepath):
                            os.remove(old_filepath)
                    
                    # Update both store_profile and profile_picture to keep them in sync
                    cursor.execute("UPDATE users SET store_profile = %s, profile_picture = %s WHERE username = %s", 
                                  (unique_filename, unique_filename, session['username']))
                    # Keep session in sync so dropdown/header shows latest image
                    session['profile_picture'] = unique_filename
                    photos_updated = True

        # Handle About text edits (About form)
        about_text = request.form.get('about_text')
        about_updated = False
        if about_text is not None:
            cursor.execute(
                """
                UPDATE seller_applications
                SET store_description = %s
                WHERE user_id = %s AND status = 'approved'
                """,
                (about_text, user_id)
            )
            about_updated = True

        conn.commit()

        if about_updated and photos_updated:
            flash('Store photos and About section updated.', 'success')
        elif about_updated:
            flash('Store About section updated.', 'success')
        elif photos_updated:
            flash('Store photos updated successfully!', 'success')

        cursor.close()
        conn.close()
        return redirect(url_for('store_preview'))
    
    # Fetch store data, including latest approved description
    cursor.execute(
        """
        SELECT 
            u.store_name,
            u.cover_photo,
            u.store_profile,
            (
                SELECT sa.store_description
                FROM seller_applications sa
                WHERE sa.user_id = u.id AND sa.status = 'approved'
                ORDER BY sa.created_at DESC
                LIMIT 1
            ) AS store_description
        FROM users u
        WHERE u.id = %s
        """,
        (user_id,)
    )
    store_data = cursor.fetchone()
    
    # Fetch products for this seller
    cursor.execute("""
        SELECT id, product_name, price, stock, specifications, image
        FROM products WHERE seller_username = %s
        ORDER BY created_at DESC
    """, (session['username'],))
    products_data = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    store = {
        'name': store_data[0] if store_data and store_data[0] else 'My Store',
        'cover_photo': store_data[1] if store_data and store_data[1] else None,
        'store_profile': store_data[2] if store_data and store_data[2] else None,
        'description': store_data[3] if store_data and len(store_data) > 3 and store_data[3] else None
    }
    
    products = []
    if products_data:
        for p in products_data:
            products.append({
                'id': p[0],
                'name': p[1],
                'price': p[2],
                'stock': p[3],
                'specifications': p[4],
                'image': p[5]
            })
    
    return render_template('store_preview.html', store=store, products=products, seller_approved=seller_approved)

@app.route('/add_product', methods=['POST'])
def add_product():
    """Handle adding new product with support for multiple images and a thumbnail."""
    if 'username' not in session or session.get('role') != 'seller':
        return redirect(url_for('login_page'))

    product_name = request.form.get('product_name')
    price = request.form.get('price')
    stock = request.form.get('stock')
    specifications = request.form.get('specifications')

    conn = get_db_connection()
    cursor = conn.cursor()

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
        import uuid
        new_filename = f"{session['username']}_product_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = os.path.join(upload_folder, new_filename)
        file.save(filepath)
        saved_filenames.append(new_filename)

    image_filename = saved_filenames[0] if saved_filenames else None

    thumb_raw = request.form.get('thumbnail_index')
    try:
        thumb_index = int(thumb_raw) if thumb_raw is not None else 0
    except (TypeError, ValueError):
        thumb_index = 0
    if thumb_index < 0 or thumb_index >= len(saved_filenames):
        thumb_index = 0
    if saved_filenames:
        image_filename = saved_filenames[thumb_index]

    cursor.execute("""
        INSERT INTO products (seller_username, product_name, price, stock, specifications, image)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (session['username'], product_name, price, stock, specifications, image_filename))

    product_id = cursor.lastrowid

    if saved_filenames:
        for idx, filename in enumerate(saved_filenames):
            is_thumbnail = idx == thumb_index
            cursor.execute(
                """
                INSERT INTO product_images (product_id, filename, is_thumbnail, sort_order)
                VALUES (%s, %s, %s, %s)
                """,
                (product_id, filename, is_thumbnail, idx),
            )

    conn.commit()
    cursor.close()
    conn.close()

    flash('Product added successfully!', 'success')
    return redirect(url_for('store_preview'))


@app.route('/seller/products/bulk-delete', methods=['POST'])
def bulk_delete_products():
    """Bulk delete products for the logged-in seller."""
    if 'username' not in session or session.get('role') != 'seller':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json() or {}
    raw_ids = data.get('product_ids', [])

    if not isinstance(raw_ids, list):
        return jsonify({'success': False, 'message': 'Invalid payload'}), 400

    # Sanitize IDs to integers
    product_ids = []
    for pid in raw_ids:
        try:
            product_ids.append(int(pid))
        except (TypeError, ValueError):
            continue

    if not product_ids:
        return jsonify({'success': False, 'message': 'No valid product IDs provided'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        placeholders = ','.join(['%s'] * len(product_ids))
        query = f"""
            DELETE FROM products
            WHERE id IN ({placeholders}) AND seller_username = %s
        """
        params = (*product_ids, session['username'])
        cursor.execute(query, params)
        deleted_count = cursor.rowcount
        conn.commit()
        return jsonify({'success': True, 'deleted_count': deleted_count}), 200
    except Exception as e:
        print(f"Error deleting products for seller {session.get('username')}: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Error deleting products'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page accessible by guests, buyers, and sellers"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch product details with seller information
    cursor.execute("""
        SELECT p.id, p.product_name, p.price, p.stock, p.specifications, p.image,
               p.seller_username, p.created_at,
               u.store_name, u.first_name, u.last_name, u.store_profile
        FROM products p
        JOIN users u ON p.seller_username = u.username
        WHERE p.id = %s
    """, (product_id,))
    product_data = cursor.fetchone()
    
    if not product_data:
        cursor.close()
        conn.close()
        flash('Product not found', 'error')
        # Redirect based on user status
        if 'username' in session:
            return redirect(url_for('homepage') if session.get('role') == 'user' else url_for('store_preview'))
        else:
            return redirect(url_for('guest_home'))

    product = {
        'id': product_data[0],
        'name': product_data[1],
        'price': product_data[2],
        'stock': product_data[3],
        'specifications': product_data[4],
        'image': product_data[5],
        'seller_username': product_data[6],
        'created_at': product_data[7],
        'store_name': product_data[8] or f"{product_data[9]} {product_data[10]}",
        'store_profile': product_data[11]
    }

    profile_picture = None
    if 'username' in session:
        cursor.execute("SELECT profile_picture FROM users WHERE username = %s", (session['username'],))
        user_data = cursor.fetchone()
        profile_picture = user_data[0] if user_data else None

    cursor.execute(
        """
        SELECT id, filename, is_thumbnail, sort_order
        FROM product_images
        WHERE product_id = %s
        ORDER BY is_thumbnail DESC, sort_order ASC, id ASC
        """,
        (product_id,),
    )
    images_data = cursor.fetchall()

    cursor.close()
    conn.close()

    images = []
    if images_data:
        for row in images_data:
            images.append(
                {
                    'id': row[0],
                    'filename': row[1],
                    'is_thumbnail': bool(row[2]),
                    'sort_order': row[3],
                }
            )
    elif product.get('image'):
        images.append(
            {
                'id': None,
                'filename': product['image'],
                'is_thumbnail': True,
                'sort_order': 0,
            }
        )

    is_guest = 'username' not in session
    is_seller = session.get('role') == 'seller' if 'username' in session else False
    is_owner = session.get('username') == product['seller_username'] if 'username' in session else False

    avg_rating = 0.0
    total_reviews = 0
    user_can_review = False

    with app.app_context():
        try:
            avg_rating = db.session.query(db.func.avg(Review.rating)).filter(
                Review.product_id == product_id,
                Review.status == 'approved'
            ).scalar() or 0.0
            total_reviews = db.session.query(db.func.count(Review.id)).filter(
                Review.product_id == product_id,
                Review.status == 'approved'
            ).scalar() or 0
        except Exception as e:
            print(f"Error computing review summary for product {product_id}: {e}")
            avg_rating = 0.0
            total_reviews = 0

    if not is_guest and session.get('role') == 'user':
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM orders o
                JOIN order_items oi ON o.id = oi.order_id
                JOIN products p ON oi.product_id = p.id
                JOIN users u ON o.user_id = u.id
                WHERE o.status = 'delivered'
                  AND oi.product_id = %s
                  AND u.username = %s
                """,
                (product_id, session['username']),
            )
            count = cursor.fetchone()[0] or 0
            user_can_review = count > 0
        except Exception as e:
            print(f"Error checking review eligibility for product {product_id}: {e}")
            user_can_review = False
        finally:
            cursor.close()
            conn.close()

    return render_template(
        'product_detail.html',
        product=product,
        profile_picture=profile_picture,
        is_seller=is_seller,
        is_owner=is_owner,
        is_guest=is_guest,
        images=images,
        avg_rating=round(float(avg_rating), 1) if avg_rating else 0.0,
        total_reviews=total_reviews,
        user_can_review=user_can_review,
    )


@app.route('/product/<int:product_id>/reviews')
def get_product_reviews(product_id):
    """Return reviews summary and list for a product as JSON."""
    with app.app_context():
        try:
            avg_rating = db.session.query(db.func.avg(Review.rating)).filter(
                Review.product_id == product_id,
                Review.status == 'approved'
            ).scalar() or 0.0
            total = db.session.query(db.func.count(Review.id)).filter(
                Review.product_id == product_id,
                Review.status == 'approved'
            ).scalar() or 0

            review_rows = (
                Review.query
                .filter_by(product_id=product_id, status='approved')
                .order_by(Review.created_at.desc())
                .all()
            )

            reviews_payload = []
            for r in review_rows:
                photos = [p.filename for p in (r.photos or [])]
                reviews_payload.append({
                    'id': r.id,
                    'customer_name': r.customer_name,
                    'rating': r.rating,
                    'comment': r.comment,
                    'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                    'photos': photos,
                })

            return jsonify({
                'success': True,
                'avg_rating': round(float(avg_rating), 1) if avg_rating else 0.0,
                'total_reviews': total,
                'reviews': reviews_payload,
            }), 200
        except Exception as e:
            print(f"Error loading reviews for product {product_id}: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/product/<int:product_id>/reviews', methods=['POST'])
def submit_product_review(product_id):
    """Submit a new review for a product. Only delivered buyers can review."""
    if 'username' not in session or session.get('role') != 'user':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    rating = int(request.form.get('rating', '0') or 0)
    comment = (request.form.get('comment') or '').strip()

    if rating < 1 or rating > 5:
        return jsonify({'success': False, 'error': 'Rating must be between 1 and 5.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT u.id
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            JOIN users u ON o.user_id = u.id
            WHERE o.status = 'delivered'
              AND oi.product_id = %s
              AND u.username = %s
            LIMIT 1
            """,
            (product_id, session['username']),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'You can only review products you have received.'}), 403

        user_id = row[0]
    except Exception as e:
        print(f"Error checking review eligibility (submit) for product {product_id}: {e}")
        return jsonify({'success': False, 'error': 'Eligibility check failed.'}), 500
    finally:
        cursor.close()
        conn.close()

    with app.app_context():
        try:
            customer_name = session.get('username')

            review = Review(
                product_id=product_id,
                customer_name=customer_name,
                rating=rating,
                comment=comment,
                status='approved',
            )
            db.session.add(review)
            db.session.flush()

            files = request.files.getlist('photos') or []
            reviews_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'reviews')
            os.makedirs(reviews_upload_dir, exist_ok=True)

            for f in files:
                if not f or not f.filename:
                    continue
                filename = secure_filename(f.filename)
                base, ext = os.path.splitext(filename)
                if ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif']:
                    continue
                unique_name = f"review_{product_id}_{int(time.time())}_{random.randint(1000,9999)}{ext.lower()}"
                filepath = os.path.join(reviews_upload_dir, unique_name)
                f.save(filepath)

                photo = ReviewPhoto(review_id=review.id, filename=unique_name)
                db.session.add(photo)

            db.session.commit()

            return jsonify({'success': True}), 201
        except Exception as e:
            print(f"Error saving review for product {product_id}: {e}")
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Failed to save review.'}), 500


@app.route('/store/<seller_username>')
def public_store(seller_username):
    """Public store profile page for a seller, visible to guests and logged-in users."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Fetch basic seller store info
        cursor.execute(
            """
            SELECT id, store_name, cover_photo, store_profile, seller_approved
            FROM users
            WHERE username = %s AND role = 'seller'
            """,
            (seller_username,),
        )
        row = cursor.fetchone()

        if not row:
            return render_template('store_public.html', store=None, products=[], not_found=True), 404

        user_id, store_name, cover_photo, store_profile, seller_approved = row

        # Only show approved stores publicly
        if not seller_approved:
            return render_template('store_public.html', store=None, products=[], not_found=True), 404

        # Get latest approved store description from seller applications
        cursor.execute(
            """
            SELECT sa.store_description
            FROM seller_applications sa
            WHERE sa.user_id = %s AND sa.status = 'approved'
            ORDER BY sa.created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        desc_row = cursor.fetchone()
        description = desc_row[0] if desc_row and desc_row[0] else None

        # Fetch products for this seller (only in-stock items)
        cursor.execute(
            """
            SELECT id, product_name, price, stock, specifications, image
            FROM products
            WHERE seller_username = %s AND stock > 0
            ORDER BY created_at DESC
            """,
            (seller_username,),
        )
        products_data = cursor.fetchall()

        store = {
            'username': seller_username,
            'name': store_name or f"{seller_username}'s Store",
            'cover_photo': cover_photo,
            'store_profile': store_profile,
            'description': description,
        }

        products = []
        if products_data:
            for p in products_data:
                products.append(
                    {
                        'id': p[0],
                        'name': p[1],
                        'price': p[2],
                        'stock': p[3],
                        'specifications': p[4],
                        'image': p[5],
                    }
                )

        return render_template('store_public.html', store=store, products=products, not_found=False)
    except Exception as e:
        print(f"Error loading public store for {seller_username}: {e}")
        return render_template('store_public.html', store=None, products=[], error=str(e), not_found=True), 500
    finally:
        cursor.close()
        conn.close()

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

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status, COUNT(*)
        FROM seller_applications
        GROUP BY status
    """)
    rows = cursor.fetchall()

    pending_count = 0
    approved_count = 0
    rejected_count = 0

    for status, count in rows:
        if status == 'pending':
            pending_count = count
        elif status == 'approved':
            approved_count = count
        elif status == 'rejected':
            rejected_count = count

    total_count = pending_count + approved_count + rejected_count
    approval_rate = (approved_count / total_count * 100.0) if total_count > 0 else 0.0

    cursor.close()
    conn.close()

    return render_template(
        'admin_dashboard_v2.html',
        pending_count=pending_count,
        approved_count=approved_count,
        total_count=total_count,
        approval_rate=approval_rate
    )


@app.route('/admin/seller-applications')
def admin_seller_applications():
    """List seller applications in a dedicated admin page."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sa.id, sa.user_id, sa.store_name, sa.store_category,
               sa.store_phone, sa.status, sa.created_at,
               u.username, u.email
        FROM seller_applications sa
        JOIN users u ON sa.user_id = u.id
        ORDER BY sa.created_at DESC
    """)
    applications_data = cursor.fetchall()

    applications = []
    for app in applications_data:
        applications.append({
            'id': app[0],
            'user_id': app[1],
            'store_name': app[2],
            'store_category': app[3],
            'store_phone': app[4],
            'status': app[5],
            'created_at': app[6],
            'username': app[7],
            'email': app[8]
        })

    pending_count = sum(1 for app in applications if app['status'] == 'pending')
    approved_count = sum(1 for app in applications if app['status'] == 'approved')
    total_count = len(applications)

    cursor.close()
    conn.close()

    return render_template(
        'admin_seller_applications.html',
        applications=applications,
        pending_count=pending_count,
        approved_count=approved_count,
        total_count=total_count
    )


@app.route('/admin/seller-applications/<int:application_id>')
def admin_seller_application_detail(application_id):
    """Detailed view of a single seller application."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sa.id, sa.user_id, sa.store_name, sa.store_description, sa.store_category,
               sa.store_phone, sa.business_permit, sa.valid_id, sa.status,
               sa.created_at, sa.updated_at,
               u.username, u.email, u.first_name, u.last_name, u.address, u.phone
        FROM seller_applications sa
        JOIN users u ON sa.user_id = u.id
        WHERE sa.id = %s
    """, (application_id,))
    app = cursor.fetchone()

    if not app:
        cursor.close()
        conn.close()
        flash('Seller application not found.', 'warning')
        return redirect(url_for('admin_seller_applications'))

    application = {
        'id': app[0],
        'user_id': app[1],
        'store_name': app[2],
        'store_description': app[3],
        'store_category': app[4],
        'store_phone': app[5],
        'business_permit': app[6],
        'valid_id': app[7],
        'status': app[8],
        'created_at': app[9],
        'updated_at': app[10],
        'username': app[11],
        'email': app[12],
        'first_name': app[13],
        'last_name': app[14],
        'address': app[15],
        'phone': app[16]
    }

    cursor.close()
    conn.close()

    return render_template(
        'admin_seller_application_detail.html',
        application=application
    )


@app.route('/admin/seller-application/<int:user_id>/<action>', methods=['POST'])
def handle_seller_application(user_id, action):
    """Approve or reject seller application"""
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if action == 'approve':
            # Update seller_applications status
            cursor.execute("""
                UPDATE seller_applications 
                SET status = 'approved'
                WHERE user_id = %s AND status = 'pending'
            """, (user_id,))
            
            # Update user's seller_approved status
            cursor.execute("""
                UPDATE users 
                SET seller_approved = TRUE
                WHERE id = %s
            """, (user_id,))
            
            message = 'Seller application approved successfully!'
        else:
            # Update seller_applications status
            cursor.execute("""
                UPDATE seller_applications 
                SET status = 'rejected'
                WHERE user_id = %s AND status = 'pending'
            """, (user_id,))
            
            message = 'Seller application rejected!'
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/rider-applications')
def admin_rider_applications():
    """List rider applications for admin review."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT ra.id, ra.user_id, ra.full_name, ra.address, ra.phone, ra.email,
               ra.vehicle_type, ra.vehicle_registration, ra.license_number,
               ra.license_image, ra.status, ra.created_at,
               u.username
        FROM rider_applications ra
        JOIN users u ON ra.user_id = u.id
        ORDER BY ra.created_at DESC
        """
    )
    rows = cursor.fetchall()

    applications = []
    for r in rows:
        applications.append({
            'id': r[0],
            'user_id': r[1],
            'full_name': r[2],
            'address': r[3],
            'phone': r[4],
            'email': r[5],
            'vehicle_type': r[6],
            'vehicle_registration': r[7],
            'license_number': r[8],
            'license_image': r[9],
            'status': r[10],
            'created_at': r[11],
            'username': r[12],
        })

    pending_count = sum(1 for app in applications if app['status'] == 'pending')
    approved_count = sum(1 for app in applications if app['status'] == 'approved')
    total_count = len(applications)

    cursor.close()
    conn.close()

    return render_template(
        'admin_rider_applications.html',
        applications=applications,
        pending_count=pending_count,
        approved_count=approved_count,
        total_count=total_count,
    )


@app.route('/admin/rider-applications/<int:application_id>')
def admin_rider_application_detail(application_id):
    """Detailed view of a single rider application."""
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT ra.id, ra.user_id, ra.full_name, ra.address, ra.phone, ra.email,
               ra.vehicle_type, ra.vehicle_registration, ra.license_number,
               ra.license_image, ra.status, ra.created_at, ra.updated_at,
               u.username
        FROM rider_applications ra
        JOIN users u ON ra.user_id = u.id
        WHERE ra.id = %s
        """,
        (application_id,),
    )
    r = cursor.fetchone()

    if not r:
        cursor.close()
        conn.close()
        flash('Rider application not found.', 'warning')
        return redirect(url_for('admin_rider_applications'))

    application = {
        'id': r[0],
        'user_id': r[1],
        'full_name': r[2],
        'address': r[3],
        'phone': r[4],
        'email': r[5],
        'vehicle_type': r[6],
        'vehicle_registration': r[7],
        'license_number': r[8],
        'license_image': r[9],
        'status': r[10],
        'created_at': r[11],
        'updated_at': r[12],
        'username': r[13],
    }

    cursor.close()
    conn.close()

    return render_template('admin_rider_application_detail.html', application=application)


@app.route('/admin/rider-application/<int:user_id>/<action>', methods=['POST'])
def handle_rider_application(user_id, action):
    """Approve or reject rider application and toggle users.is_approved."""
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if action == 'approve':
            cursor.execute(
                """
                UPDATE rider_applications
                SET status = 'approved'
                WHERE user_id = %s AND status = 'pending'
                """,
                (user_id,),
            )

            cursor.execute(
                """
                UPDATE users
                SET is_approved = TRUE
                WHERE id = %s AND role = 'rider'
                """,
                (user_id,),
            )
        else:
            cursor.execute(
                """
                UPDATE rider_applications
                SET status = 'rejected'
                WHERE user_id = %s AND status = 'pending'
                """,
                (user_id,),
            )

            cursor.execute(
                """
                UPDATE users
                SET is_approved = FALSE
                WHERE id = %s AND role = 'rider'
                """,
                (user_id,),
            )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get orders that are accepted/shipped by sellers but not yet assigned to riders,
        # including seller/customer names, locations, and product names
        cursor.execute("""
            SELECT 
                o.id,
                o.total_amount,
                o.status,
                o.order_date,
                u.username AS customer_name,
                u.latitude AS customer_latitude,
                u.longitude AS customer_longitude,
                s.username AS seller_name,
                s.latitude AS seller_latitude,
                s.longitude AS seller_longitude,
                o.shipping_address AS delivery_address,
                GROUP_CONCAT(DISTINCT p.product_name SEPARATOR ', ') AS product_names
            FROM orders o
            JOIN users u ON o.user_id = u.id
            JOIN users s ON o.seller_id = s.id
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status IN ('accepted', 'shipped') AND o.rider_id IS NULL
            GROUP BY 
                o.id, o.total_amount, o.status, o.order_date,
                u.username, u.latitude, u.longitude,
                s.username, s.latitude, s.longitude,
                o.shipping_address
            ORDER BY o.order_date DESC
        """)
        
        orders = []
        for row in cursor.fetchall():
            orders.append({
                'id': row[0],
                'public_id': format_public_order_id(row[0]),
                'total_amount': float(row[1]),
                'status': row[2],
                'order_date': row[3].isoformat() if row[3] else None,
                'customer_name': row[4],
                'customer_latitude': float(row[5]) if row[5] is not None else None,
                'customer_longitude': float(row[6]) if row[6] is not None else None,
                'seller_name': row[7],
                'seller_latitude': float(row[8]) if row[8] is not None else None,
                'seller_longitude': float(row[9]) if row[9] is not None else None,
                'delivery_address': row[10] or 'Address not provided',
                'product_names': row[11] or ''
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'orders': orders})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/rider/my-deliveries')
@role_required('rider')
def get_my_deliveries():
    """Get current active deliveries for the rider"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get current rider's ID and approval status
        cursor.execute("SELECT id, is_approved FROM users WHERE username = %s", (session['username'],))
        rider_result = cursor.fetchone()
        if not rider_result:
            return jsonify({'success': False, 'message': 'Rider not found'}), 404

        rider_id, is_approved = rider_result
        if not is_approved:
            return jsonify({'success': False, 'message': 'Rider not approved yet'}), 403

        # Get non-delivered, non-cancelled orders assigned to this rider,
        # including customer and seller locations
        cursor.execute("""
            SELECT 
                o.id,
                o.status,
                o.shipping_address,
                u.username AS customer_name,
                u.phone AS customer_phone,
                u.latitude AS customer_latitude,
                u.longitude AS customer_longitude,
                s.username AS seller_name,
                s.latitude AS seller_latitude,
                s.longitude AS seller_longitude
            FROM orders o
            JOIN users u ON o.user_id = u.id
            JOIN users s ON o.seller_id = s.id
            WHERE o.rider_id = %s AND o.status NOT IN ('delivered', 'cancelled', 'rejected')
            ORDER BY o.order_date DESC
        """, (rider_id,))

        orders = cursor.fetchall()

        deliveries = []
        for row in orders:
            order_id = row[0]

            # Build a simple items summary string
            cursor.execute("""
                SELECT p.product_name, oi.quantity
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id = %s
            """, (order_id,))
            item_rows = cursor.fetchall()
            items_summary = ", ".join(
                f"{item_name} × {qty}" for (item_name, qty) in item_rows
            )

            deliveries.append({
                'id': order_id,
                'public_id': format_public_order_id(order_id),
                'delivery_status': row[1],
                'delivery_address': row[2] or 'No address provided',
                'customer_name': row[3],
                'customer_phone': row[4],
                'customer_latitude': float(row[5]) if row[5] is not None else None,
                'customer_longitude': float(row[6]) if row[6] is not None else None,
                'seller_name': row[7],
                'seller_latitude': float(row[8]) if row[8] is not None else None,
                'seller_longitude': float(row[9]) if row[9] is not None else None,
                'items': items_summary
            })

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'deliveries': deliveries})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/rider/delivery-history')
@role_required('rider')
def get_delivery_history():
    """Get rider's delivery history"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current rider's ID and approval status
        cursor.execute("SELECT id, is_approved FROM users WHERE username = %s", (session['username'],))
        rider_result = cursor.fetchone()
        if not rider_result:
            return jsonify({'success': False, 'message': 'Rider not found'}), 404

        rider_id, is_approved = rider_result
        if not is_approved:
            return jsonify({'success': False, 'message': 'Rider not approved yet'}), 403
        
        # Get delivered orders for this rider (use delivery_date column for compatibility)
        cursor.execute("""
            SELECT o.id, o.total_amount, o.delivery_date,
                   u.username as customer_name
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.rider_id = %s AND o.status = 'delivered'
            ORDER BY o.delivery_date DESC
        """, (rider_id,))
        
        deliveries = []
        for row in cursor.fetchall():
            deliveries.append({
                'id': row[0],
                'public_id': format_public_order_id(row[0]),
                'total_amount': float(row[1]),
                'delivered_at': row[2].isoformat() if row[2] else None,
                'customer_name': row[3]
            })
        
        cursor.close()
        conn.close()
        
        # Return under both keys for compatibility with older JS
        return jsonify({'success': True, 'history': deliveries, 'deliveries': deliveries})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/rider/update-delivery-status/<int:order_id>', methods=['POST'])
@role_required('rider')
def update_delivery_status(order_id):
    """Update delivery status for an order and notify the customer"""
    try:
        data = request.get_json() or {}
        status = data.get('status')
        notes = (data.get('notes') or '').strip()

        if status not in ['out_for_delivery', 'delivered']:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get current rider's ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        rider_result = cursor.fetchone()
        if not rider_result:
            return jsonify({'success': False, 'message': 'Rider not found'}), 404

        rider_id = rider_result[0]

        # Load order and ensure it belongs to this rider
        cursor.execute("""
            SELECT id, user_id, status
            FROM orders
            WHERE id = %s AND rider_id = %s
        """, (order_id, rider_id))
        order = cursor.fetchone()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found for this rider'}), 404

        customer_id = order[1]
        seller_id = order[2]
        current_status = order[2]

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
        if new_order_status == 'delivered':
            cursor.execute("""
                UPDATE orders
                SET status = %s, delivered_at = NOW(), notes = %s
                WHERE id = %s AND rider_id = %s
            """, (new_order_status, notes or None, order_id, rider_id))
        else:
            cursor.execute("""
                UPDATE orders
                SET status = %s, notes = %s
                WHERE id = %s AND rider_id = %s
            """, (new_order_status, notes or None, order_id, rider_id))

        # Send notification to customer if needed
        if send_notification and notif_type:
            cursor.execute("""
                INSERT INTO notifications (user_id, order_id, type, title, message)
                VALUES (%s, %s, %s, %s, %s)
            """, (customer_id, order_id, notif_type, notif_title, notif_message))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Delivery status updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/rider/notifications')
@role_required('rider')
def get_rider_notifications_legacy():
    """Get rider notifications"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current rider's ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        rider_result = cursor.fetchone()
        if not rider_result:
            return jsonify({'success': False, 'message': 'Rider not found'}), 404
        
        rider_id = rider_result[0]
        
        # Get notifications for this rider
        cursor.execute("""
            SELECT message, created_at, is_read
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (rider_id,))
        
        notifications = []
        for row in cursor.fetchall():
            notifications.append({
                'message': row[0],
                'created_at': row[1].isoformat() if row[1] else None,
                'read': bool(row[2])
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'notifications': notifications})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/rider/accept-order/<int:order_id>', methods=['POST'])
@role_required('rider')
def accept_order(order_id):
    """Accept an order for delivery"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current rider's ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        rider_result = cursor.fetchone()
        if not rider_result:
            return jsonify({'success': False, 'message': 'Rider not found'}), 404
        
        rider_id = rider_result[0]
        
        # Check if order exists and is available (accepted/shipped by seller and not yet assigned)
        cursor.execute("""
            SELECT id, user_id, seller_id, status FROM orders 
            WHERE id = %s AND status IN ('accepted', 'shipped') AND rider_id IS NULL
        """, (order_id,))
        
        order = cursor.fetchone()
        if not order:
            return jsonify({'success': False, 'message': 'Order not available'}), 404
        
        customer_id = order[1]
        
        # Assign rider to order and update status
        cursor.execute("""
            UPDATE orders 
            SET rider_id = %s, status = 'out_for_delivery', accepted_at = NOW()
            WHERE id = %s
        """, (rider_id, order_id))
        
        # Send notification to customer
        public_id = format_public_order_id(order_id)
        cursor.execute("""
            INSERT INTO notifications (user_id, order_id, type, title, message)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            customer_id,
            order_id,
            'order_shipped',
            'Order Out for Delivery',
            f"Great news! Your order ID {public_id} has been accepted by a rider and is out for delivery!"
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Order accepted successfully!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/rider/reject-order/<int:order_id>', methods=['POST'])
@role_required('rider')
def reject_order(order_id):
    """Reject an order with reason"""
    try:
        data = request.get_json()
        reason = data.get('reason', '').strip()
        
        if not reason:
            return jsonify({'success': False, 'message': 'Rejection reason is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure rider is approved before rejecting orders
        cursor.execute("SELECT is_approved FROM users WHERE username = %s", (session['username'],))
        result = cursor.fetchone()
        is_approved = result[0] if result and result[0] is not None else False
        if not is_approved:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Rider not approved yet'}), 403
        
        # Check if order exists and is available (accepted by seller and not yet assigned)
        cursor.execute("""
            SELECT id, user_id, status FROM orders 
            WHERE id = %s AND status = 'accepted' AND rider_id IS NULL
        """, (order_id,))
        
        order = cursor.fetchone()
        if not order:
            return jsonify({'success': False, 'message': 'Order not available'}), 404
        
        customer_id = order[1]
        
        # Update order status and add rejection reason
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
            f"Sorry, your order ID {public_id} was rejected by the delivery service. Reason: {reason}"
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Order rejected successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# API Routes for Seller Order Management (for AJAX calls)
@app.route('/api/seller/orders')
@role_required('seller')
def api_get_seller_orders():
    """API endpoint to get orders for seller's products"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current seller's ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (session['username'],))
        seller_result = cursor.fetchone()
        if not seller_result:
            return jsonify({'success': False, 'message': 'Seller not found'}), 404
        
        seller_id = seller_result[0]
        
        # Get orders containing seller's products
        cursor.execute("""
            SELECT DISTINCT o.id, o.total_amount, o.status, o.order_date,
                   u.username as customer_name, o.shipping_address as delivery_address
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            JOIN users u ON o.user_id = u.id
            WHERE p.seller_username = %s
            ORDER BY o.order_date DESC
        """, (session['username'],))
        
        orders = []
        for row in cursor.fetchall():
            orders.append({
                'id': row[0],
                'total_amount': float(row[1]),
                'status': row[2],
                'order_date': row[3].isoformat() if row[3] else None,
                'customer_name': row[4],
                'delivery_address': row[5] or 'Address not provided'
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'orders': orders})
        
    except Exception as e:
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

@app.route('/seller/order/<int:order_id>/accept', methods=['POST'])
@role_required('seller')
def accept_seller_order(order_id):
    """Accept an order as seller"""
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

@app.route('/api/seller/approve-order/<int:order_id>', methods=['POST'])
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

@app.route('/api/seller/reject-order/<int:order_id>', methods=['POST'])
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

# Register checkout routes
register_checkout_routes(app)

if __name__ == '__main__':
    # Initialize database tables before starting the app
    init_database()
    app.run(debug=True)
