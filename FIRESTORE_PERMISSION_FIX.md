# Firestore Permission Fix for Rider Actions

## Problem
When riders tried to accept deliveries or update order status, they got a Firestore permission error:
```
Error: [cloud_firestore/permission-denied] Missing or insufficient permissions
```

This happened because riders don't have direct write access to the `orders` collection in Firestore security rules.

## Solution
Routed all rider order actions through Flask API endpoints (similar to how messages work).

### Changes Made

#### 1. Added Flask API Endpoints
**File:** `finals_web/app.py`

**New Endpoints:**

##### `/api/mobile/rider/accept_delivery` (POST)
- Accepts an order for delivery
- Updates order status from 'accepted' to 'picking_up'
- Assigns rider to the order
- Stores shipping fee

**Request Body:**
```json
{
  "order_id": "string",
  "rider_username": "string",
  "shipping_fee": 38.0
}
```

**Response:**
```json
{
  "success": true,
  "message": "Delivery accepted successfully"
}
```

##### `/api/mobile/rider/update_status` (POST)
- Updates order status (picked_up or delivered)
- Verifies rider is assigned to the order
- If status is 'delivered', adds shipping fee to rider balance

**Request Body:**
```json
{
  "order_id": "string",
  "status": "picked_up" | "delivered",
  "rider_username": "string"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Status updated successfully"
}
```

#### 2. Updated Flutter Rider Screen
**File:** `finals_app/lib/screens/rider_screen.dart`

**Modified Methods:**

##### `_acceptDelivery()`
- Changed from direct Firestore write to HTTP POST request
- Calls `/api/mobile/rider/accept_delivery`
- Handles success/error responses
- Shows appropriate snackbar messages

##### `_updateStatus()` (in _RiderDeliveriesPage)
- Changed from direct Firestore write to HTTP POST request
- Calls `/api/mobile/rider/update_status`
- Removed local balance update logic (now handled by backend)
- Handles success/error responses

## How It Works Now

### Accept Delivery Flow:
1. Rider clicks "Accept Delivery" button
2. Flutter app sends POST request to Flask API
3. Flask validates the request
4. Flask updates Firestore with proper permissions
5. Flask returns success/error response
6. Flutter shows result to rider

### Update Status Flow:
1. Rider clicks "Mark as Picked Up" or "Mark as Delivered"
2. Flutter app sends POST request to Flask API
3. Flask validates rider is assigned to order
4. Flask updates order status in Firestore
5. If delivered, Flask adds shipping fee to rider balance
6. Flask returns success/error response
7. Flutter refreshes deliveries list

## Benefits

1. **Security:** Riders can't directly modify orders in Firestore
2. **Validation:** Flask validates all requests before updating database
3. **Authorization:** Flask checks rider is assigned to order
4. **Consistency:** All order updates go through controlled API
5. **Error Handling:** Better error messages and handling
6. **Audit Trail:** All actions logged on server side

## Testing

### Test Accept Delivery:
1. Login as rider
2. Go to home page
3. See order in "Ready for Pickup"
4. Click "Accept Delivery"
5. Should see success message
6. Order should move to Deliveries tab

### Test Update Status:
1. Go to Deliveries tab
2. In "Picking Up" section, click "Mark as Picked Up"
3. Should see success message
4. Order should move to "Picked Up" tab
5. Click "Mark as Delivered"
6. Should see success message
7. Order should move to "Delivered" tab
8. Check balance on home page - should increase

### Expected Behavior:
- ✅ No permission errors
- ✅ Orders update correctly
- ✅ Balance increases on delivery
- ✅ Status changes reflect immediately
- ✅ Error messages are clear

## Error Handling

### Possible Errors:
1. **Order not found:** Returns 404 with message
2. **Order not available:** Returns 400 if status is not 'accepted'
3. **Unauthorized:** Returns 403 if rider not assigned to order
4. **Invalid status:** Returns 400 if status is not 'picked_up' or 'delivered'
5. **Network error:** Shows error snackbar in Flutter app

### Error Messages:
- "Missing required fields" - Request missing data
- "Order not found" - Order ID doesn't exist
- "Order is not available for pickup" - Order already assigned or wrong status
- "Unauthorized" - Rider trying to update someone else's order
- "Invalid status" - Status must be 'picked_up' or 'delivered'

## Firestore Security Rules

The current Firestore rules don't allow riders to write to orders collection.
This is correct and secure. All rider actions should go through Flask API.

**Current Rule (Correct):**
```javascript
match /orders/{orderId} {
  allow read: if request.auth != null;
  allow write: if false; // Only Flask can write
}
```

**DO NOT change this rule.** The Flask API handles all writes with proper validation.

## Files Modified

1. `finals_web/app.py` - Added 2 new API endpoints
2. `finals_app/lib/screens/rider_screen.dart` - Updated 2 methods to use API

## Related Documentation

- See `RIDER_DELIVERY_SYSTEM_COMPLETE.md` for full system overview
- See `TESTING_GUIDE_RIDER_SYSTEM.md` for comprehensive testing guide
