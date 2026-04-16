"""
Firestore Database Module for Verdant E-Commerce Platform
Replaces MySQL with Cloud Firestore
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from werkzeug.security import generate_password_hash
import os

# Initialize Firebase Admin SDK
cred = credentials.Certificate('firebase_verdant_db.json')
firebase_admin.initialize_app(cred)

# Get Firestore client
db = firestore.client()

# Collection references
users_ref = db.collection('users')
products_ref = db.collection('products')
orders_ref = db.collection('orders')
cart_ref = db.collection('cart')
notifications_ref = db.collection('notifications')
messages_ref = db.collection('chat_messages')
seller_applications_ref = db.collection('seller_applications')
rider_applications_ref = db.collection('rider_applications')
reviews_ref = db.collection('reviews')
product_images_ref = db.collection('product_images')

# New collections for product variations system
products_v2_ref = db.collection('products_v2')  # Products with variation support
product_variations_ref = db.collection('product_variations')  # Individual variations


def get_firestore_client():
    """Return the Firestore client instance"""
    return db


def initialize_firestore():
    """Initialize Firestore with sample data if empty"""
    print("Initializing Firestore database...")
    
    # Check if admin user exists
    admin_query = users_ref.where('username', '==', 'admin').limit(1).get()
    
    if len(admin_query) == 0:
        print("Creating sample users...")
        
        # Create admin user
        users_ref.add({
            'username': 'admin',
            'email': 'admin@verdant.com',
            'password': generate_password_hash('admin123'),
            'role': 'user',
            'fullname': 'Admin User',
            'address': '123 Admin Street',
            'phone': '09123456789',
            'is_active': True,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        # Create sample seller
        users_ref.add({
            'username': 'seller1',
            'email': 'seller1@verdant.com',
            'password': generate_password_hash('password123'),
            'role': 'seller',
            'fullname': 'John Seller',
            'address': '456 Seller Avenue',
            'phone': '09123456788',
            'store_name': 'Green Garden Store',
            'business_address': '456 Seller Avenue, Business District',
            'is_active': True,
            'seller_approved': True,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        # Create sample rider
        users_ref.add({
            'username': 'rider1',
            'email': 'rider1@verdant.com',
            'password': generate_password_hash('password123'),
            'role': 'rider',
            'fullname': 'Mike Rider',
            'address': '789 Rider Road',
            'phone': '09123456787',
            'vehicle_type': 'motorcycle',
            'license_number': 'DL123456789',
            'is_active': True,
            'is_approved': True,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        print("Sample data created successfully!")
    else:
        print("Sample data already exists.")
    
    print("Firestore initialization completed!")
    return True


# Helper functions for common operations

def get_user_by_username(username):
    """Get user document by username (username is the document ID)"""
    user_doc = users_ref.document(username).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        user_data['id'] = user_doc.id  # Add document ID to the data
        return user_data
    return None


def get_user_by_id(user_id):
    """Get user document by ID"""
    user_doc = users_ref.document(user_id).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        user_data['id'] = user_doc.id
        return user_data
    return None


def get_user_by_email(email):
    """Get user document by email"""
    users = users_ref.where('email', '==', email).limit(1).get()
    if users:
        user_doc = users[0]
        user_data = user_doc.to_dict()
        user_data['id'] = user_doc.id
        return user_data
    return None


def get_user_by_email_and_role(email, role):
    """Get user document by email and role - allows same email for different roles"""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        users = users_ref.where('email', '==', email).where('role', '==', role).limit(1).get()
    if users:
        user_doc = users[0]
        user_data = user_doc.to_dict()
        user_data['id'] = user_doc.id
        return user_data
    return None


def create_user(user_data):
    """Create a new user document with username as document ID"""
    username = user_data.get('username')
    if not username:
        raise ValueError("Username is required to create a user")
    
    # Add timestamps if not already present
    if 'created_at' not in user_data:
        user_data['created_at'] = firestore.SERVER_TIMESTAMP
    if 'updated_at' not in user_data:
        user_data['updated_at'] = firestore.SERVER_TIMESTAMP
    
    # Use username as document ID
    doc_ref = users_ref.document(username)
    doc_ref.set(user_data)
    return username  # Returns the username (document ID)


def update_user(user_id, update_data):
    """Update user document"""
    update_data['updated_at'] = firestore.SERVER_TIMESTAMP
    users_ref.document(user_id).update(update_data)
    return True


def get_products(limit=None, seller_username=None, in_stock_only=False):
    """Get products with optional filters"""
    query = products_ref
    
    if seller_username:
        query = query.where('seller_username', '==', seller_username)
    
    if in_stock_only:
        query = query.where('stock_quantity', '>', 0)
    
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    
    if limit:
        query = query.limit(limit)
    
    products = []
    for doc in query.stream():
        product_data = doc.to_dict()
        product_data['id'] = doc.id
        products.append(product_data)
    
    return products


def get_product_by_id(product_id):
    """Get product by ID"""
    product_doc = products_ref.document(product_id).get()
    if product_doc.exists:
        product_data = product_doc.to_dict()
        product_data['id'] = product_doc.id
        return product_data
    return None


def create_product(product_data):
    """Create a new product"""
    product_data['created_at'] = firestore.SERVER_TIMESTAMP
    product_data['updated_at'] = firestore.SERVER_TIMESTAMP
    product_data['is_active'] = True
    doc_ref = products_ref.add(product_data)
    return doc_ref[1].id


def update_product(product_id, update_data):
    """Update product"""
    update_data['updated_at'] = firestore.SERVER_TIMESTAMP
    products_ref.document(product_id).update(update_data)
    return True


def delete_product(product_id):
    """Delete product"""
    products_ref.document(product_id).delete()
    return True


def get_cart_items(user_id):
    """Get cart items for a user"""
    cart_items = cart_ref.where('user_id', '==', user_id).stream()
    items = []
    for doc in cart_items:
        item_data = doc.to_dict()
        item_data['id'] = doc.id
        items.append(item_data)
    return items


def add_to_cart(user_id, product_id, quantity=1):
    """Add item to cart or update quantity"""
    # Check if item already in cart
    existing = cart_ref.where('user_id', '==', user_id).where('product_id', '==', product_id).limit(1).get()
    
    if existing:
        # Update quantity
        cart_doc = existing[0]
        current_qty = cart_doc.to_dict().get('quantity', 0)
        cart_ref.document(cart_doc.id).update({
            'quantity': current_qty + quantity,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        return cart_doc.id
    else:
        # Add new item
        doc_ref = cart_ref.add({
            'user_id': user_id,
            'product_id': product_id,
            'quantity': quantity,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        return doc_ref[1].id


def update_cart_quantity(cart_item_id, quantity):
    """Update cart item quantity"""
    cart_ref.document(cart_item_id).update({
        'quantity': quantity,
        'updated_at': firestore.SERVER_TIMESTAMP
    })
    return True


def remove_from_cart(cart_item_id):
    """Remove item from cart"""
    cart_ref.document(cart_item_id).delete()
    return True


def clear_cart(user_id):
    """Clear all cart items for a user"""
    cart_items = cart_ref.where('user_id', '==', user_id).stream()
    for item in cart_items:
        item.reference.delete()
    return True


def create_order(order_data):
    """Create a new order"""
    order_data['order_date'] = firestore.SERVER_TIMESTAMP
    order_data['status'] = order_data.get('status', 'pending')
    doc_ref = orders_ref.add(order_data)
    return doc_ref[1].id


def get_order_by_id(order_id):
    """Get order by ID"""
    order_doc = orders_ref.document(order_id).get()
    if order_doc.exists:
        order_data = order_doc.to_dict()
        order_data['id'] = order_doc.id
        return order_data
    return None


def get_orders(user_id=None, seller_id=None, rider_id=None, status=None):
    """Get orders with filters"""
    query = orders_ref
    
    if user_id:
        query = query.where('user_id', '==', user_id)
    
    if seller_id:
        query = query.where('seller_id', '==', seller_id)
    
    if rider_id:
        query = query.where('rider_id', '==', rider_id)
    
    if status:
        query = query.where('status', '==', status)
    
    query = query.order_by('order_date', direction=firestore.Query.DESCENDING)
    
    orders = []
    for doc in query.stream():
        order_data = doc.to_dict()
        order_data['id'] = doc.id
        orders.append(order_data)
    
    return orders


def update_order(order_id, update_data):
    """Update order"""
    orders_ref.document(order_id).update(update_data)
    return True


def create_notification(notification_data):
    """Create a notification"""
    notification_data['created_at'] = firestore.SERVER_TIMESTAMP
    notification_data['is_read'] = False
    doc_ref = notifications_ref.add(notification_data)
    return doc_ref[1].id


def get_notifications(user_id, limit=50):
    """Get notifications for a user"""
    notifications = notifications_ref.where('user_id', '==', user_id)\
        .order_by('created_at', direction=firestore.Query.DESCENDING)\
        .limit(limit)\
        .stream()
    
    notifs = []
    for doc in notifications:
        notif_data = doc.to_dict()
        notif_data['id'] = doc.id
        notifs.append(notif_data)
    
    return notifs


def mark_notification_read(notification_id):
    """Mark notification as read"""
    notifications_ref.document(notification_id).update({'is_read': True})
    return True


if __name__ == "__main__":
    initialize_firestore()
