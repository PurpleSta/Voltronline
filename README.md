# VOLTR Shop — Full-Stack E-Commerce

Flask + MySQL + Safaricom Daraja M-Pesa + PayPal + Live ECB Exchange Rates

---

## Project Structure

```
voltr/
├── app.py                  # Flask app factory, CLI seed command
├── config.py               # Configuration (loads from .env)
├── models.py               # SQLAlchemy models
├── requirements.txt
├── .env.example            # Copy to .env and fill in your credentials
├── routes/
│   ├── auth.py             # Login, register, profile
│   ├── vendor.py           # Vendor dashboard, products, orders
│   ├── shop.py             # Storefront, cart, checkout pages
│   └── payment.py          # Daraja STK push, callback, PayPal, card
├── templates/
│   ├── base.html
│   ├── auth/               # login, register, profile
│   ├── shop/               # index, products, product_detail, checkout, track, orders, addresses
│   ├── vendor/             # dashboard, products, add_product, orders, settings
│   └── errors/             # 404, 500
└── static/
    ├── css/style.css
    ├── img/placeholder.svg
    └── uploads/            # Created automatically for vendor product images
```

---

## 1. Prerequisites

- Python 3.10+
- MySQL 8.0+ (or MariaDB 10.6+)
- ngrok (for M-Pesa callback during local dev)
- Safaricom Daraja account: https://developer.safaricom.co.ke
- PayPal developer account (optional): https://developer.paypal.com

---

## 2. MySQL Setup

```sql
CREATE DATABASE voltr_shop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'voltr'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON voltr_shop.* TO 'voltr'@'localhost';
FLUSH PRIVILEGES;
```

---

## 3. Install & Configure

```bash
cd voltr

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — fill in MYSQL credentials and Daraja keys
```

---

## 4. Database Migration & Seed

```bash
flask db init          # Only first time
flask db migrate -m "initial"
flask db upgrade

# Seed categories, demo vendor, customer and 12 sample products
flask seed
```

---

## 5. M-Pesa Daraja Setup (REQUIRED for real STK push)

### Get credentials
1. Register at https://developer.safaricom.co.ke
2. Create an App → note **Consumer Key** and **Consumer Secret**
3. Go to **Lipa Na M-Pesa Online** → note the **Passkey** (sandbox: already shown)
4. Sandbox shortcode: `174379`

### Set up ngrok callback (local dev only)
```bash
# In a separate terminal:
ngrok http 5000
# Copy the HTTPS URL, e.g. https://abc123.ngrok.io
```

Update `.env`:
```
MPESA_CONSUMER_KEY=your_key
MPESA_CONSUMER_SECRET=your_secret
MPESA_SHORTCODE=174379
MPESA_PASSKEY=bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919
MPESA_CALLBACK_URL=https://abc123.ngrok.io/api/payment/mpesa/callback
MPESA_ENV=sandbox
```

### Production
- Change `MPESA_ENV=production`
- Use your real shortcode and passkey
- Set `MPESA_CALLBACK_URL` to your live HTTPS domain

---

## 6. PayPal Setup (optional)

### Sandbox (default — works out of the box)
The SDK loads with `client-id=sb` for sandbox testing.

### Production
1. Create an app at https://developer.paypal.com/dashboard
2. Copy Client ID
3. In `.env`: `PAYPAL_CLIENT_ID=your_live_client_id`
4. In `templates/shop/checkout.html` the SDK script tag reads the client_id from config

---

## 7. Run

```bash
flask run
# or
python app.py
```

Visit: http://localhost:5000

---

## 8. Demo Accounts (after `flask seed`)

| Role     | Email                  | Password      |
|----------|------------------------|---------------|
| Customer | jane@example.com       | customer123!  |
| Vendor   | vendor@voltr.shop      | vendor123!    |
| Admin    | admin@voltr.shop       | admin123!     |

---

## 9. Key Features

### Customer
- Browse products with live ECB currency conversion (7 currencies)
- Filter by category, badge, sort by price/newest
- Add to cart (localStorage), proceed to checkout
- Save and manage multiple delivery addresses
- Pay via:
  - **M-Pesa** — real Daraja STK push sent to phone; frontend polls `/api/payment/mpesa/query/<id>` every 3s; only confirms when Safaricom callback fires
  - **PayPal** — PayPal JS SDK; order created server-side, capture confirmed server-side
  - **Card** — demo flow (wire Stripe or Flutterwave for production)
- Full Jumia-style order tracking with timeline steps

### Vendor
- Register as vendor with store name and description
- Add/edit/delete products with image upload or URL, price, stock, badge, category
- Toggle products active/inactive
- View orders containing their products
- Update order status (confirmed → processing → packed → shipped → out for delivery → delivered)
- Status updates appear in the customer's tracking timeline with notes

### Technical
- All prices stored in USD; converted client-side and server-side using live rates
- M-Pesa amount: USD × live KES rate, rounded to integer
- Upload directory auto-created at `static/uploads/`
- Rate cache: 1-hour TTL, fallback to static rates if API unavailable

---

## 10. Production Checklist

- [ ] Set `SECRET_KEY` to a long random string
- [ ] Set `FLASK_ENV=production`
- [ ] Switch from SQLite to MySQL (already configured)
- [ ] Configure real Daraja credentials with live shortcode
- [ ] Add real PayPal live client ID
- [ ] Set `MPESA_CALLBACK_URL` to your HTTPS domain
- [ ] Integrate Stripe or Flutterwave for card payments
- [ ] Run behind gunicorn + nginx
- [ ] Enable SSL (required by Safaricom for callback URL)
- [ ] Set `UPLOAD_FOLDER` to a persistent path outside the repo

```bash
# Production run
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```
