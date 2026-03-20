"""
M-Pesa Daraja API Integration
──────────────────────────────
Flow:
  1. POST /api/payment/mpesa/stk      → get access token → call STK Push → return checkout_request_id
  2. Safaricom calls POST /api/payment/mpesa/callback → verify → update order + payment
  3. GET  /api/payment/mpesa/query/<checkout_request_id> → poll status from client

PayPal & Card handled server-side for order creation only; capture is client-side (PayPal JS SDK).
"""

import base64
import json
import string
import random
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, session
from flask_login import current_user, login_required
from models import db, Order, OrderItem, Payment, Product, Address, OrderStatusLog

payment_bp = Blueprint('payment', __name__, url_prefix='/api/payment')


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def gen_order_id():
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=7))
    return f'VLT-{suffix}'

def normalize_phone(raw: str) -> str:
    """Convert 07xx/01xx/+2547xx to 2547xx format."""
    phone = raw.strip().replace(' ', '').replace('-', '')
    if phone.startswith('+'):
        phone = phone[1:]
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    if not phone.startswith('254'):
        phone = '254' + phone
    return phone

def build_order_from_cart(user, cart_items, address_id, payment_method, currency='USD'):
    """Create Order + OrderItems from the cart data sent by JS."""
    address = Address.query.filter_by(id=address_id, user_id=user.id).first()
    subtotal = 0.0
    items_to_create = []
    for ci in cart_items:
        product = Product.query.get(ci['id'])
        if not product or not product.is_active:
            return None, f"Product '{ci.get('name',ci['id'])}' is unavailable."
        if product.stock < ci['qty']:
            return None, f"Insufficient stock for '{product.name}'."
        line = float(product.price_usd) * ci['qty']
        subtotal += line
        items_to_create.append((product, ci['qty'], float(product.price_usd)))

    delivery = 4.00
    total    = subtotal + delivery
    order_id = gen_order_id()

    order = Order(
        id             = order_id,
        user_id        = user.id,
        address_id     = address.id if address else None,
        status         = 'pending_payment',
        subtotal_usd   = subtotal,
        delivery_usd   = delivery,
        total_usd      = total,
        currency       = currency,
        payment_method = payment_method,
    )
    db.session.add(order)
    db.session.flush()

    for product, qty, unit_price in items_to_create:
        oi = OrderItem(order_id=order.id, product_id=product.id, quantity=qty, unit_price_usd=unit_price)
        db.session.add(oi)
        product.stock = max(0, product.stock - qty)

    return order, None


