import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from functools import wraps
from models import db, Product, Category, Order, OrderItem, OrderStatusLog, Vendor
from datetime import datetime, timedelta

vendor_bp = Blueprint('vendor', __name__, url_prefix='/vendor')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

def vendor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_vendor:
            flash('Vendor access required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload(file):
    filename = secure_filename(file.filename)
    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    unique_name = f"{ts}_{filename}"
    upload_dir = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, unique_name)
    file.save(path)
    return f"/{current_app.config['UPLOAD_FOLDER']}/{unique_name}"


# ─── Dashboard ───────────────────────────────
@vendor_bp.route('/dashboard')
@login_required
@vendor_required
def dashboard():
    v = current_user.vendor
    products  = Product.query.filter_by(vendor_id=v.id).order_by(Product.created_at.desc()).all()
    # Orders containing vendor's products
    vendor_product_ids = [p.id for p in products]
    order_items = (OrderItem.query
        .filter(OrderItem.product_id.in_(vendor_product_ids))
        .all()) if vendor_product_ids else []
    order_ids = list({oi.order_id for oi in order_items})
    orders = Order.query.filter(Order.id.in_(order_ids)).order_by(Order.created_at.desc()).limit(10).all() if order_ids else []

    # Stats
    total_sales = sum(
        float(oi.unit_price_usd) * oi.quantity
        for oi in order_items
        if oi.order and oi.order.status not in ('cancelled','refunded','pending_payment')
    )
    active_products  = sum(1 for p in products if p.is_active)
    pending_orders   = sum(1 for o in orders if o.status in ('confirmed','processing','packed'))

    return render_template('vendor/dashboard.html',
        vendor=v, products=products[:8], orders=orders,
        total_sales=total_sales, active_products=active_products,
        pending_orders=pending_orders, total_products=len(products))


# ─── Products list ───────────────────────────
@vendor_bp.route('/products')
@login_required
@vendor_required
def products():
    v = current_user.vendor
    q = request.args.get('q', '').strip()
    query = Product.query.filter_by(vendor_id=v.id)
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))
    prods = query.order_by(Product.created_at.desc()).all()
    return render_template('vendor/products.html', products=prods, q=q)


# ─── Add product ─────────────────────────────
@vendor_bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@vendor_required
def add_product():
    categories = Category.query.order_by(Category.name).all()
    if request.method == 'POST':
        name        = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price       = request.form.get('price')
        orig_price  = request.form.get('orig_price') or None
        stock       = request.form.get('stock', 0)
        badge       = request.form.get('badge', '')
        cat_id      = request.form.get('category_id') or None

        if not name or not price:
            flash('Product name and price are required.', 'error')
            return render_template('vendor/add_product.html', categories=categories)

        image_url = None
        file = request.files.get('image')
        if file and file.filename and allowed_file(file.filename):
            image_url = save_upload(file)
        elif request.form.get('image_url'):
            image_url = request.form.get('image_url').strip()

        product = Product(
            vendor_id   = current_user.vendor.id,
            category_id = cat_id,
            name        = name,
            description = description,
            price_usd   = float(price),
            orig_price_usd = float(orig_price) if orig_price else None,
            stock       = int(stock),
            badge       = badge,
            image_url   = image_url,
        )
        db.session.add(product)
        db.session.commit()
        flash(f'"{name}" listed successfully!', 'success')
        return redirect(url_for('vendor.products'))
    return render_template('vendor/add_product.html', categories=categories)


# ─── Edit product ─────────────────────────────
@vendor_bp.route('/products/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
@vendor_required
def edit_product(pid):
    p = Product.query.filter_by(id=pid, vendor_id=current_user.vendor.id).first_or_404()
    categories = Category.query.order_by(Category.name).all()
    if request.method == 'POST':
        p.name          = request.form.get('name', p.name).strip()
        p.description   = request.form.get('description', p.description).strip()
        p.price_usd     = float(request.form.get('price', p.price_usd))
        op = request.form.get('orig_price')
        p.orig_price_usd = float(op) if op else None
        p.stock         = int(request.form.get('stock', p.stock))
        p.badge         = request.form.get('badge', p.badge)
        p.category_id   = request.form.get('category_id') or p.category_id
        p.is_active     = bool(request.form.get('is_active'))

        file = request.files.get('image')
        if file and file.filename and allowed_file(file.filename):
            p.image_url = save_upload(file)
        elif request.form.get('image_url'):
            p.image_url = request.form.get('image_url').strip()

        db.session.commit()
        flash('Product updated.', 'success')
        return redirect(url_for('vendor.products'))
    return render_template('vendor/add_product.html', categories=categories, product=p, editing=True)


# ─── Toggle active ────────────────────────────
@vendor_bp.route('/products/<int:pid>/toggle', methods=['POST'])
@login_required
@vendor_required
def toggle_product(pid):
    p = Product.query.filter_by(id=pid, vendor_id=current_user.vendor.id).first_or_404()
    p.is_active = not p.is_active
    db.session.commit()
    return jsonify({'active': p.is_active})


# ─── Delete product ───────────────────────────
@vendor_bp.route('/products/<int:pid>/delete', methods=['POST'])
@login_required
@vendor_required
def delete_product(pid):
    p = Product.query.filter_by(id=pid, vendor_id=current_user.vendor.id).first_or_404()
    db.session.delete(p)
    db.session.commit()
    flash(f'"{p.name}" deleted.', 'info')
    return redirect(url_for('vendor.products'))


# ─── Vendor Orders ────────────────────────────
@vendor_bp.route('/orders')
@login_required
@vendor_required
def orders():
    v = current_user.vendor
    vpids = [p.id for p in v.products]
    ois   = OrderItem.query.filter(OrderItem.product_id.in_(vpids)).all() if vpids else []
    oids  = list({oi.order_id for oi in ois})
    ords  = (Order.query.filter(Order.id.in_(oids))
             .order_by(Order.created_at.desc()).all()) if oids else []
    return render_template('vendor/orders.html', orders=ords)


# ─── Update order status ─────────────────────
@vendor_bp.route('/orders/<oid>/status', methods=['POST'])
@login_required
@vendor_required
def update_order_status(oid):
    order  = Order.query.get_or_404(oid)
    status = request.form.get('status')
    note   = request.form.get('note', '')
    valid  = ['confirmed','processing','packed','shipped','out_for_delivery','delivered','cancelled']
    if status not in valid:
        flash('Invalid status.', 'error')
        return redirect(url_for('vendor.orders'))
    order.status = status
    log = OrderStatusLog(order_id=order.id, status=status, note=note, created_by=current_user.id)
    db.session.add(log)
    db.session.commit()
    flash(f'Order {oid} status updated to {status}.', 'success')
    return redirect(url_for('vendor.orders'))


# ─── Store settings ──────────────────────────
@vendor_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@vendor_required
def settings():
    v = current_user.vendor
    if request.method == 'POST':
        v.store_name  = request.form.get('store_name', v.store_name).strip()
        v.description = request.form.get('description', v.description).strip()
        file = request.files.get('logo')
        if file and file.filename and allowed_file(file.filename):
            v.logo_url = save_upload(file)
        current_user.full_name = request.form.get('full_name', current_user.full_name).strip()
        current_user.phone     = request.form.get('phone', current_user.phone)
        db.session.commit()
        flash('Settings saved.', 'success')
    return render_template('vendor/settings.html', vendor=v)
