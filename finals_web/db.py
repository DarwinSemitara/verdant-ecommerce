import mysql.connector
from mysql.connector import Error
import os
from werkzeug.security import generate_password_hash

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',  # Default XAMPP user
    'password': '',  # Default XAMPP password (empty)
    'database': 'verdant',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}

def get_db_connection():
    """Create and return a database connection"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def create_database_if_not_exists():
    """Create the database if it doesn't exist"""
    try:
        # Connect without specifying database
        config_without_db = DB_CONFIG.copy()
        del config_without_db['database']
        
        connection = mysql.connector.connect(**config_without_db)
        cursor = connection.cursor()
        
        # Create database
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"Database '{DB_CONFIG['database']}' created or already exists.")
        
        cursor.close()
        connection.close()
        
    except Error as e:
        print(f"Error creating database: {e}")

def create_tables():
    """Create all necessary tables"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                role ENUM('user', 'seller', 'rider') NOT NULL DEFAULT 'user',
                fullname VARCHAR(100),
                address TEXT,
                phone VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                store_name VARCHAR(100),
                business_address TEXT,
                vehicle_type ENUM('motorcycle', 'bicycle', 'car', 'van'),
                license_number VARCHAR(50),
                is_approved BOOLEAN DEFAULT FALSE,
                profile_picture VARCHAR(255),
                latitude DECIMAL(10, 8),
                longitude DECIMAL(11, 8),
                INDEX idx_username (username),
                INDEX idx_email (email),
                INDEX idx_role (role),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Add missing columns to existing users table (for backwards compatibility)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN profile_picture VARCHAR(255)")
        except:
            pass  # Column already exists
        
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN latitude DECIMAL(10, 8)")
        except:
            pass  # Column already exists
        
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN longitude DECIMAL(11, 8)")
        except:
            pass  # Column already exists
        
        # Products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                seller_id INT NOT NULL,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                price DECIMAL(10, 2) NOT NULL,
                category VARCHAR(100),
                image_path VARCHAR(255),
                stock_quantity INT DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_seller_id (seller_id),
                INDEX idx_category (category),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                seller_id INT NOT NULL,
                rider_id INT,
                total_amount DECIMAL(10, 2) NOT NULL,
                status ENUM('pending', 'accepted', 'rejected', 'shipped', 'delivered', 'cancelled') DEFAULT 'pending',
                shipping_address TEXT NOT NULL,
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivery_date TIMESTAMP NULL,
                notes TEXT,
                rejection_reason TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (rider_id) REFERENCES users(id) ON DELETE SET NULL,
                INDEX idx_user_id (user_id),
                INDEX idx_seller_id (seller_id),
                INDEX idx_rider_id (rider_id),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Order items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                order_id INT NOT NULL,
                product_id INT NOT NULL,
                quantity INT NOT NULL,
                unit_price DECIMAL(10, 2) NOT NULL,
                total_price DECIMAL(10, 2) NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                INDEX idx_order_id (order_id),
                INDEX idx_product_id (product_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Additional product images table (supports multiple photos per product)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_images (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT NOT NULL,
                filename VARCHAR(255) NOT NULL,
                is_thumbnail BOOLEAN DEFAULT FALSE,
                sort_order INT DEFAULT 0,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                INDEX idx_product_id (product_id),
                INDEX idx_product_thumb (product_id, is_thumbnail)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Cart table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                product_id INT NOT NULL,
                quantity INT NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                UNIQUE KEY unique_user_product (user_id, product_id),
                INDEX idx_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Notifications table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                order_id INT,
                type ENUM('order_accepted', 'order_rejected', 'order_shipped', 'order_delivered', 'general') NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_is_read (is_read),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Chat messages table for seller/rider/user messaging
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sender_username VARCHAR(50) NOT NULL,
                receiver_username VARCHAR(50) NOT NULL,
                message_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read BOOLEAN DEFAULT FALSE,
                INDEX idx_sender_receiver (sender_username, receiver_username),
                INDEX idx_receiver_is_read (receiver_username, is_read),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        connection.commit()
        print("All tables created successfully!")
        return True
        
    except Error as e:
        print(f"Error creating tables: {e}")
        return False
    finally:
        cursor.close()
        connection.close()

def insert_sample_data():
    """Insert sample data for testing"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Check if sample data already exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE username IN ('admin', 'seller1', 'rider1')")
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Insert sample users
            sample_users = [
                ('admin', 'admin@verdant.com', generate_password_hash('password123'), 'user', 'Admin User', '123 Admin Street', '09123456789'),
                ('seller1', 'seller1@verdant.com', generate_password_hash('password123'), 'seller', 'John Seller', '456 Seller Avenue', '09123456788'),
                ('rider1', 'rider1@verdant.com', generate_password_hash('password123'), 'rider', 'Mike Rider', '789 Rider Road', '09123456787')
            ]
            
            for user in sample_users:
                cursor.execute("""
                    INSERT INTO users (username, email, password, role, fullname, address, phone, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, user + (True,))
            
            # Update seller with store info
            cursor.execute("""
                UPDATE users SET store_name = %s, business_address = %s 
                WHERE username = %s
            """, ('Green Garden Store', '456 Seller Avenue, Business District', 'seller1'))
            
            # Update rider with vehicle info
            cursor.execute("""
                UPDATE users SET vehicle_type = %s, license_number = %s, is_approved = %s 
                WHERE username = %s
            """, ('motorcycle', 'DL123456789', True, 'rider1'))
            
            connection.commit()
            print("Sample data inserted successfully!")
        else:
            print("Sample data already exists.")
        
        return True
        
    except Error as e:
        print(f"Error inserting sample data: {e}")
        return False
    finally:
        cursor.close()
        connection.close()

def initialize_database():
    """Initialize the entire database"""
    print("Initializing Verdant Database...")
    
    # Create database
    create_database_if_not_exists()
    
    # Create tables
    if create_tables():
        # Insert sample data
        insert_sample_data()
        print("Database initialization completed successfully!")
        return True
    else:
        print("Database initialization failed!")
        return False

if __name__ == "__main__":
    initialize_database()