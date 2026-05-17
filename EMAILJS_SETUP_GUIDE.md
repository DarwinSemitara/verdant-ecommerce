# EmailJS Setup Guide for Forgot Password Feature

## Overview
This guide will help you integrate EmailJS into your Verdant e-commerce application to send password reset emails.

## Step 1: Create EmailJS Account

1. Go to [https://www.emailjs.com/](https://www.emailjs.com/)
2. Click "Sign Up" and create a free account
3. Verify your email address

## Step 2: Add Email Service

1. After logging in, go to the **Email Services** page
2. Click **"Add New Service"**
3. Choose your email provider (Gmail, Outlook, Yahoo, etc.)
4. For Gmail:
   - Service ID: Will be auto-generated (e.g., `service_abc123`)
   - Service Name: Give it a name like "Verdant Password Reset"
   - Click **"Connect Account"** and authorize with your Gmail
5. Click **"Create Service"**
6. **IMPORTANT**: Copy and save your **Service ID** (you'll need this later)

## Step 3: Create Email Template

1. Go to the **Email Templates** page
2. Click **"Create New Template"**
3. Configure the template:
   - Template Name: `Password Reset - Verdant`
   - Template ID: Will be auto-generated (e.g., `template_xyz789`)
   
4. **Email Template Content**:

   **Subject:**
   ```
   Password Reset Request - Verdant
   ```

   **Content (HTML):**
   ```html
   <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8f9fa; border-radius: 10px;">
     <div style="background-color: #2d5016; padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
       <h1 style="color: white; margin: 0;">Verdant</h1>
     </div>
     
     <div style="background-color: white; padding: 30px; border-radius: 0 0 10px 10px;">
       <h2 style="color: #2d5016; margin-top: 0;">Password Reset Request</h2>
       
       <p>Hello <strong>{{user_name}}</strong>,</p>
       
       <p>We received a request to reset your password for your Verdant account.</p>
       
       <p>Your temporary reset code is:</p>
       
       <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
         <h1 style="color: #2d5016; margin: 0; font-size: 32px; letter-spacing: 5px;">{{reset_code}}</h1>
       </div>
       
       <p><strong>This code will expire in 15 minutes.</strong></p>
       
       <p>If you didn't request this password reset, please ignore this email or contact support if you have concerns.</p>
       
       <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">
       
       <p style="color: #6c757d; font-size: 14px; margin: 0;">
         This is an automated message from Verdant. Please do not reply to this email.
       </p>
     </div>
   </div>
   ```

   **Template Parameters** (these will be filled by your code):
   - `{{user_name}}` - The user's name
   - `{{reset_code}}` - The 6-digit reset code
   - `{{to_email}}` - Recipient's email (auto-filled)

5. Click **"Save"**
6. **IMPORTANT**: Copy and save your **Template ID**

## Step 4: Get Your Public Key

1. Go to **Account** → **General**
2. Find your **Public Key** (looks like: `abc123XYZ456`)
3. **IMPORTANT**: Copy and save this key

## Step 5: Install EmailJS in Your Project

Add the EmailJS SDK to your HTML file. Add this script tag in the `<head>` section of your login page:

```html
<script type="text/javascript" src="https://cdn.jsdelivr.net/npm/@emailjs/browser@3/dist/email.min.js"></script>
<script type="text/javascript">
  (function(){
    emailjs.init("YOUR_PUBLIC_KEY_HERE"); // Replace with your actual public key
  })();
</script>
```

## Step 6: Update Your Configuration

You'll need these three values:
- **Public Key**: `YOUR_PUBLIC_KEY`
- **Service ID**: `service_abc123`
- **Template ID**: `template_xyz789`

## Step 7: Backend Implementation

Add this route to your `app.py`:

```python
import random
import string
from datetime import datetime, timedelta

# Store reset codes temporarily (in production, use Redis or database)
password_reset_codes = {}

@app.route('/api/request_password_reset', methods=['POST'])
def request_password_reset():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email:
        return jsonify({'success': False, 'message': 'Email is required'}), 400
    
    try:
        from firestore_db import users_ref
        
        # Find user by email
        users_query = users_ref.where('email', '==', email).limit(1).stream()
        user = None
        for doc in users_query:
            user = doc.to_dict()
            user['id'] = doc.id
            break
        
        if not user:
            # Don't reveal if email exists or not (security)
            return jsonify({
                'success': True, 
                'message': 'If this email exists, a reset code has been sent'
            })
        
        # Generate 6-digit code
        reset_code = ''.join(random.choices(string.digits, k=6))
        
        # Store code with expiration (15 minutes)
        password_reset_codes[email] = {
            'code': reset_code,
            'expires': datetime.now() + timedelta(minutes=15),
            'user_id': user['id']
        }
        
        # Return code and user info for EmailJS to send
        return jsonify({
            'success': True,
            'message': 'Reset code generated',
            'reset_code': reset_code,
            'user_name': user.get('full_name', user.get('username', 'User')),
            'email': email
        })
        
    except Exception as e:
        print(f"Error requesting password reset: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Error processing request'}), 500


@app.route('/api/verify_reset_code', methods=['POST'])
def verify_reset_code():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    code = data.get('code', '').strip()
    
    if not email or not code:
        return jsonify({'success': False, 'message': 'Email and code are required'}), 400
    
    # Check if code exists and is valid
    if email not in password_reset_codes:
        return jsonify({'success': False, 'message': 'Invalid or expired code'}), 400
    
    stored_data = password_reset_codes[email]
    
    # Check expiration
    if datetime.now() > stored_data['expires']:
        del password_reset_codes[email]
        return jsonify({'success': False, 'message': 'Code has expired'}), 400
    
    # Check code match
    if stored_data['code'] != code:
        return jsonify({'success': False, 'message': 'Invalid code'}), 400
    
    # Code is valid
    return jsonify({
        'success': True,
        'message': 'Code verified',
        'user_id': stored_data['user_id']
    })


@app.route('/api/reset_password_with_code', methods=['POST'])
def reset_password_with_code():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    code = data.get('code', '').strip()
    new_password = data.get('new_password', '')
    
    if not email or not code or not new_password:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400
    
    if len(new_password) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
    
    # Verify code first
    if email not in password_reset_codes:
        return jsonify({'success': False, 'message': 'Invalid or expired code'}), 400
    
    stored_data = password_reset_codes[email]
    
    if datetime.now() > stored_data['expires']:
        del password_reset_codes[email]
        return jsonify({'success': False, 'message': 'Code has expired'}), 400
    
    if stored_data['code'] != code:
        return jsonify({'success': False, 'message': 'Invalid code'}), 400
    
    try:
        from firestore_db import users_ref
        
        # Update password
        hashed_password = generate_password_hash(new_password)
        users_ref.document(stored_data['user_id']).update({
            'password': hashed_password,
            'updated_at': datetime.now()
        })
        
        # Remove used code
        del password_reset_codes[email]
        
        return jsonify({'success': True, 'message': 'Password reset successfully'})
        
    except Exception as e:
        print(f"Error resetting password: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Error resetting password'}), 500
```

## Step 8: Frontend Implementation

Add this JavaScript to your login page (where the "Forgot Password" link is):

```javascript
// Initialize EmailJS with your public key
emailjs.init("YOUR_PUBLIC_KEY_HERE");

function showForgotPasswordModal() {
  // Create modal HTML
  const modalHTML = `
    <div id="forgotPasswordModal" style="display: flex; position: fixed; z-index: 9999; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); align-items: center; justify-content: center;">
      <div style="background-color: white; padding: 2rem; border-radius: 12px; max-width: 500px; width: 90%;">
        <h2 style="margin-top: 0; color: #2d5016;">Reset Password</h2>
        
        <div id="emailStep">
          <p>Enter your email address and we'll send you a reset code.</p>
          <input type="email" id="resetEmail" placeholder="Enter your email" style="width: 100%; padding: 0.75rem; border: 1px solid #dee2e6; border-radius: 8px; margin-bottom: 1rem;">
          <button onclick="sendResetCode()" style="width: 100%; padding: 0.75rem; background: #2d5016; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 1rem;">Send Reset Code</button>
        </div>
        
        <div id="codeStep" style="display: none;">
          <p>Enter the 6-digit code sent to your email.</p>
          <input type="text" id="resetCode" placeholder="Enter 6-digit code" maxlength="6" style="width: 100%; padding: 0.75rem; border: 1px solid #dee2e6; border-radius: 8px; margin-bottom: 1rem; text-align: center; font-size: 1.5rem; letter-spacing: 5px;">
          <input type="password" id="newPassword" placeholder="New password (min 8 characters)" style="width: 100%; padding: 0.75rem; border: 1px solid #dee2e6; border-radius: 8px; margin-bottom: 1rem;">
          <input type="password" id="confirmNewPassword" placeholder="Confirm new password" style="width: 100%; padding: 0.75rem; border: 1px solid #dee2e6; border-radius: 8px; margin-bottom: 1rem;">
          <button onclick="resetPassword()" style="width: 100%; padding: 0.75rem; background: #2d5016; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 1rem;">Reset Password</button>
        </div>
        
        <button onclick="closeForgotPasswordModal()" style="width: 100%; padding: 0.75rem; background: #6c757d; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 1rem; margin-top: 1rem;">Cancel</button>
        
        <div id="resetMessage" style="margin-top: 1rem; padding: 0.75rem; border-radius: 8px; display: none;"></div>
      </div>
    </div>
  `;
  
  document.body.insertAdjacentHTML('beforeend', modalHTML);
}

function closeForgotPasswordModal() {
  const modal = document.getElementById('forgotPasswordModal');
  if (modal) modal.remove();
}

let currentResetEmail = '';

function sendResetCode() {
  const email = document.getElementById('resetEmail').value.trim();
  
  if (!email) {
    showResetMessage('Please enter your email', 'error');
    return;
  }
  
  currentResetEmail = email;
  
  // Request reset code from backend
  fetch('/api/request_password_reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      // Send email using EmailJS
      emailjs.send(
        "YOUR_SERVICE_ID",  // Replace with your Service ID
        "YOUR_TEMPLATE_ID", // Replace with your Template ID
        {
          to_email: email,
          user_name: data.user_name,
          reset_code: data.reset_code
        }
      )
      .then(() => {
        showResetMessage('Reset code sent! Check your email.', 'success');
        document.getElementById('emailStep').style.display = 'none';
        document.getElementById('codeStep').style.display = 'block';
      })
      .catch(error => {
        console.error('EmailJS error:', error);
        showResetMessage('Failed to send email. Please try again.', 'error');
      });
    } else {
      showResetMessage(data.message, 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showResetMessage('An error occurred. Please try again.', 'error');
  });
}

function resetPassword() {
  const code = document.getElementById('resetCode').value.trim();
  const newPassword = document.getElementById('newPassword').value;
  const confirmPassword = document.getElementById('confirmNewPassword').value;
  
  if (!code || !newPassword || !confirmPassword) {
    showResetMessage('Please fill in all fields', 'error');
    return;
  }
  
  if (newPassword.length < 8) {
    showResetMessage('Password must be at least 8 characters', 'error');
    return;
  }
  
  if (newPassword !== confirmPassword) {
    showResetMessage('Passwords do not match', 'error');
    return;
  }
  
  fetch('/api/reset_password_with_code', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: currentResetEmail,
      code: code,
      new_password: newPassword
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showResetMessage('Password reset successfully! You can now log in.', 'success');
      setTimeout(() => {
        closeForgotPasswordModal();
      }, 2000);
    } else {
      showResetMessage(data.message, 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showResetMessage('An error occurred. Please try again.', 'error');
  });
}

function showResetMessage(message, type) {
  const messageDiv = document.getElementById('resetMessage');
  messageDiv.textContent = message;
  messageDiv.style.display = 'block';
  messageDiv.style.backgroundColor = type === 'success' ? '#d4edda' : '#f8d7da';
  messageDiv.style.color = type === 'success' ? '#155724' : '#721c24';
  messageDiv.style.border = `1px solid ${type === 'success' ? '#c3e6cb' : '#f5c6cb'}`;
}

// Add click handler to "Forgot Password" link
document.querySelector('.forgot-password-link').addEventListener('click', function(e) {
  e.preventDefault();
  showForgotPasswordModal();
});
```

## Step 9: Replace Placeholders

In your code, replace these placeholders with your actual values:

1. **Public Key**: Replace `YOUR_PUBLIC_KEY_HERE` with your EmailJS public key
2. **Service ID**: Replace `YOUR_SERVICE_ID` with your service ID
3. **Template ID**: Replace `YOUR_TEMPLATE_ID` with your template ID

## Step 10: Testing

1. Click "Forgot Password" on your login page
2. Enter a valid email address
3. Check your email for the 6-digit code
4. Enter the code and new password
5. Try logging in with the new password

## Important Notes

- **Free Tier Limits**: EmailJS free tier allows 200 emails/month
- **Security**: Never expose your private key (only use public key in frontend)
- **Production**: Consider using a database or Redis to store reset codes instead of in-memory storage
- **Expiration**: Reset codes expire after 15 minutes for security
- **Rate Limiting**: Consider adding rate limiting to prevent abuse

## Troubleshooting

**Email not received?**
- Check spam/junk folder
- Verify email service is connected in EmailJS dashboard
- Check EmailJS dashboard for failed sends
- Verify template parameters match exactly

**"Invalid code" error?**
- Code may have expired (15 minutes)
- Check for typos in the code
- Request a new code

**EmailJS errors?**
- Verify all IDs are correct (Public Key, Service ID, Template ID)
- Check browser console for detailed error messages
- Ensure EmailJS script is loaded before your code runs

## Support

- EmailJS Documentation: https://www.emailjs.com/docs/
- EmailJS Dashboard: https://dashboard.emailjs.com/

---

**Your EmailJS Credentials** (fill these in):
- Public Key: `_____________________`
- Service ID: `_____________________`
- Template ID: `_____________________`
