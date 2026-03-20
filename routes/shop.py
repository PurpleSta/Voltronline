import requests as http_requests
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session, abort
from flask_login import login_required, current_user
from models import db, Product, Category, Order, OrderItem, Address, Payment, OrderStatusLog

shop_bp = Blueprint('shop', __name__)

# Simple in-memory rate cache
_rate_cache = {}

def get_rates():
    import time
    now = time.time()
    if _rate_cache.get('ts', 0) + 3600 > now and _rate_cache.get('rates'):
        return _rate_cache['rates']
    try:
        resp = http_requests.get('https://api.frankfurter.app/latest?from=USD', timeout=5)
        rates = resp.json().get('rates', {})
        rates['USD'] = 1.0
        rates['KES'] = rates.get('KES', 129.5)
        _rate_cache['rates'] = rates
        _rate_cache['ts']    = now
        return rates
    except Exception:
        return {'USD':1,'EUR':0.92,'GBP':0.79,'KES':129.5,'JPY':149.2,'AUD':1.53,'CAD':1.36}

CURRENCY_SYMBOLS = {'USD':'$','EUR':'€','GBP':'£','KES':'KSh ','JPY':'¥','AUD':'A$','CAD':'C$'}


@shop_bp.route('/')
def index():
    currency  = request.args.get('currency', session.get('currency', 'USD'))
    session['currency'] = currency
    rates     = get_rates()
    rate      = rates.get(currency, 1.0)
    featured  = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).limit(8).all()
    categories= Category.query.all()
    return render_template('shop/index.html',
        products=featured, categories=categories,
        currency=currency, rate=rate,
        symbol=CURRENCY_SYMBOLS.get(currency,'$'), rates=rates)


@shop_bp.route('/shop')
def products():
    currency  = request.args.get('currency', session.get('currency', 'USD'))
    session['currency'] = currency
    rates     = get_rates()
    rate      = rates.get(currency, 1.0)
    q         = request.args.get('q', '').strip()
    cat_slug  = request.args.get('cat', '')
    badge     = request.args.get('badge', '')
    sort      = request.args.get('sort', 'newest')

    query = Product.query.filter_by(is_active=True)
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%') | Product.description.ilike(f'%{q}%'))
    if cat_slug:
        cat = Category.query.filter_by(slug=cat_slug).first()
        if cat:
            query = query.filter_by(category_id=cat.id)
    if badge:
        query = query.filter_by(badge=badge)
    if sort == 'price_asc':
        query = query.order_by(Product.price_usd.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price_usd.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    prods      = query.all()
    categories = Category.query.all()
    return render_template('shop/products.html',
        products=prods, categories=categories, q=q, cat_slug=cat_slug, badge=badge, sort=sort,
        currency=currency, rate=rate, symbol=CURRENCY_SYMBOLS.get(currency,'$'), rates=rates)


@shop_bp.route('/product/<int:pid>')
def product_detail(pid):
    currency = request.args.get('currency', session.get('currency', 'USD'))
    session['currency'] = currency
    rates    = get_rates()
    rate     = rates.get(currency, 1.0)
    product  = Product.query.filter_by(id=pid, is_active=True).first_or_404()
    related  = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != pid,
        Product.is_active == True
    ).limit(4).all()
    return render_template('shop/product_detail.html', product=product, related=related,
        currency=currency, rate=rate, symbol=CURRENCY_SYMBOLS.get(currency,'$'), rates=rates)


@shop_bp.route('/checkout')
@login_required
def checkout():
    currency = session.get('currency', 'USD')
    rates    = get_rates()
    rate     = rates.get(currency, 1.0)
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    from flask import current_app
    paypal_client_id = current_app.config['PAYPAL_CLIENT_ID']
    return render_template('shop/checkout.html',
        addresses=addresses, currency=currency, rate=rate,
        symbol=CURRENCY_SYMBOLS.get(currency,'$'), rates=rates,
        paypal_client_id=paypal_client_id)


@shop_bp.route('/orders')
@login_required
def my_orders():
    currency = session.get('currency', 'USD')
    orders   = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('shop/orders.html', orders=orders, currency=currency,
        symbol=CURRENCY_SYMBOLS.get(currency,'$'), rates=get_rates())


@shop_bp.route('/orders/<oid>')
@login_required
def track_order(oid):
    currency = session.get('currency', 'USD')
    rates    = get_rates()
    rate     = rates.get(currency, 1.0)
    order    = Order.query.filter_by(id=oid, user_id=current_user.id).first_or_404()
    return render_template('shop/track.html', order=order,
        currency=currency, rate=rate, symbol=CURRENCY_SYMBOLS.get(currency,'$'))


# ── Address management ──────────────────────
@shop_bp.route('/addresses', methods=['GET'])
@login_required
def addresses():
    addrs = Address.query.filter_by(user_id=current_user.id).all()
    return render_template('shop/addresses.html', addresses=addrs)

@shop_bp.route('/addresses/add', methods=['POST'])
@login_required
def add_address():
    a = Address(
        user_id   = current_user.id,
        full_name = request.form.get('full_name','').strip(),
        phone     = request.form.get('phone','').strip(),
        line1     = request.form.get('line1','').strip(),
        city      = request.form.get('city','').strip(),
        postcode  = request.form.get('postcode','').strip(),
        country   = request.form.get('country','Kenya'),
        is_default= bool(request.form.get('is_default')),
    )
    if not all([a.full_name, a.line1, a.city]):
        flash('Name, address and city are required.', 'error')
        return redirect(request.referrer or url_for('shop.checkout'))
    if a.is_default:
        Address.query.filter_by(user_id=current_user.id).update({'is_default': False})
    db.session.add(a)
    db.session.commit()
    flash('Address saved.', 'success')
    return redirect(request.referrer or url_for('shop.checkout'))

@shop_bp.route('/addresses/<int:aid>/delete', methods=['POST'])
@login_required
def delete_address(aid):
    a = Address.query.filter_by(id=aid, user_id=current_user.id).first_or_404()
    db.session.delete(a)
    db.session.commit()
    flash('Address removed.', 'info')
    return redirect(request.referrer or url_for('shop.addresses'))


# ── Currency API endpoint ────────────────────
@shop_bp.route('/api/rates')
def api_rates():
    currency = request.args.get('base', 'USD')
    rates    = get_rates()
    return jsonify({'base': 'USD', 'rates': rates, 'currency': currency})
