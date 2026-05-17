# Testing Guide: Rider Delivery System

## Quick Test Scenarios

### Scenario 1: Complete Order Flow
**Objective:** Test the entire order lifecycle from user checkout to rider delivery

1. **User Side (Flutter App):**
   - Login as a verified user
   - Add items to cart (try different price ranges to test shipping fee)
   - Go to cart and select items
   - Click "Checkout"
   - Verify shipping fee is displayed correctly:
     - Order ≤ ₱1000 → ₱38 shipping
     - Order ₱3000 → ₱78 shipping
     - Order ₱6000 → ₱158 shipping
   - Confirm and place order

2. **Seller Side (Web):**
   - Login as seller
   - Go to Orders page
   - Find the new order (status: pending)
   - Click "Accept Order"
   - Verify status changes to "accepted"

3. **Rider Side (Flutter App):**
   - Login as approved rider
   - Pull down to refresh home page
   - See order in "Ready for Pickup" section
   - Verify shipping fee shows as "Your Earnings"
   - Click "Accept Delivery"
   - Go to "Deliveries" tab
   - Verify order appears in "Picking Up" section

4. **Mark as Picked Up:**
   - In "Picking Up" tab, click "Mark as Picked Up"
   - Verify order moves to "Picked Up" tab

5. **Mark as Delivered:**
   - In "Picked Up" tab, click "Mark as Delivered"
   - Verify order moves to "Delivered" tab
   - Check rider balance on home page - should increase by shipping fee amount

6. **User Side Verification:**
   - Go to Orders page
   - Verify order status shows "delivered"

### Scenario 2: Shipping Fee Calculation Test
**Objective:** Verify shipping fee calculates correctly for different order amounts

Test these order totals:

| Test | Items Total | Expected Shipping | Expected Total |
|------|-------------|-------------------|----------------|
| 1 | ₱500 | ₱38 | ₱538 |
| 2 | ₱1000 | ₱38 | ₱1038 |
| 3 | ₱1500 | ₱78 | ₱1578 |
| 4 | ₱3000 | ₱78 | ₱3078 |
| 5 | ₱3300 | ₱118 | ₱3418 |
| 6 | ₱5000 | ₱118 | ₱5118 |
| 7 | ₱6000 | ₱158 | ₱6158 |

**Steps:**
1. Add items to cart to reach each test amount
2. Go to checkout
3. Verify shipping fee matches expected value
4. Verify total = items + shipping

### Scenario 3: Rider Balance Accumulation
**Objective:** Test that rider earnings accumulate correctly

1. Start with rider balance at ₱0 (or note starting balance)
2. Accept and deliver 3 orders with different shipping fees:
   - Order 1: ₱500 items → ₱38 shipping
   - Order 2: ₱3000 items → ₱78 shipping
   - Order 3: ₱6000 items → ₱158 shipping
3. After each delivery, verify balance increases:
   - After Order 1: Balance = Start + ₱38
   - After Order 2: Balance = Start + ₱38 + ₱78
   - After Order 3: Balance = Start + ₱38 + ₱78 + ₱158 = Start + ₱274

### Scenario 4: Refresh Functionality
**Objective:** Test pull-to-refresh updates data correctly

1. **Rider Home Page:**
   - Note current balance and number of ready orders
   - Have another user place an order (or use web to create test order)
   - Pull down to refresh
   - Verify new order appears in "Ready for Pickup"

2. **After Accepting Order:**
   - Accept an order
   - Pull down to refresh
   - Verify order is removed from home page
   - Go to Deliveries tab
   - Pull down to refresh
   - Verify order appears in correct section

### Scenario 5: Multiple Orders Management
**Objective:** Test handling multiple orders in different stages

1. Create 6 test orders
2. Accept 2 orders → should appear in "Picking Up"
3. Mark 2 orders as picked up → should move to "Picked Up"
4. Mark 2 orders as delivered → should move to "Delivered"
5. Verify each tab shows correct orders
6. Verify balance increased by sum of all delivered orders' shipping fees

### Scenario 6: Web Checkout Shipping Fee
**Objective:** Verify web checkout also shows shipping fee correctly

1. Login to web as user
2. Add items to cart
3. Click checkout
4. Verify modal shows:
   - Subtotal (items only)
   - Shipping Fee (calculated)
   - Total (subtotal + shipping)
5. Place order
6. Verify order total in database includes shipping fee

## Common Issues to Check

### Issue 1: Shipping Fee Not Showing
**Check:**
- Order has `shipping_fee` field in Firestore
- Rider screen is reading `shipping_fee` from order data
- Calculation function is being called

### Issue 2: Balance Not Updating
**Check:**
- Rider user document has `balance` field
- `_updateStatus` method is adding shipping fee to balance
- Balance is being reloaded after delivery

### Issue 3: Orders Not Moving Between Tabs
**Check:**
- Status is being updated in Firestore
- Queries are filtering by correct status values
- Tab controller is refreshing after status change

### Issue 4: Refresh Not Working
**Check:**
- `RefreshIndicator` is wrapping the scrollable content
- `onRefresh` callback is async and returns Future
- Data is being reloaded and setState is called

## Test Data Setup

### Create Test Users:
1. **User:** username: `testuser1`, role: `user`, verified and approved
2. **Seller:** username: `testseller1`, role: `seller`, approved
3. **Rider:** username: `testrider1`, role: `rider`, verified and approved

### Create Test Products:
1. **Cheap Item:** ₱100 (to test base shipping fee)
2. **Medium Item:** ₱1500 (to test first bracket)
3. **Expensive Item:** ₱3000 (to test multiple brackets)

### Test Order Combinations:
- 5 × Cheap Item = ₱500 → ₱38 shipping
- 2 × Medium Item = ₱3000 → ₱78 shipping
- 2 × Expensive Item = ₱6000 → ₱158 shipping

## Expected Behavior Summary

### Rider Home Page:
- Shows current balance at top
- Shows "Ready for Pickup" orders (status: accepted)
- Pull-to-refresh updates both balance and orders
- Each order card shows shipping fee as "Your Earnings"

### Deliveries Page:
- **Picking Up Tab:** Orders rider has accepted, button: "Mark as Picked Up"
- **Picked Up Tab:** Orders rider has picked up, button: "Mark as Delivered"
- **Delivered Tab:** Completed orders, no buttons, shows "Earned: ₱XX"

### User Orders Page:
- Shows all orders with current status
- Status updates in real-time as rider progresses
- Final status: "delivered"

### Checkout (Flutter & Web):
- Shows subtotal (items only)
- Shows shipping fee (calculated)
- Shows total (subtotal + shipping)
- All three values are clearly labeled

## Performance Checks

1. **Load Time:** Deliveries page should load within 2 seconds
2. **Refresh Time:** Pull-to-refresh should complete within 1 second
3. **Status Update:** Status changes should reflect immediately
4. **Balance Update:** Balance should update within 1 second of marking delivered

## Edge Cases to Test

1. **Zero Balance:** New rider with no deliveries
2. **Large Balance:** Rider with many completed deliveries
3. **No Orders:** Empty "Ready for Pickup" section
4. **All Tabs Empty:** New rider with no accepted orders
5. **Rapid Status Changes:** Quickly marking orders as picked up and delivered
6. **Concurrent Orders:** Multiple riders accepting different orders simultaneously

## Success Criteria

✅ All shipping fees calculate correctly
✅ Orders move through all status stages
✅ Rider balance accumulates accurately
✅ Refresh updates all data
✅ UI shows correct information at each stage
✅ No errors in console/logs
✅ All status changes persist in Firestore
✅ User sees correct order status
