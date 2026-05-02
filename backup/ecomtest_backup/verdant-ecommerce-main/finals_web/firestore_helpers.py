"""
Helper functions for complex Firestore queries
Used by app.py for migrated functionality
"""

from firestore_db import (
    db, users_ref, products_ref, orders_ref, cart_ref,
    get_user_by_username, get_products, get_orders
)
from datetime import datetime, timedelta
from google.cloud import firestore


def get_top_products():
    """Get top 3 best-selling products by units sold in last 30 days"""
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Get all completed orders from last 30 days
    all_orders = orders_ref.where('status', '==', 'completed')\
        .where('order_date', '>=', thirty_days_ago)\
        .stream()
    
    # Calculate product sales
    product_sales = {}
    for order_doc in all_orders:
        order_data = order_doc.to_dict()
        order_items = order_data.get('items', [])
        
        for item in order_items:
            product_id = item.get('product_id')
            if product_id not in product_sales:
                product_sales[product_id] = {
                    'product_id': product_id,
                    'total_quantity': 0,
                    'total_revenue': 0,
                    'order_count': 0
                }
            product_sales[product_id]['total_quantity'] += item.get('quantity', 0)
            product_sales[product_id]['total_revenue'] += float(item.get('total_price', 0))
            product_sales[product_id]['order_count'] += 1
    
    # Sort by total quantity sold and get top 3
    sorted_products = sorted(product_sales.values(), key=lambda x: x['total_quantity'], reverse=True)
    return sorted_products[:3]


def get_order_status_breakdown():
    """Get breakdown of order statuses"""
    status_counts = {}
    statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled', 'completed']
    
    for status in statuses:
        orders = orders_ref.where('status', '==', status).stream()
        status_counts[status] = len(list(orders))
    
    return status_counts


def get_order_status_summary():
    """Aggregate order statuses into friendly groups for dashboard."""
    delay_threshold_days = 7
    threshold_dt = datetime.utcnow() - timedelta(days=delay_threshold_days)
    
    # Get all orders
    all_orders = list(orders_ref.stream())
    
    pending_payment = sum(1 for o in all_orders if o.to_dict().get('status') == 'pending')
    ready_to_ship = sum(1 for o in all_orders if o.to_dict().get('status') == 'processing')
    
    delayed_exception = sum(
        1 for o in all_orders
        if o.to_dict().get('order_date') and o.to_dict()['order_date'] < threshold_dt
        and o.to_dict().get('status') in ['pending', 'processing', 'shipped']
    )
    
    completed = sum(1 for o in all_orders if o.to_dict().get('status') == 'completed')
    
    return {
        'pending_payment': pending_payment,
        'ready_to_ship': ready_to_ship,
        'delayed_exception': delayed_exception,
        'completed': completed,
        'delay_threshold_days': delay_threshold_days,
    }


def get_sales_chart_data():
    """Get sales data for chart visualization over last 30 days"""
    now = datetime.utcnow()
    chart_data = []
    
    # Get all completed orders
    completed_orders = list(orders_ref.where('status', '==', 'completed').stream())
    
    # Get daily sales for last 30 days
    for i in range(30):
        date = now - timedelta(days=i)
        date_start = datetime(date.year, date.month, date.day, 0, 0, 0)
        date_end = datetime(date.year, date.month, date.day, 23, 59, 59)
        
        daily_orders = [
            o for o in completed_orders
            if o.to_dict().get('order_date') and date_start <= o.to_dict()['order_date'] <= date_end
        ]
        
        daily_revenue = sum(float(o.to_dict().get('total_amount', 0)) for o in daily_orders)
        daily_orders_count = len(daily_orders)
        
        chart_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'revenue': daily_revenue,
            'orders': daily_orders_count
        })
    
    # Reverse to get chronological order
    chart_data.reverse()
    
    # Calculate week-over-week growth
    current_week_revenue = sum(item['revenue'] for item in chart_data[-7:])
    previous_week_revenue = sum(item['revenue'] for item in chart_data[-14:-7])
    
    if previous_week_revenue > 0:
        week_growth = ((current_week_revenue - previous_week_revenue) / previous_week_revenue) * 100
    else:
        week_growth = 100.0 if current_week_revenue > 0 else 0.0
    
    return {
        'chart_data': chart_data,
        'week_growth': round(week_growth, 1),
        'current_week_revenue': current_week_revenue,
        'previous_week_revenue': previous_week_revenue
    }


def get_dashboard_summary():
    """Get comprehensive dashboard summary data"""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    week_ago = now - timedelta(days=7)
    
    # Get all orders
    all_orders = list(orders_ref.stream())
    completed_orders = [o for o in all_orders if o.to_dict().get('status') == 'completed']
    
    # Total revenue
    total_revenue = sum(float(o.to_dict().get('total_amount', 0)) for o in completed_orders)
    
    # Total orders
    total_orders = len(all_orders)
    
    # Pending orders
    pending_orders = sum(1 for o in all_orders if o.to_dict().get('status') == 'pending')
    
    # Get oldest pending order
    pending_order_docs = [o for o in all_orders if o.to_dict().get('status') == 'pending']
    oldest_pending_order_id = None
    if pending_order_docs:
        oldest = min(pending_order_docs, key=lambda o: o.to_dict().get('order_date', datetime.max))
        oldest_pending_order_id = oldest.id
    
    # Stock alerts
    all_products = get_products()
    low_stock_count = sum(1 for p in all_products if 0 < p.get('stock_quantity', 0) <= 10 and p.get('is_active', True))
    out_of_stock_count = sum(1 for p in all_products if p.get('stock_quantity', 0) == 0 and p.get('is_active', True))
    total_stock_alerts = low_stock_count + out_of_stock_count
    
    # Recent activity (last 7 days)
    recent_orders = sum(
        1 for o in all_orders
        if o.to_dict().get('order_date') and o.to_dict()['order_date'] >= week_ago
    )
    recent_revenue = sum(
        float(o.to_dict().get('total_amount', 0))
        for o in completed_orders
        if o.to_dict().get('order_date') and o.to_dict()['order_date'] >= week_ago
    )
    
    return {
        'total_revenue': float(total_revenue),
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'oldest_pending_order_id': oldest_pending_order_id,
        'stock_alerts': total_stock_alerts,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'available_balance': 0.0,  # TODO: Implement wallet
        'recent_orders': recent_orders,
        'recent_revenue': float(recent_revenue)
    }
