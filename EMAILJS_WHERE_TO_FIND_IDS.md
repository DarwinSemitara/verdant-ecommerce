# Where to Find Your EmailJS IDs

## 🔑 1. Public Key

**Location:** Account → General

```
1. Log in to https://dashboard.emailjs.com/
2. Click "Account" in the left sidebar
3. Click "General" tab
4. Look for "Public Key" section
5. Copy the key (looks like: abc123XYZ456)
```

**What it looks like:**
```
┌─────────────────────────────────────┐
│ Public Key                          │
│ ┌─────────────────────────────────┐ │
│ │ abc123XYZ456                    │ │
│ └─────────────────────────────────┘ │
│ [Copy]                              │
└─────────────────────────────────────┘
```

---

## 📧 2. Service ID

**Location:** Email Services

```
1. Click "Email Services" in the left sidebar
2. You'll see your connected service (e.g., "Verdant Password Reset")
3. The Service ID is shown under the service name
4. Copy it (looks like: service_abc123)
```

**What it looks like:**
```
┌─────────────────────────────────────────────┐
│ Email Services                              │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │ 📧 Verdant Password Reset               │ │
│ │ Gmail                                   │ │
│ │ Service ID: service_abc123              │ │
│ │ Status: ✅ Connected                    │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

---

## 📝 3. Template ID

**Location:** Email Templates

```
1. Click "Email Templates" in the left sidebar
2. You'll see your template (e.g., "Verdant Password Reset")
3. The Template ID is shown under the template name
4. Copy it (looks like: template_xyz789)
```

**What it looks like:**
```
┌─────────────────────────────────────────────┐
│ Email Templates                             │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │ 📄 Verdant Password Reset               │ │
│ │ Template ID: template_xyz789            │ │
│ │ Last modified: Today                    │ │
│ │ [Edit] [Preview] [Test]                 │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

---

## 📋 Quick Copy Template

Once you have all three, fill this in:

```javascript
// In login.html <head> section (~line 17)
emailjs.init("YOUR_PUBLIC_KEY");
             ↓
emailjs.init("abc123XYZ456");  // Your actual Public Key


// In forgot password script (~line 735)
emailjs.send(
  "YOUR_SERVICE_ID",
  "YOUR_TEMPLATE_ID",
  { ... }
)
             ↓
emailjs.send(
  "service_abc123",      // Your actual Service ID
  "template_xyz789",     // Your actual Template ID
  { ... }
)
```

---

## ✅ Verification Checklist

Before testing, verify:

- [ ] Public Key is in `emailjs.init("...")`
- [ ] Service ID is in first parameter of `emailjs.send(...)`
- [ ] Template ID is in second parameter of `emailjs.send(...)`
- [ ] All IDs are in quotes (strings)
- [ ] No typos or extra spaces
- [ ] Saved the file

---

## 🧪 Test Your Setup

1. Open browser console (F12)
2. Go to login page
3. Click "Forgot password?"
4. Enter username
5. Click "Send verification code"
6. Watch console for:
   - ✅ "Sending email..." message
   - ✅ No red errors
   - ✅ Email received in inbox

If you see errors in console, they'll tell you exactly what's wrong!

---

## 🎯 Common Mistakes

❌ **Wrong:** `emailjs.init(abc123XYZ456)` - Missing quotes
✅ **Right:** `emailjs.init("abc123XYZ456")` - Has quotes

❌ **Wrong:** `emailjs.send("service_abc123", template_xyz789, ...)` - Missing quotes on template
✅ **Right:** `emailjs.send("service_abc123", "template_xyz789", ...)` - Both have quotes

❌ **Wrong:** Copying "Service ID: service_abc123" (including the label)
✅ **Right:** Copying just "service_abc123" (only the ID)

---

## 📸 Visual Guide

### Finding Public Key:
```
Dashboard → Account (left sidebar) → General (tab) → Public Key (section)
```

### Finding Service ID:
```
Dashboard → Email Services (left sidebar) → Your Service → Service ID (under name)
```

### Finding Template ID:
```
Dashboard → Email Templates (left sidebar) → Your Template → Template ID (under name)
```

---

That's it! Once you have all three IDs and update the code, you're done! 🎉
