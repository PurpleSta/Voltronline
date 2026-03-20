from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ─────────────────────────────────────────────
#  USER & AUTH
# ─────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name     = db.Column(db.String(150), nullable=False)
    phone         = db.Column(db.String(20))
    role          = db.Column(db.Enum('customer','vendor','admin'), default='customer', nullable=False)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    vendor    = db.relationship('Vendor', backref='user', uselist=False, lazy=True)
    orders    = db.relationship('Order', backref='customer', lazy=True)
    addresses = db.relationship('Address', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_vendor(self):
        return self.role == 'vendor'

    @property
    def is_admin(self):
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.email}>'


# ─────────────────────────────────────────────
#  VENDOR STORE
# ─────────────────────────────────────────────
class Vendor(db.Model):
    __tablename__ = 'vendors'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    store_name  = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    logo_url    = db.Column(db.String(500))
    is_verified = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship('Product', backref='vendor', lazy=True)

    def __repr__(self):
        return f'<Vendor {self.store_name}>'


# ─────────────────────────────────────────────
#  CATEGORY
# ─────────────────────────────────────────────
class Category(db.Model):
    __tablename__ = 'categories'
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False, unique=True)
    slug     = db.Column(db.String(100), nullable=False, unique=True)
    icon_url = db.Column(db.String(500))

    products = db.relationship('Product', backref='category', lazy=True)

    def __repr__(self):
        return f'<Category {self.name}>'


# ─────────────────────────────────────────────
#  PRODUCT
# ─────────────────────────────────────────────
class Product(db.Model):
    __tablename__ = 'products'
    id          = db.Column(db.Integer, primary_key=True)
    vendor_id   = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price_usd   = db.Column(db.Numeric(10, 2), nullable=False)
    orig_price_usd = db.Column(db.Numeric(10, 2))  # strike-through price
    stock       = db.Column(db.Integer, default=0)
    image_url   = db.Column(db.String(500))
    badge       = db.Column(db.Enum('new','sale','hot',''), default='')
    is_active   = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order_items = db.relationship('OrderItem', backref='product', lazy=True)

    def to_dict(self, currency='USD', rate=1.0):
        sym = {'USD':'$','EUR':'€','GBP':'£','KES':'KSh ','JPY':'¥','AUD':'A$','CAD':'C$'}.get(currency,'$')
        def fmt(v):
            if v is None: return None
            val = float(v) * rate
            return f"{sym}{val:,.0f}" if currency in ('KES','JPY') else f"{sym}{val:,.2f}"
        return {
            'id':          self.id,
            'name':        self.name,
            'description': self.description,
            'price':       fmt(self.price_usd),
            'price_raw':   float(self.price_usd),
            'orig_price':  fmt(self.orig_price_usd),
            'stock':       self.stock,
            'image_url':   self.image_url or '/static/img/placeholder.svg',
            'badge':       self.badge,
            'vendor':      self.vendor.store_name if self.vendor else '',
            'category':    self.category.name if self.category else '',
        }

    def __repr__(self):
        return f'<Product {self.name}>'


# ─────────────────────────────────────────────
#  DELIVERY ADDRESS
# ─────────────────────────────────────────────
class Address(db.Model):
    __tablename__ = 'addresses'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    full_name  = db.Column(db.String(150), nullable=False)
    phone      = db.Column(db.String(20), nullable=False)
    line1      = db.Column(db.String(255), nullable=False)
    city       = db.Column(db.String(100), nullable=False)
    postcode   = db.Column(db.String(20))
    country    = db.Column(db.String(100), default='Kenya')
    is_default = db.Column(db.Boolean, default=False)

    orders = db.relationship('Order', backref='address', lazy=True)

    def __repr__(self):
        return f'<Address {self.line1}, {self.city}>'


# ─────────────────────────────────────────────
#  ORDER
# ─────────────────────────────────────────────
ORDER_STATUSES = ['pending_payment','confirmed','processing','packed','shipped','out_for_delivery','delivered','cancelled','refunded']

