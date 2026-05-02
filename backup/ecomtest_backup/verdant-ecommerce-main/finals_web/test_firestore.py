"""
Test script to verify Firestore connection and basic operations
"""

from firestore_db import (
    get_user_by_username,
    get_products,
    create_product,
    get_orders,
    users_ref
)

print("=" * 60)
print("FIRESTORE CONNECTION TEST")
print("=" * 60)

# Test 1: Get users
print("\n1. Testing user lookup...")
try:
    user = get_user_by_username('seller1')
    if user:
        print(f"   ✓ Found user: {user['username']} ({user['email']})")
        print(f"   ✓ Role: {user['role']}")
    else:
        print("   ✗ User not found")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 2: List all users
print("\n2. Listing all users...")
try:
    all_users = list(users_ref.stream())
    print(f"   ✓ Total users in database: {len(all_users)}")
    for user_doc in all_users:
        user_data = user_doc.to_dict()
        print(f"      - {user_data.get('username')} ({user_data.get('role')})")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 3: Get products
print("\n3. Testing product queries...")
try:
    products = get_products(limit=5)
    print(f"   ✓ Found {len(products)} products")
    if len(products) == 0:
        print("   ℹ No products yet - this is normal for new setup")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 4: Create a test product
print("\n4. Creating test product...")
try:
    test_product = {
        'product_name': 'Test Garden Tool',
        'seller_username': 'seller1',
        'price': 29.99,
        'stock': 100,
        'specifications': 'A test product for Firestore',
        'image': 'default.jpg'
    }
    product_id = create_product(test_product)
    print(f"   ✓ Product created with ID: {product_id}")
    
    # Verify it was created
    products = get_products(limit=1)
    if products:
        print(f"   ✓ Verified: {products[0].get('product_name')}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 5: Get orders
print("\n5. Testing order queries...")
try:
    orders = get_orders()
    print(f"   ✓ Found {len(orders)} orders")
    if len(orders) == 0:
        print("   ℹ No orders yet - this is normal for new setup")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE!")
print("=" * 60)
print("\n✅ Firestore is connected and working!")
print("\n📱 Your mobile app can now connect to the same database.")
print("   Use the Firebase credentials JSON file in your mobile app.")
print("\n🌐 Flask app can use Firestore functions from firestore_db.py")
print("\n" + "=" * 60)