# ─────────────────────────────────────────────
#  DARAJA ACCESS TOKEN
# ─────────────────────────────────────────────
def get_mpesa_access_token():
    key    = current_app.config['MPESA_CONSUMER_KEY']
    secret = current_app.config['MPESA_CONSUMER_SECRET']
    base   = current_app.config['MPESA_BASE_URL']
    if not key or not secret:
        raise ValueError('M-Pesa credentials not configured in .env')
    credentials = base64.b64encode(f'{key}:{secret}'.encode()).decode()
    resp = requests.get(
        f'{base}/oauth/v1/generate?grant_type=client_credentials',
        headers={'Authorization': f'Basic {credentials}'},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()['access_token']


# ─────────────────────────────────────────────
#  STK PUSH
# ─────────────────────────────────────────────
@payment_bp.route('/mpesa/stk', methods=['POST'])
@login_required
def mpesa_stk():
    data = request.get_json(force=True)
    phone_raw   = data.get('phone', '')
    cart_items  = data.get('cart', [])
    address_id  = data.get('address_id')
    currency    = data.get('currency', 'USD')

    if not phone_raw or not cart_items:
        return jsonify({'error': 'Phone number and cart are required.'}), 400

    # Build order first (in DB, status=pending_payment)
    order, err = build_order_from_cart(current_user, cart_items, address_id, 'mpesa', currency)
    if err:
        return jsonify({'error': err}), 400

    phone   = normalize_phone(phone_raw)
    amount  = max(1, int(round(float(order.total_usd) * 129.5)))  # USD→KES approx

    shortcode = current_app.config['MPESA_SHORTCODE']
    passkey   = current_app.config['MPESA_PASSKEY']
    callback  = current_app.config['MPESA_CALLBACK_URL']
    base      = current_app.config['MPESA_BASE_URL']

    ts        = datetime.now().strftime('%Y%m%d%H%M%S')
    password  = base64.b64encode(f'{shortcode}{passkey}{ts}'.encode()).decode()

    try:
        token = get_mpesa_access_token()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Could not authenticate with Safaricom: {str(e)}'}), 502

    payload = {
        'BusinessShortCode': shortcode,
        'Password':          password,
        'Timestamp':         ts,
        'TransactionType':   'CustomerPayBillOnline',
        'Amount':            amount,
        'PartyA':            phone,
        'PartyB':            shortcode,
        'PhoneNumber':       phone,
        'CallBackURL':       callback,
        'AccountReference':  order.id,
        'TransactionDesc':   f'VOLTR Order {order.id}',
    }

    try:
        resp = requests.post(
            f'{base}/mpesa/stkpush/v1/processrequest',
            json=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type':  'application/json',
            },
            timeout=20
        )
        resp.raise_for_status()
        result = resp.json()
    except requests.exceptions.RequestException as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to reach Safaricom: {str(e)}'}), 502

    if result.get('ResponseCode') != '0':
        db.session.rollback()
        return jsonify({'error': result.get('ResponseDescription', 'STK push failed')}), 400

    # Save payment record
    payment = Payment(
        order_id            = order.id,
        method              = 'mpesa',
        status              = 'pending',
        amount_usd          = order.total_usd,
        checkout_request_id = result['CheckoutRequestID'],
        merchant_request_id = result['MerchantRequestID'],
        mpesa_phone         = phone,
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({
        'success':              True,
        'order_id':             order.id,
        'checkout_request_id':  result['CheckoutRequestID'],
        'merchant_request_id':  result['MerchantRequestID'],
        'amount_kes':           amount,
        'message':              result.get('CustomerMessage', 'STK push sent. Enter your M-Pesa PIN.'),
    })


# ─────────────────────────────────────────────
#  DARAJA CALLBACK (called by Safaricom servers)
# ─────────────────────────────────────────────
@payment_bp.route('/mpesa/callback', methods=['POST'])
def mpesa_callback():
    try:
        body   = request.get_json(force=True)
        result = body['Body']['stkCallback']
        checkout_request_id = result['CheckoutRequestID']
        result_code         = result['ResultCode']
        result_desc         = result['ResultDesc']

        payment = Payment.query.filter_by(checkout_request_id=checkout_request_id).first()
        if not payment:
            return jsonify({'ResultCode': 0, 'ResultDesc': 'Accepted'})

        order = payment.order
        if result_code == 0:
            # Success — extract receipt
            meta_items = result.get('CallbackMetadata', {}).get('Item', [])
            meta = {item['Name']: item.get('Value') for item in meta_items}
            payment.status        = 'completed'
            payment.mpesa_receipt = str(meta.get('MpesaReceiptNumber', ''))
            order.status          = 'confirmed'
            log = OrderStatusLog(order_id=order.id, status='confirmed',
                                 note=f"M-Pesa payment confirmed. Receipt: {payment.mpesa_receipt}")
            db.session.add(log)
        else:
            payment.status = 'failed'
            log = OrderStatusLog(order_id=order.id, status='pending_payment',
                                 note=f"M-Pesa failed: {result_desc}")
            db.session.add(log)

        db.session.commit()
    except Exception as e:
        current_app.logger.error(f'M-Pesa callback error: {e}')

    # Safaricom expects this exact response
    return jsonify({'ResultCode': 0, 'ResultDesc': 'Accepted'})


# ─────────────────────────────────────────────
#  POLL STATUS (client polls every 3s after STK push)
# ─────────────────────────────────────────────
@payment_bp.route('/mpesa/query/<checkout_request_id>', methods=['GET'])
@login_required
def mpesa_query(checkout_request_id):
    payment = Payment.query.filter_by(checkout_request_id=checkout_request_id).first()
    if not payment:
        return jsonify({'error': 'Payment record not found.'}), 404

    # If the callback already updated us, return that
    if payment.status in ('completed', 'failed'):
        return jsonify({
            'status':         payment.status,
            'order_id':       payment.order_id,
            'mpesa_receipt':  payment.mpesa_receipt,
        })

    # Otherwise, actively query Daraja
    shortcode = current_app.config['MPESA_SHORTCODE']
    passkey   = current_app.config['MPESA_PASSKEY']
    base      = current_app.config['MPESA_BASE_URL']
    ts        = datetime.now().strftime('%Y%m%d%H%M%S')
    password  = base64.b64encode(f'{shortcode}{passkey}{ts}'.encode()).decode()

    try:
        token = get_mpesa_access_token()
        resp  = requests.post(
            f'{base}/mpesa/stkpushquery/v1/query',
            json={
                'BusinessShortCode': shortcode,
                'Password':          password,
                'Timestamp':         ts,
                'CheckoutRequestID': checkout_request_id,
            },
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=15
        )
        resp.raise_for_status()
        result = resp.json()
        rc = result.get('ResultCode')
        if rc == '0' or rc == 0:
            payment.status = 'completed'
            payment.order.status = 'confirmed'
            db.session.commit()
            return jsonify({'status': 'completed', 'order_id': payment.order_id})
        elif rc is not None and str(rc) != '1032':
            payment.status = 'failed'
            db.session.commit()
            return jsonify({'status': 'failed', 'message': result.get('ResultDesc', '')})
    except Exception as e:
        current_app.logger.warning(f'Daraja query error: {e}')

    return jsonify({'status': 'pending'})


# ─────────────────────────────────────────────
#  PAYPAL — create order server-side
# ─────────────────────────────────────────────
@payment_bp.route('/paypal/create', methods=['POST'])
@login_required
def paypal_create():
    data       = request.get_json(force=True)
    cart_items = data.get('cart', [])
    address_id = data.get('address_id')
    currency   = data.get('currency', 'USD')

    order, err = build_order_from_cart(current_user, cart_items, address_id, 'paypal', currency)
    if err:
        return jsonify({'error': err}), 400
    db.session.commit()
    return jsonify({'order_id': order.id, 'amount': str(order.total_usd)})


@payment_bp.route('/paypal/capture', methods=['POST'])
@login_required
def paypal_capture():
    data           = request.get_json(force=True)
    db_order_id    = data.get('db_order_id')
    paypal_details = data.get('details', {})
    order          = Order.query.filter_by(id=db_order_id, user_id=current_user.id).first_or_404()
    payment = Payment(
        order_id        = order.id,
        method          = 'paypal',
        status          = 'completed',
        amount_usd      = order.total_usd,
        paypal_order_id = paypal_details.get('id', ''),
    )
    db.session.add(payment)
    order.status = 'confirmed'
    log = OrderStatusLog(order_id=order.id, status='confirmed',
                         note=f"PayPal payment confirmed. TxID: {paypal_details.get('id','')}")
    db.session.add(log)
    db.session.commit()
    return jsonify({'success': True, 'order_id': order.id})


# ─────────────────────────────────────────────
#  CARD — demo only (integrate Stripe / Flutterwave in production)
# ─────────────────────────────────────────────
@payment_bp.route('/card/charge', methods=['POST'])
@login_required
def card_charge():
    data       = request.get_json(force=True)
    cart_items = data.get('cart', [])
    address_id = data.get('address_id')
    currency   = data.get('currency', 'USD')
    last4      = data.get('last4', '0000')

    order, err = build_order_from_cart(current_user, cart_items, address_id, 'card', currency)
    if err:
        return jsonify({'error': err}), 400

    payment = Payment(
        order_id   = order.id,
        method     = 'card',
        status     = 'completed',
        amount_usd = order.total_usd,
        card_last4 = str(last4)[-4:],
    )
    db.session.add(payment)
    order.status = 'confirmed'
    log = OrderStatusLog(order_id=order.id, status='confirmed', note='Card payment authorised.')
    db.session.add(log)
    db.session.commit()
    return jsonify({'success': True, 'order_id': order.id})
