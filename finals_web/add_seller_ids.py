"""
Script to add seller IDs to existing approved sellers who don't have one yet.
Run this once to migrate existing sellers.
"""

import os
import sys

# Add the parent directory to the path so we can import from finals_web
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from firestore_db import db, users_ref
import random
import string

def generate_seller_id():
    """Generate a unique seller ID in format VRD-XXXXXX"""
    return 'VRD-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def add_seller_ids():
    """Add seller IDs to all approved sellers who don't have one"""
    print("🔍 Finding approved sellers without seller_id...")
    
    try:
        # Get all approved sellers
        sellers_query = users_ref.where('role', '==', 'seller').where('seller_approved', '==', True).stream()
        
        updated_count = 0
        skipped_count = 0
        
        for seller_doc in sellers_query:
            seller_data = seller_doc.to_dict()
            username = seller_data.get('username')
            existing_seller_id = seller_data.get('seller_id')
            
            if existing_seller_id:
                print(f"⏭️  Skipping {username} - already has seller_id: {existing_seller_id}")
                skipped_count += 1
                continue
            
            # Generate unique seller ID
            seller_id = generate_seller_id()
            
            # Check if seller_id already exists (very unlikely but good practice)
            while True:
                existing = users_ref.where('seller_id', '==', seller_id).limit(1).get()
                if not existing:
                    break
                seller_id = generate_seller_id()
            
            # Update seller with new ID
            seller_doc.reference.update({'seller_id': seller_id})
            print(f"✅ Added seller_id {seller_id} to {username}")
            updated_count += 1
        
        print(f"\n📊 Summary:")
        print(f"   Updated: {updated_count} sellers")
        print(f"   Skipped: {skipped_count} sellers (already had IDs)")
        print(f"   Total: {updated_count + skipped_count} sellers processed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    add_seller_ids()
