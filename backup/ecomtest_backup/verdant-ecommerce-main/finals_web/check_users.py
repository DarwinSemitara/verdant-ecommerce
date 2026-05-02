"""
Script to check and manage users in Firestore
"""
from firestore_db import db, users_ref

def list_all_users():
    """List all users in the database"""
    print("\n=== All Users in Database ===")
    users = users_ref.stream()
    count = 0
    for user_doc in users:
        count += 1
        user_data = user_doc.to_dict()
        print(f"\n{count}. Username: {user_doc.id}")
        print(f"   Email: {user_data.get('email', 'N/A')}")
        print(f"   Role: {user_data.get('role', 'N/A')}")
        print(f"   Verified: {user_data.get('is_verified', 'N/A')}")
        print(f"   Active: {user_data.get('is_active', 'N/A')}")
    
    if count == 0:
        print("No users found in database.")
    else:
        print(f"\nTotal users: {count}")
    
    return count

def delete_user_by_username(username):
    """Delete a user by username"""
    try:
        users_ref.document(username).delete()
        print(f"✅ User '{username}' deleted successfully")
        return True
    except Exception as e:
        print(f"❌ Error deleting user: {e}")
        return False

def delete_user_by_email(email):
    """Delete all users with a specific email"""
    try:
        users = users_ref.where('email', '==', email).stream()
        count = 0
        for user_doc in users:
            user_doc.reference.delete()
            count += 1
            print(f"✅ Deleted user: {user_doc.id}")
        
        if count == 0:
            print(f"No users found with email: {email}")
        else:
            print(f"✅ Deleted {count} user(s) with email: {email}")
        return True
    except Exception as e:
        print(f"❌ Error deleting users: {e}")
        return False

if __name__ == "__main__":
    print("Firestore User Management Tool")
    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. List all users")
        print("2. Delete user by username")
        print("3. Delete user(s) by email")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == "1":
            list_all_users()
        
        elif choice == "2":
            username = input("Enter username to delete: ").strip()
            if username:
                confirm = input(f"Are you sure you want to delete user '{username}'? (yes/no): ").strip().lower()
                if confirm == "yes":
                    delete_user_by_username(username)
            else:
                print("Username cannot be empty")
        
        elif choice == "3":
            email = input("Enter email to delete: ").strip()
            if email:
                confirm = input(f"Are you sure you want to delete all users with email '{email}'? (yes/no): ").strip().lower()
                if confirm == "yes":
                    delete_user_by_email(email)
            else:
                print("Email cannot be empty")
        
        elif choice == "4":
            print("Exiting...")
            break
        
        else:
            print("Invalid choice. Please try again.")
