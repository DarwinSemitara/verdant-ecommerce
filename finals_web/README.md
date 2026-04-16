# 🌿 Verdant - Home & Garden E-Commerce Platform

A full-featured e-commerce platform for home and garden products, built with Flask and MySQL.

## 🎯 Features

### For Guests (Visitors)
- ✅ Browse all products from all sellers
- ✅ View product details
- ✅ Search and filter products
- ✅ Prompted to login for cart/purchase features

### For Buyers (Users)
- ✅ User registration and login
- ✅ Browse and search products
- ✅ View product details with reviews
- ✅ Add products to cart
- ✅ Place orders
- ✅ Profile management

### For Sellers
- ✅ Seller registration
- ✅ Store management (name, profile, cover image)
- ✅ Product management (add, edit, delete)
- ✅ Product listings with images
- ✅ Inventory tracking
- ✅ Store preview page
- ✅ Dashboard analytics

### For Riders
- ✅ Rider registration
- ✅ Dashboard (under development)
- ✅ Delivery management (coming soon)

### For Admins
- ✅ Admin dashboard
- ✅ User management
- ✅ Platform oversight
- ✅ Cashout request management

## 🛠️ Technology Stack

**Backend:**
- Python 3.8+
- Flask 2.2.2
- Flask-SQLAlchemy
- Flask-Login
- MySQL (via XAMPP)

**Frontend:**
- HTML5
- CSS3
- JavaScript
- Jinja2 Templates

**Database:**
- MySQL 8.0+
- phpMyAdmin (via XAMPP)

## 📋 Prerequisites

1. **Python 3.8+** - [Download](https://www.python.org/downloads/)
2. **XAMPP** - [Download](https://www.apachefriends.org/download.html)
3. **Text Editor** (VS Code recommended)

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start XAMPP
- Open XAMPP Control Panel
- Start Apache and MySQL services

### 3. Initialize Database
```bash
python db.py
```

### 4. Run Application
```bash
python app.py
```

### 5. Access Application
Open browser and go to: **http://localhost:5000/**

## 🔑 Default Credentials

**Admin:**
- Username: `admin`
- Password: `admin123`

**Sample Seller:**
- Username: `seller1`
- Password: `password123`

**Sample Rider:**
- Username: `rider1`
- Password: `password123`

## 📁 Project Structure

```
FINALS/
├── app.py                    # Main Flask application
├── db.py                     # Database setup script
├── requirements.txt          # Python dependencies
├── static/                   # Static files (CSS, JS, images)
│   ├── css/
│   ├── js/
│   ├── resources/
│   └── uploads/             # User uploaded files
│       └── products/        # Product images
├── templates/               # HTML templates
│   ├── guest_homepage.html
│   ├── user_homepage.html
│   ├── seller_dashboard.html
│   ├── product_detail.html
│   └── ...
└── models/                  # Database models
```

## 📚 Documentation

- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** - Complete installation guide
- **[DATABASE_EXPORT_GUIDE.md](DATABASE_EXPORT_GUIDE.md)** - Database export/import instructions

## 🎨 User Roles

| Role | Description | Access |
|------|-------------|--------|
| **Guest** | Unregistered visitor | Browse products, view details |
| **Buyer** | Registered customer | Shop, cart, orders, profile |
| **Seller** | Store owner | Manage store, products, inventory |
| **Rider** | Delivery personnel | Delivery management (coming soon) |
| **Admin** | Platform administrator | Full system access |

## 🔐 Security Features

- Password hashing (Werkzeug)
- Session management
- Role-based access control
- SQL injection prevention
- File upload validation
- CSRF protection

## 📸 Screenshots

### Guest Homepage
- Product grid display
- Search and filter options
- Login prompts for restricted features

### Seller Dashboard
- Store management
- Product inventory
- Analytics (coming soon)

### Product Detail Page
- Full product information
- Image display
- Reviews section (placeholder)
- Add to cart functionality

## 🚧 Upcoming Features

- [ ] Payment integration
- [ ] Order tracking
- [ ] Review and rating system
- [ ] Rider delivery management
- [ ] Email notifications
- [ ] Advanced analytics
- [ ] Product categories
- [ ] Wishlist functionality

## 🐛 Known Issues

- None currently reported

## 🤝 Contributing

This is a group project. To contribute:
1. Get the latest code
2. Import the latest database
3. Make your changes
4. Test thoroughly
5. Share updates with team

## 📞 Support

For setup issues, refer to:
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Installation help
- [DATABASE_EXPORT_GUIDE.md](DATABASE_EXPORT_GUIDE.md) - Database help

## 📄 License

This project is for educational purposes.

## 👥 Team

Developed by: [Your Team Name]

---

**Version**: 1.0  
**Last Updated**: November 2025  
**Status**: Active Development
