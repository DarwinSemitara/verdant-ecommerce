# Checkout and Order Management Routes
from flask import session, request, jsonify, redirect, url_for, render_template, flash
from firestore_db import db, get_user_by_username, get_product_by_id, products_v2_ref, product_variations_ref
from datetime import datetime
from google.cloud.firestore import SERVER_TIMESTAMP

def register_checkout_routes(app):
    
    @app.route('/checkout', methods=['POST'])
    def checkout():
        if 'username' not in session or session.get('role') != 'user':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        try:
            # Get user data
            user = get_user_by_username(session['username'])
            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            
            # Check if user account is verified
            if not user.get('is_verified', False):
                return jsonify({
                    'success': False,
                    'message': 'Please verify your account before placing orders.',
                    'requires_verification': True,
                    'verification_status': 'not_verified'
                }), 403
            
            # Check if user account is approved by admin
            if not user.get('is_approved', False):
                return jsonify({
                    'success': False,
                    'message': 'Your verification is under review. Please wait for admin approval before placing orders.',
                    'requires_verification': True,
                    'verification_status': 'pending_approval'
                }), 403
            
            # Get selected cart IDs and payment method from request
            data = request.get_json() or {}
            selected_cart_ids = data.get('cart_ids', [])
            payment_method = data.get('payment_method', 'cod')
            
            if not selected_cart_ids:
                return jsonify({'success': False, 'message': 'No items selected'}), 400
            
            shipping_address = user.get('address', 'No address provided')
            user_latitude = user.get('latitude')
            user_longitude = user.get('longitude')

            # Require pinned location before placing an order
            if user_latitude is None or user_longitude is None:
                return jsonify({
                    'success': False,
                    'message': 'Please pin your delivery location (latitude & longitude) in your account before placing an order.'
                }), 400
            
            # Get selected cart items
            cart_items = []
            print(f"DEBUG: Selected cart IDs: {selected_cart_ids}")
            print(f"DEBUG: Session username: {session['username']}")
            
            # Get user_id (which is the username in Firestore)
            user_id = user['id']
            
            for cart_id in selected_cart_ids:
                cart_doc = db.collection('cart').document(cart_id).get()
                print(f"DEBUG: Cart {cart_id} exists: {cart_doc.exists}")
                if cart_doc.exists:
                    cart_data = cart_doc.to_dict()
                    print(f"DEBUG: Cart data user_id: {cart_data.get('user_id')}")
                    if cart_data.get('user_id') == user_id:
                        cart_data['id'] = cart_doc.id
                        cart_items.append(cart_data)
                        print(f"DEBUG: Added cart item {cart_id}")
            
            print(f"DEBUG: Total cart items found: {len(cart_items)}")
            
            if not cart_items:
                return jsonify({'success': False, 'message': 'Cart is empty'}), 400
            
            # Group items by seller
            orders_by_seller = {}
            for cart_item in cart_items:
                product_id = cart_item['product_id']
                variation_id = cart_item.get('variation_id')
                quantity = cart_item['quantity']
                
                # Get product from V2 collection
                product_doc = products_v2_ref.document(product_id).get()
                if not product_doc.exists:
                    continue
                
                product_data = product_doc.to_dict()
                seller_username = product_data.get('seller_username')
                
                # Determine price and stock based on whether it has variation
                if variation_id:
                    # Get variation details
                    variation_doc = product_variations_ref.document(variation_id).get()
                    if not variation_doc.exists:
                        continue
                    
                    variation_data = variation_doc.to_dict()
                    price = float(variation_data.get('price', 0))
                    stock = variation_data.get('stock', 0)
                    product_name = variation_data.get('name', 'Unknown')
                else:
                    # Product without variation
                    price = float(product_data.get('price', 0))
                    stock = product_data.get('stock', 0)
                    product_name = product_data.get('product_name', 'Unknown')
                
                # Check stock availability
                if quantity > stock:
                    return jsonify({
                        'success': False, 
                        'message': f'Insufficient stock for {product_name}'
                    }), 400
                
                if seller_username not in orders_by_seller:
                    orders_by_seller[seller_username] = []
                orders_by_seller[seller_username].append({
                    'cart_id': cart_item['id'],
                    'product_id': product_id,
                    'variation_id': variation_id,
                    'quantity': quantity,
                    'price': price
                })
            
            # Create orders for each seller
            for seller_username, items in orders_by_seller.items():
                # Calculate total
                total_amount = sum(item['quantity'] * item['price'] for item in items)
                
                # Create order
                order_ref = db.collection('orders').document()
                order_data = {
                    'username': session['username'],
                    'seller_username': seller_username,
                    'total_amount': total_amount,
                    'status': 'pending',
                    'shipping_address': shipping_address,
                    'order_date': SERVER_TIMESTAMP,
                    'delivery_date': None,
                    'rider_username': None,
                    'rejection_reason': None
                }
                order_ref.set(order_data)
                order_id = order_ref.id
                
                # Create notification for seller about new order
                from app import format_public_order_id
                public_order_id = format_public_order_id(order_id)
                seller_notification_ref = db.collection('notifications').document()
                seller_notification_ref.set({
                    'username': seller_username,
                    'order_id': order_id,
                    'type': 'new_order',
                    'title': 'New Order Received',
                    'message': f'You have a new order #{public_order_id} from {session["username"]}. Total: ₱{total_amount:.2f}',
                    'is_read': False,
                    'created_at': SERVER_TIMESTAMP
                })
                
                # Create order items and update stock
                for item in items:
                    order_item_data = {
                        'order_id': order_id,
                        'product_id': item['product_id'],
                        'quantity': item['quantity'],
                        'unit_price': item['price'],
                        'total_price': item['quantity'] * item['price']
                    }
                    
                    # Add variation_id if present
                    if item.get('variation_id'):
                        order_item_data['variation_id'] = item['variation_id']
                    
                    order_item_ref = db.collection('order_items').document()
                    order_item_ref.set(order_item_data)
                    
                    # Remove from cart
                    db.collection('cart').document(item['cart_id']).delete()
            
            return jsonify({'success': True, 'message': 'Order placed successfully'}), 200
            
        except Exception as e:
            print(f"Error during checkout: {e}")
            return jsonify({'success': False, 'message': 'Error processing order'}), 500
    
    @app.route('/seller/orders')
    def seller_orders():
        if 'username' not in session or session.get('role') != 'seller':
            return redirect(url_for('login_page'))
        
        try:
            # Get seller data
            seller = get_user_by_username(session['username'])
            if not seller:
                return redirect(url_for('login_page'))
            
            profile_picture = seller.get('profile_picture')
            seller_approved = seller.get('seller_approved', False)
            
            print(f"DEBUG: Seller: {session['username']}, Approved: {seller_approved}")
            
            # Check if seller is approved
            if not seller_approved:
                flash('Your seller application is pending approval. You cannot access orders yet.', 'warning')
                return redirect(url_for('seller_dashboard'))
            
            # Check if this seller has any products in products_v2 (NEW)
            products_query = products_v2_ref.where('seller_username', '==', session['username']).limit(1).stream()
            product_count = sum(1 for _ in products_query)
            print(f"DEBUG: Seller has {product_count} products in products_v2")
            
            if product_count == 0:
                orders = []
            else:
                # Get all orders for this seller (removed order_by to avoid index requirement)
                orders_query = db.collection('orders').where('seller_username', '==', session['username']).stream()
                
                orders = []
                for order_doc in orders_query:
                    order_data = order_doc.to_dict()
                    order_id = order_doc.id
                    
                    print(f"DEBUG: Processing order {order_id} for seller {session['username']}")
                    
                    # Get order items for this order
                    items_query = db.collection('order_items').where('order_id', '==', order_id).stream()
                    items = []
                    seller_total = 0
                    
                    for item_doc in items_query:
                        item_data = item_doc.to_dict()
                        product_id = item_data['product_id']
                        variation_id = item_data.get('variation_id')
                        
                        print(f"DEBUG: Order item - product_id: {product_id}, variation_id: {variation_id}")
                        
                        # Get product from V2 collection
                        product_doc = products_v2_ref.document(product_id).get()
                        
                        if product_doc.exists:
                            product_data = product_doc.to_dict()
                            
                            if product_data.get('seller_username') == session['username']:
                                # If has variation, get variation details
                                if variation_id:
                                    variation_doc = product_variations_ref.document(variation_id).get()
                                    if variation_doc.exists:
                                        variation_data = variation_doc.to_dict()
                                        # For variations, show variation name only
                                        product_name = variation_data.get('name', 'Unknown')
                                        product_image = variation_data.get('image', product_data.get('image', 'default.jpg'))
                                    else:
                                        product_name = product_data.get('product_name', 'Unknown')
                                        product_image = product_data.get('image', 'default.jpg')
                                else:
                                    product_name = product_data.get('product_name', 'Unknown')
                                    product_image = product_data.get('image', 'default.jpg')
                                
                                # Truncate name if longer than 8 characters
                                if len(product_name) > 8:
                                    display_name = product_name[:6] + '..'
                                else:
                                    display_name = product_name
                                
                                items.append({
                                    'product_id': product_id,
                                    'name': display_name,
                                    'full_name': product_name,  # Keep full name for tooltips
                                    'quantity': item_data['quantity'],
                                    'unit_price': float(item_data['unit_price']),
                                    'total_price': float(item_data['total_price']),
                                    'image': product_image
                                })
                                seller_total += float(item_data['total_price'])
                    
                    if items:  # Only include orders with this seller's products
                        # Get rider info if assigned
                        rider_username = order_data.get('rider_username')
                        rider_info = None
                        if rider_username:
                            rider = get_user_by_username(rider_username)
                            if rider:
                                rider_info = rider.get('username')
                        
                        orders.append({
                            'id': order_id,
                            'customer_username': order_data['username'],
                            'total_amount': seller_total,
                            'status': order_data['status'],
                            'shipping_address': order_data.get('shipping_address', 'No address provided'),
                            'order_date': order_data.get('order_date'),
                            'rejection_reason': order_data.get('rejection_reason'),
                            'rider_id': order_data.get('rider_username'),
                            'rider_username': rider_info,
                            'items': items
                        })
            
            # Sort orders by order_date in Python instead of Firestore
            orders.sort(key=lambda x: x.get('order_date') or datetime.min, reverse=True)
            
            print(f"DEBUG: Final orders count: {len(orders)}")
            if orders:
                print(f"DEBUG: First order details: {orders[0]}")
            
            return render_template('seller_orders.html', 
                                 orders=orders, 
                                 profile_picture=profile_picture, 
                                 seller_approved=seller_approved)
            
        except Exception as e:
            import traceback
            error_msg = f"Error in seller_orders: {str(e)}"
            print(error_msg)
            print("Full traceback:")
            print(traceback.format_exc())
            
            return render_template('seller_orders.html', 
                                 orders=[], 
                                 profile_picture=None, 
                                 seller_approved=True,
                                 error_message=error_msg)
    
    @app.route('/seller/order/<order_id>/accept', methods=['POST'])
    def seller_accept_order(order_id):
        if 'username' not in session or session.get('role') != 'seller':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        try:
            order_id_str = str(order_id)
            
            # Get order
            order_ref = db.collection('orders').document(order_id_str)
            order_doc = order_ref.get()
            
            if not order_doc.exists:
                return jsonify({'success': False, 'message': 'Order not found'}), 404
            
            order_data = order_doc.to_dict()
            
            # Verify order belongs to this seller
            if order_data['seller_username'] != session['username']:
                return jsonify({'success': False, 'message': 'Order not found'}), 404
            
            if order_data['status'] != 'pending':
                return jsonify({'success': False, 'message': 'Order already processed'}), 400
            
            # Get order items to update stock
            items_query = db.collection('order_items').where('order_id', '==', order_id_str).stream()
            
            for item_doc in items_query:
                item_data = item_doc.to_dict()
                product_id = item_data['product_id']
                variation_id = item_data.get('variation_id')
                quantity = item_data['quantity']
                
                # Check if order item has variation
                if variation_id:
                    # Update variation stock
                    variation_ref = product_variations_ref.document(variation_id)
                    variation_doc = variation_ref.get()
                    
                    if variation_doc.exists:
                        variation_data = variation_doc.to_dict()
                        current_stock = variation_data.get('stock', 0)
                        
                        if current_stock < quantity:
                            return jsonify({'success': False, 'message': 'Insufficient stock'}), 400
                        
                        # Update variation stock
                        variation_ref.update({'stock': current_stock - quantity})
                else:
                    # Update product stock (no variation)
                    product_ref = products_v2_ref.document(product_id)
                    product_doc = product_ref.get()
                    
                    if product_doc.exists:
                        product_data = product_doc.to_dict()
                        if product_data.get('seller_username') == session['username']:
                            current_stock = product_data.get('stock', 0)
                            
                            if current_stock < quantity:
                                return jsonify({'success': False, 'message': 'Insufficient stock'}), 400
                            
                            # Update product stock
                            product_ref.update({'stock': current_stock - quantity})
            
            # Update order status
            order_ref.update({'status': 'accepted'})
            
            # Create notification for user
            notification_ref = db.collection('notifications').document()
            notification_ref.set({
                'username': order_data['username'],
                'order_id': order_id_str,
                'type': 'order_accepted',
                'title': 'Order Accepted',
                'message': 'Your order has been accepted by the seller and is being prepared.',
                'is_read': False,
                'created_at': SERVER_TIMESTAMP
            })
            
            # Send automated thank you message to customer
            try:
                from datetime import datetime
                
                # Get order items for the message
                items_query = db.collection('order_items').where('order_id', '==', order_id_str).stream()
                product_details = []
                for item_doc in items_query:
                    item_data = item_doc.to_dict()
                    product_name = item_data.get('product_name', 'Unknown Product')
                    variation_name = item_data.get('variation_name', '')
                    quantity = item_data.get('quantity', 1)
                    
                    if variation_name:
                        product_details.append(f"{product_name} ({variation_name}) x{quantity}")
                    else:
                        product_details.append(f"{product_name} x{quantity}")
                
                # Format order ID for display
                from app import format_public_order_id
                public_order_id = format_public_order_id(order_id_str)
                
                # Get current date
                current_date = datetime.now().strftime("%B %d, %Y")
                
                # Create items text
                if len(product_details) == 1:
                    items_text = f"\n\n📦 Product: {product_details[0]}"
                elif len(product_details) > 1:
                    items_list = '\n'.join([f"  • {detail}" for detail in product_details[:5]])
                    if len(product_details) > 5:
                        items_list += f"\n  • ...and {len(product_details) - 5} more"
                    items_text = f"\n\n📦 Products:\n{items_list}"
                else:
                    items_text = ""
                
                # Create the message with actual product names and date
                thank_you_message = f"""🎉 Thank you for your order!

Your order #{public_order_id} has been accepted on {current_date} and is being prepared for shipment.{items_text}

I'm here to help if you have any questions about your order or need assistance with anything. Feel free to message me anytime!

Best regards,
{session['username']}"""
                
                # Send message to customer
                message_ref = db.collection('messages').document()
                message_ref.set({
                    'sender_username': session['username'],
                    'receiver_username': order_data['username'],
                    'message_text': thank_you_message,
                    'is_read': False,
                    'created_at': SERVER_TIMESTAMP
                })
                
                print(f"Successfully sent order acceptance message to {order_data['username']}")
            except Exception as msg_error:
                print(f"Error sending order acceptance message: {msg_error}")
                # Don't fail the order acceptance if message fails
            
            return jsonify({'success': True, 'message': 'Order accepted successfully'}), 200
            
        except Exception as e:
            print(f"Error accepting order: {e}")
            return jsonify({'success': False, 'message': 'Error accepting order'}), 500
    
    @app.route('/seller/order/<order_id>/ship', methods=['POST'])
    def seller_ship_order(order_id):
        """Legacy endpoint disabled: seller-side shipping is no longer supported."""
        if 'username' not in session or session.get('role') != 'seller':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401

        # Endpoint intentionally disabled to prevent breaking the rider order flow
        return jsonify({
            'success': False,
            'message': 'This action is no longer available. Orders are handed off to riders automatically.'
        }), 410
    
    @app.route('/seller/order/<order_id>/reject', methods=['POST'])
    def seller_reject_order(order_id):
        if 'username' not in session or session.get('role') != 'seller':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        data = request.get_json()
        rejection_reason = data.get('reason', '')
        
        try:
            order_id_str = str(order_id)
            
            # Get order
            order_ref = db.collection('orders').document(order_id_str)
            order_doc = order_ref.get()
            
            if not order_doc.exists:
                return jsonify({'success': False, 'message': 'Order not found'}), 404
            
            order_data = order_doc.to_dict()
            
            # Verify order belongs to this seller
            if order_data['seller_username'] != session['username']:
                return jsonify({'success': False, 'message': 'Order not found'}), 404
            
            if order_data['status'] != 'pending':
                return jsonify({'success': False, 'message': 'Order already processed'}), 400
            
            # Update order status
            order_ref.update({
                'status': 'rejected',
                'rejection_reason': rejection_reason
            })
            
            # Create notification for user
            notification_message = f'Your order has been rejected by the seller.'
            if rejection_reason:
                notification_message += f' Reason: {rejection_reason}'
            
            notification_ref = db.collection('notifications').document()
            notification_ref.set({
                'username': order_data['username'],
                'order_id': order_id_str,
                'type': 'order_rejected',
                'title': 'Order Rejected',
                'message': notification_message,
                'is_read': False,
                'created_at': SERVER_TIMESTAMP
            })
            
            return jsonify({'success': True, 'message': 'Order rejected successfully'}), 200
            
        except Exception as e:
            print(f"Error rejecting order: {e}")
            return jsonify({'success': False, 'message': 'Error rejecting order'}), 500
    
    @app.route('/user/orders')
    def user_orders():
        if 'username' not in session:
            return redirect(url_for('login_page'))

        print(f"DEBUG /user/orders session: username={session.get('username')}, role={session.get('role')}")

        try:
            user = get_user_by_username(session['username'])
            if not user:
                return redirect(url_for('login_page'))

            profile_picture = user.get('profile_picture')

            # Get all orders for this user (removed order_by to avoid index requirement)
            orders_query = db.collection('orders').where('username', '==', session['username']).stream()

            orders = []
            for order_doc in orders_query:
                order_data = order_doc.to_dict()
                order_id = order_doc.id
                
                # Get seller info
                seller = get_user_by_username(order_data['seller_username'])
                seller_store_name = seller.get('store_name', 'Unknown Store') if seller else 'Unknown Store'
                
                # Get rider info if assigned
                rider = None
                rider_username = order_data.get('rider_username')
                if rider_username:
                    rider_data = get_user_by_username(rider_username)
                    if rider_data:
                        rider = {
                            'username': rider_data['username'],
                            'profile_picture': rider_data.get('profile_picture')
                        }
                
                # Get order items
                items_query = db.collection('order_items').where('order_id', '==', order_id).stream()
                items = []
                
                for item_doc in items_query:
                    item_data = item_doc.to_dict()
                    product_id = item_data['product_id']
                    variation_id = item_data.get('variation_id')
                    
                    print(f"DEBUG: Processing order item - product_id: {product_id}, variation_id: {variation_id}")
                    
                    # Try to get product from V2 collection first
                    product_doc = products_v2_ref.document(product_id).get()
                    
                    if product_doc.exists:
                        product_data = product_doc.to_dict()
                        print(f"DEBUG: Found in products_v2 - keys: {list(product_data.keys())}")
                        
                        # If has variation, get variation details
                        if variation_id:
                            variation_doc = product_variations_ref.document(variation_id).get()
                            if variation_doc.exists:
                                variation_data = variation_doc.to_dict()
                                print(f"DEBUG: Variation found - variation_name: {variation_data.get('variation_name')}")
                                # For variations, show variation name only (product name is the parent)
                                product_name = variation_data.get('variation_name', 'Unknown Variation')
                                product_image = variation_data.get('image', product_data.get('image', ''))
                            else:
                                print(f"DEBUG: Variation {variation_id} not found")
                                product_name = product_data.get('product_name', 'Unknown Product')
                                product_image = product_data.get('image', '')
                        else:
                            product_name = product_data.get('product_name', 'Unknown Product')
                            product_image = product_data.get('image', '')
                        
                        print(f"DEBUG: Final product_name from v2: {product_name}")
                    else:
                        # Fallback to old products collection
                        print(f"DEBUG: Product {product_id} not found in products_v2, trying old collection")
                        old_product = get_product_by_id(product_id)
                        if old_product:
                            product_name = old_product.get('product_name', 'Unknown Product')
                            product_image = old_product.get('image', '')
                            print(f"DEBUG: Found in old products - name: {product_name}")
                        else:
                            print(f"DEBUG: Product {product_id} not found in any collection")
                            product_name = 'Unknown Product'
                            product_image = ''
                    
                    # Truncate name if longer than 8 characters
                    if len(product_name) > 8:
                        display_name = product_name[:6] + '..'
                    else:
                        display_name = product_name
                    
                    items.append({
                        'product_id': product_id,
                        'name': display_name,
                        'full_name': product_name,  # Keep full name for tooltips
                        'quantity': item_data.get('quantity', 0),
                        'unit_price': float(item_data.get('unit_price', 0.0)),
                        'total_price': float(item_data.get('total_price', 0.0)),
                        'image': product_image
                    })
                
                orders.append({
                    'id': order_id,
                    'total_amount': float(order_data.get('total_amount', 0.0)),
                    'status': order_data.get('status', 'unknown'),
                    'order_date': order_data.get('order_date'),
                    'delivered_at': order_data.get('delivery_date'),
                    'shipping_address': order_data.get('shipping_address', 'No address provided'),
                    'seller_username': order_data.get('seller_username', 'Unknown'),
                    'seller_store_name': seller_store_name,
                    'items': items,
                    'rider': rider
                })

            to_be_delivered = [
                o for o in orders
                if o['status'] not in ('delivered', 'cancelled', 'rejected')
            ]
            delivered_orders = [o for o in orders if o['status'] == 'delivered']

            return render_template(
                'user_orders.html',
                profile_picture=profile_picture,
                to_be_delivered=to_be_delivered,
                delivered_orders=delivered_orders
            )

        except Exception as e:
            print(f"Error loading user orders: {e}")
            import traceback
            traceback.print_exc()
            return render_template(
                'user_orders.html',
                profile_picture=None,
                to_be_delivered=[],
                delivered_orders=[]
            )
    
    @app.route('/notifications')
    def get_notifications():
        if 'username' not in session:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        try:
            # Get notifications for this user (removed order_by to avoid index requirement)
            notifications_query = db.collection('notifications').where('username', '==', session['username']).limit(50).stream()
            
            notifications = []
            unread_count = 0
            
            for notif_doc in notifications_query:
                notif_data = notif_doc.to_dict()
                created_at = notif_data.get('created_at')
                
                notifications.append({
                    'id': notif_doc.id,
                    'order_id': notif_data.get('order_id'),
                    'type': notif_data.get('type'),
                    'title': notif_data.get('title'),
                    'message': notif_data.get('message'),
                    'is_read': notif_data.get('is_read', False),
                    'created_at': created_at,
                    'created_at_str': created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else None
                })
                
                if not notif_data.get('is_read', False):
                    unread_count += 1
            
            # Sort by created_at in Python instead of Firestore
            from datetime import datetime
            notifications.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
            
            # Convert dates to strings after sorting
            for notif in notifications:
                notif['created_at'] = notif['created_at_str']
                del notif['created_at_str']
            
            return jsonify({
                'success': True,
                'notifications': notifications,
                'unread_count': unread_count
            }), 200
            
        except Exception as e:
            print(f"Error fetching notifications: {e}")
            return jsonify({'success': False, 'message': 'Error fetching notifications'}), 500
    
    @app.route('/notifications/<notification_id>/read', methods=['POST'])
    def mark_notification_read(notification_id):
        if 'username' not in session:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        try:
            # Get notification
            notif_ref = db.collection('notifications').document(notification_id)
            notif_doc = notif_ref.get()
            
            if not notif_doc.exists:
                return jsonify({'success': False, 'message': 'Notification not found'}), 404
            
            notif_data = notif_doc.to_dict()
            
            # Verify notification belongs to this user
            if notif_data['username'] != session['username']:
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            
            # Mark as read
            notif_ref.update({'is_read': True})
            
            return jsonify({'success': True}), 200
            
        except Exception as e:
            print(f"Error marking notification as read: {e}")
            return jsonify({'success': False, 'message': 'Error updating notification'}), 500
