"""
Cleanup script to delete test users and start fresh
Keeps only admin user
"""

from firestore_db import users_ref, products_ref, orders_ref, cart_ref

print("=" * 60)
print("FIRESTORE CLEANUP - FRESH START")
print("=" * 60)

# Delete seller1
print("\n1. Deleting seller1...")
try:
    seller_query = users_ref.where('username', '==', 'seller1').limit(1).get()
    if seller_query:
        seller_query[0].reference.delete()
        print("   ✓ seller1 deleted")
    else:
        print("   ℹ seller1 not found")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Delete rider1
print("\n2. Deleting rider1...")
try:
    rider_query = users_ref.where('username', '==', 'rider1').limit(1).get()
    if rider_query:
        rider_query[0].reference.delete()
        print("   ✓ rider1 deleted")
    else:
        print("   ℹ rider1 not found")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Delete test products
print("\n3. Deleting test products...")
try:
    all_products = list(products_ref.stream())
    for product_doc in all_products:
        product_doc.reference.delete()
    print(f"   ✓ Deleted {len(all_products)} products")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Delete any orders
print("\n4. Deleting test orders...")
try:
    all_orders = list(orders_ref.stream())
    for order_doc in all_orders:
        order_doc.reference.delete()
    print(f"   ✓ Deleted {len(all_orders)} orders")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Delete cart items
print("\n5. Deleting cart items...")
try:
    all_cart = list(cart_ref.stream())
    for cart_doc in all_cart:
        cart_doc.reference.delete()
    print(f"   ✓ Deleted {len(all_cart)} cart items")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Show remaining users
print("\n6. Remaining users:")
try:
    remaining_users = list(users_ref.stream())
    for user_doc in remaining_users:
        user_data = user_doc.to_dict()
        print(f"   - {user_data.get('username')} ({user_data.get('role')})")
    print(f"\n   Total: {len(remaining_users)} users")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("CLEANUP COMPLETE!")
print("=" * 60)
print("\n✅ Database is now clean and ready for testing")
print("📝 You can now create a new account and it will save to Firestore")
print("\n" + "=" * 60)
