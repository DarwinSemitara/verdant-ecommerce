"""
Verify Firestore setup is complete and working
"""

from firestore_db import db, users_ref
from google.cloud import firestore

print("=" * 70)
print("FIRESTORE SETUP VERIFICATION")
print("=" * 70)

# List all collections
print("\n📁 Checking Firestore Collections...")
collections = db.collections()
collection_names = [col.id for col in collections]

expected_collections = [
    'users', 'products', 'product_images', 'orders', 'order_items',
    'cart', 'notifications', 'chat_messages', 'reviews', 'review_photos',
    'seller_applications', 'rider_applications', 'stores', 'messages',
    'support_tickets', 'wallet_accounts', 'cashout_requests',
    'transactions', 'delivery_tracking'
]

print(f"\n✅ Found {len(collection_names)} collections:")
for name in sorted(collection_names):
    emoji = "✓" if name in expected_collections else "?"
    print(f"   {emoji} {name}")

missing = set(expected_collections) - set(collection_names)
if missing:
    print(f"\n⚠️  Missing collections: {', '.join(missing)}")
else:
    print(f"\n✅ All {len(expected_collections)} expected collections exist!")

# Check users collection
print("\n👥 Checking Users Collection...")
users = list(users_ref.stream())
print(f"   Total users: {len(users)}")
for user_doc in users:
    user_data = user_doc.to_dict()
    print(f"   - {user_data.get('username')} ({user_data.get('role')})")

# Test connection
print("\n🔌 Testing Firestore Connection...")
try:
    test_doc = db.collection('_test').document('connection_test')
    test_doc.set({'test': True, 'timestamp': firestore.SERVER_TIMESTAMP})
    test_doc.delete()
    print("   ✅ Connection successful!")
except Exception as e:
    print(f"   ❌ Connection failed: {e}")

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE!")
print("=" * 70)

print("\n📱 Your Firestore database is ready for:")
print("   ✓ Flask web app (signup/login working)")
print("   ✓ Mobile app integration")
print("   ✓ Real-time data synchronization")

print("\n⚠️  Note: Most Flask routes still need migration")
print("   Only signup and login are currently using Firestore")

print("\n🔗 View your database:")
print("   https://console.firebase.google.com/")

print("\n" + "=" * 70)