class Order(db.Model):
    __tablename__ = 'orders'
    id             = db.Column(db.String(20), primary_key=True)   # e.g. VLT-A1B2C3
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    address_id     = db.Column(db.Integer, db.ForeignKey('addresses.id'))
    status         = db.Column(db.String(30), default='pending_payment')
    subtotal_usd   = db.Column(db.Numeric(10, 2), nullable=False)
    delivery_usd   = db.Column(db.Numeric(10, 2), default=4.00)
    total_usd      = db.Column(db.Numeric(10, 2), nullable=False)
    currency       = db.Column(db.String(5), default='USD')
    payment_method = db.Column(db.Enum('mpesa','paypal','card'), nullable=False)
    notes          = db.Column(db.Text)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items   = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    payment = db.relationship('Payment', backref='order', uselist=False, lazy=True)

    STATUS_LABELS = {
        'pending_payment': ('Awaiting Payment', 'orange'),
        'confirmed':       ('Confirmed',         'teal'),
        'processing':      ('Processing',        'blue'),
        'packed':          ('Packed',            'purple'),
        'shipped':         ('Dispatched',        'orange'),
        'out_for_delivery':('Out for Delivery',  'orange'),
        'delivered':       ('Delivered',         'green'),
        'cancelled':       ('Cancelled',         'red'),
        'refunded':        ('Refunded',          'gray'),
    }

    TIMELINE_STEPS = [
        ('confirmed',        'Order Confirmed',    'Your payment was received and order confirmed'),
        ('processing',       'Processing',         'Your items are being picked and verified'),
        ('packed',           'Packed',             'Your order has been packed and labelled'),
        ('shipped',          'Dispatched',         'Your order is on its way with our carrier'),
        ('out_for_delivery', 'Out for Delivery',   'Your order is out for delivery today'),
        ('delivered',        'Delivered',          'Package delivered successfully'),
    ]

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, (self.status, 'gray'))

    @property
    def current_step_index(self):
        keys = [s[0] for s in self.TIMELINE_STEPS]
        try:
            return keys.index(self.status)
        except ValueError:
            return 0

    def __repr__(self):
        return f'<Order {self.id}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.String(20), db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity   = db.Column(db.Integer, nullable=False, default=1)
    unit_price_usd = db.Column(db.Numeric(10, 2), nullable=False)

    @property
    def line_total_usd(self):
        return float(self.unit_price_usd) * self.quantity


# ─────────────────────────────────────────────
#  PAYMENT
# ─────────────────────────────────────────────
class Payment(db.Model):
    __tablename__ = 'payments'
    id                   = db.Column(db.Integer, primary_key=True)
    order_id             = db.Column(db.String(20), db.ForeignKey('orders.id'), nullable=False)
    method               = db.Column(db.String(20), nullable=False)
    status               = db.Column(db.Enum('pending','completed','failed','cancelled'), default='pending')
    amount_usd           = db.Column(db.Numeric(10, 2))
    # M-Pesa specific
    checkout_request_id  = db.Column(db.String(100), index=True)
    merchant_request_id  = db.Column(db.String(100))
    mpesa_receipt        = db.Column(db.String(50))
    mpesa_phone          = db.Column(db.String(20))
    # PayPal specific
    paypal_order_id      = db.Column(db.String(100))
    # Card specific
    card_last4           = db.Column(db.String(4))
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at           = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Payment {self.id} {self.method} {self.status}>'


# ─────────────────────────────────────────────
#  ORDER STATUS LOG
# ─────────────────────────────────────────────
class OrderStatusLog(db.Model):
    __tablename__ = 'order_status_logs'
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.String(20), db.ForeignKey('orders.id'), nullable=False)
    status     = db.Column(db.String(30), nullable=False)
    note       = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    order = db.relationship('Order', backref='status_logs')
