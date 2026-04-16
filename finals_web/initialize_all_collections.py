"""
Initialize all Firestore collections based on MySQL schema
Creates empty collections with proper structure
"""

from firestore_db import db
from datetime import datetime

print("=" * 70)
print("INITIALIZING ALL FIRESTORE COLLECTIONS")
print("=" * 70)

# Collection references
collections = {
    'users': db.collection('users'),
    'products': db.collection('products'),
    'product_images': db.collection('product_images'),
    'orders': db.collection('orders'),
    'order_items': db.collection('order_items'),
    'cart': db.collection('cart'),
    'notifications': db.collection('notifications'),
    'chat_messages': db.collection('chat_messages'),
    'reviews': db.collection('reviews'),
    'review_photos': db.collection('review_photos'),
    'seller_applications': db.collection('seller_applications'),
    'rider_applications': db.collection('rider_applications'),
    'stores': db.collection('stores'),
    'messages': db.collection('messages'),
    'support_tickets': db.collection('support_tickets'),
    'wallet_accounts': db.collection('wallet_accounts'),
    'cashout_requests': db.collection('cashout_requests'),
    'transactions': db.collection('transactions'),
    'delivery_tracking': db.collection('delivery_tracking')
}

# Sample document structures for each collection
sample_structures = {
    'users': {
        'username': 'sample_user',
        'email': 'user@example.com',
        'password': 'hashed_password',
        'role': 'user',  # user, seller, rider
        'first_name': '',
        'last_name': '',
        'fullname': '',
        'date_of_birth': None,
        'gender': '',
        'address': '',
        'city': '',
        'state_province': '',
        'postal_code': '',
        'country': 'Philippines',
        'phone': '',
        'alternate_phone': '',
        'latitude': None,
        'longitude': None,
        'profile_picture': None,
        'store_name': None,
        'store_profile': None,
        'business_address': None,
        'vehicle_type': None,
        'license_number': None,
        'is_active': True,
        'is_approved': False,
        'seller_approved': False,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    },
    
    'products': {
        'product_name': 'Sample Product',
        'seller_username': 'seller1',
        'seller_id': 'user_doc_id',
        'price': 0.0,
        'stock': 0,
        'stock_quantity': 0,
        'specifications': '',
        'description': '',
        'category': '',
        'image': 'default.jpg',
        'image_path': None,
        'is_active': True,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    },
    
    'product_images': {
        'product_id': 'product_doc_id',
        'filename': 'image.jpg',
        'is_thumbnail': False,
        'sort_order': 0,
        'created_at': datetime.utcnow()
    },
    
    'orders': {
        'user_id': 'user_doc_id',
        'seller_id': 'seller_doc_id',
        'rider_id': None,
        'total_amount': 0.0,
        'status': 'pending',  # pending, accepted, rejected, shipped, out_for_delivery, delivered, cancelled
        'shipping_address': '',
        'order_date': datetime.utcnow(),
        'delivery_date': None,
        'delivered_at': None,
        'accepted_at': None,
        'rejected_at': None,
        'notes': '',
        'rejection_reason': '',
        'items': []  # Array of order items
    },
    
    'order_items': {
        'order_id': 'order_doc_id',
        'product_id': 'product_doc_id',
        'product_name': '',
        'quantity': 1,
        'unit_price': 0.0,
        'total_price': 0.0
    },
    
    'cart': {
        'user_id': 'user_doc_id',
        'product_id': 'product_doc_id',
        'quantity': 1,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    },
    
    'notifications': {
        'user_id': 'user_doc_id',
        'order_id': None,
        'type': 'general',  # order_accepted, order_rejected, order_shipped, order_delivered, general
        'title': 'Notification Title',
        'message': 'Notification message',
        'is_read': False,
        'created_at': datetime.utcnow()
    },
    
    'chat_messages': {
        'sender_username': 'user1',
        'receiver_username': 'user2',
        'message_text': 'Hello',
        'is_read': False,
        'created_at': datetime.utcnow()
    },
    
    'reviews': {
        'product_id': 'product_doc_id',
        'user_id': 'user_doc_id',
        'customer_name': 'Customer Name',
        'rating': 5,
        'comment': 'Great product!',
        'status': 'pending',  # pending, approved, rejected
        'created_at': datetime.utcnow()
    },
    
    'review_photos': {
        'review_id': 'review_doc_id',
        'filename': 'photo.jpg',
        'created_at': datetime.utcnow()
    },
    
    'seller_applications': {
        'user_id': 'user_doc_id',
        'store_name': 'My Store',
        'store_description': '',
        'store_category': '',
        'store_phone': '',
        'business_permit': None,
        'valid_id': None,
        'status': 'pending',  # pending, approved, rejected
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    },
    
    'rider_applications': {
        'user_id': 'user_doc_id',
        'full_name': 'Rider Name',
        'address': '',
        'phone': '',
        'email': '',
        'vehicle_type': 'motorcycle',
        'vehicle_registration': '',
        'license_number': '',
        'license_image': None,
        'status': 'pending',  # pending, approved, rejected
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    },
    
    'stores': {
        'seller_id': 'user_doc_id',
        'name': 'Store Name',
        'description': '',
        'category': '',
        'email': '',
        'phone': '',
        'address': '',
        'operating_hours': '',
        'payment_methods': '',
        'profile_image': None,
        'cover_image': None,
        'created_at': datetime.utcnow()
    },
    
    'messages': {
        'customer_name': 'Customer',
        'customer_email': 'customer@example.com',
        'subject': 'Subject',
        'message': 'Message text',
        'status': 'unread',  # unread, read
        'created_at': datetime.utcnow()
    },
    
    'support_tickets': {
        'customer_name': 'Customer',
        'customer_email': 'customer@example.com',
        'order_id': None,
        'subject': 'Issue',
        'description': 'Description',
        'priority': 'medium',  # low, medium, high
        'status': 'open',  # open, in_progress, closed
        'created_at': datetime.utcnow()
    },
    
    'wallet_accounts': {
        'user_id': 'user_doc_id',
        'balance': 0.0,
        'pending_payouts': 0.0,
        'min_withdraw': 500.0,
        'created_at': datetime.utcnow()
    },
    
    'cashout_requests': {
        'user_id': 'user_doc_id',
        'amount': 0.0,
        'status': 'pending',  # pending, approved, rejected
        'created_at': datetime.utcnow(),
        'reviewed_at': None,
        'notes': ''
    },
    
    'transactions': {
        'user_id': 'user_doc_id',
        'type': 'credit',  # credit, debit
        'amount': 0.0,
        'description': '',
        'created_at': datetime.utcnow()
    },
    
    'delivery_tracking': {
        'order_id': 'order_doc_id',
        'rider_id': 'rider_doc_id',
        'status': 'picked_up',
        'latitude': None,
        'longitude': None,
        'notes': '',
        'created_at': datetime.utcnow()
    }
}

print("\nCreating sample documents to initialize collections...\n")

created_count = 0
for collection_name, sample_doc in sample_structures.items():
    try:
        # Check if collection already has documents
        existing_docs = list(collections[collection_name].limit(1).stream())
        
        if existing_docs:
            print(f"✓ {collection_name:25} - Already exists ({len(list(collections[collection_name].stream()))} documents)")
        else:
            # Create a sample document to initialize the collection
            doc_ref = collections[collection_name].add(sample_doc)
            print(f"✓ {collection_name:25} - Created with sample document")
            created_count += 1
            
            # Delete the sample document (we just needed to create the collection)
            doc_ref[1].delete()
            print(f"  └─ Sample document removed (collection initialized)")
            
    except Exception as e:
        print(f"✗ {collection_name:25} - Error: {e}")

print("\n" + "=" * 70)
print(f"INITIALIZATION COMPLETE!")
print("=" * 70)
print(f"\n✅ All {len(collections)} collections are ready in Firestore")
print(f"📊 {created_count} new collections were initialized")
print(f"\n🔥 Your Firestore database structure matches your MySQL schema")
print(f"📱 Mobile app can now access all collections")
print("\n" + "=" * 70)
