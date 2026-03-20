import os
import string
import random
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager
from flask_migrate import Migrate
from config import config


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ── Extensions ────────────────────────────────────
    from models import db, User
    db.init_app(app)

    migrate = Migrate(app, db)

    login_manager = LoginManager(app)
    login_manager.login_view      = 'auth.login'
    login_manager.login_message   = 'Please log in to continue.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ── Upload folder ──────────────────────────────────
    upload_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_dir, exist_ok=True)

    # ── Blueprints ─────────────────────────────────────
    from routes.auth    import auth_bp
    from routes.vendor  import vendor_bp
    from routes.shop    import shop_bp
    from routes.payment import payment_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(vendor_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(payment_bp)

    # ── Error handlers ─────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    # ── Template globals ───────────────────────────────
    @app.context_processor
    def globals():
        from routes.shop import CURRENCY_SYMBOLS, get_rates
        from flask import session
        cur = session.get('currency', 'USD')
        return {
            'current_year': datetime.utcnow().year,
            'currency':     cur,
            'symbol':       CURRENCY_SYMBOLS.get(cur, '$'),
            'CURRENCY_SYMBOLS': CURRENCY_SYMBOLS,
        }

    # ── CLI: seed database ─────────────────────────────
    @app.cli.command('seed')
    def seed_db():
        """Seed the database with categories, sample vendor and products."""
        from models import User, Vendor, Category, Product
        print('Seeding database...')

        # Categories
        cats = [
            ('Audio',       'audio'),
            ('Peripherals', 'peripherals'),
            ('Lighting',    'lighting'),
            ('Power',       'power'),
            ('Bags',        'bags'),
            ('Wearables',   'wearables'),
            ('Phones',      'phones'),
            ('Computers',   'computers'),
        ]
        cat_map = {}
        for name, slug in cats:
            c = Category.query.filter_by(slug=slug).first()
            if not c:
                c = Category(name=name, slug=slug)
                db.session.add(c)
                db.session.flush()
            cat_map[slug] = c

        # Admin user
        admin = User.query.filter_by(email='admin@voltr.shop').first()
        if not admin:
            admin = User(full_name='VOLTR Admin', email='admin@voltr.shop',
                         phone='+254700000000', role='admin')
            admin.set_password('admin123!')
            db.session.add(admin)
            db.session.flush()
            print('  Admin: admin@voltr.shop / admin123!')

        # Demo vendor
        vendor_user = User.query.filter_by(email='vendor@voltr.shop').first()
        if not vendor_user:
            vendor_user = User(full_name='TechHub Kenya', email='vendor@voltr.shop',
                               phone='+254711000001', role='vendor')
            vendor_user.set_password('vendor123!')
            db.session.add(vendor_user)
            db.session.flush()
            vendor = Vendor(user_id=vendor_user.id, store_name='TechHub Kenya',
                            description='Your premier electronics destination in Nairobi.',
                            logo_url='https://images.unsplash.com/photo-1563770660941-20978e870e26?w=80',
                            is_verified=True)
            db.session.add(vendor)
            db.session.flush()
            print('  Vendor: vendor@voltr.shop / vendor123!')
        else:
            vendor = vendor_user.vendor

        # Demo customer
        cust = User.query.filter_by(email='jane@example.com').first()
        if not cust:
            cust = User(full_name='Jane Mwangi', email='jane@example.com',
                        phone='+254712345678', role='customer')
            cust.set_password('customer123!')
            db.session.add(cust)
            db.session.flush()
            from models import Address
            addr = Address(user_id=cust.id, full_name='Jane Mwangi',
                           phone='+254712345678', line1='123 Westlands Road, Apt 4B',
                           city='Nairobi', postcode='00100', country='Kenya', is_default=True)
            db.session.add(addr)
            print('  Customer: jane@example.com / customer123!')

        # Products with real Unsplash images
        sample_products = [
            ('Sony WH-1000XM5 Headphones',    'audio',
             'Industry-leading noise cancellation with up to 30-hour battery life and crystal-clear call quality.',
             249.99, 299.99, 15, 'hot',
             'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&q=80'),
            ('JBL Charge 5 Speaker',          'audio',
             'Portable Bluetooth speaker with 20 hours of playtime, IP67 waterproof rating and built-in power bank.',
             179.00, None, 22, 'new',
             'https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=600&q=80'),
            ('Logitech MX Keys Keyboard',     'peripherals',
             'Advanced wireless illuminated keyboard with smart backlighting and comfortable key shapes.',
             119.99, 149.99, 18, None,
             'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600&q=80'),
            ('Logitech MX Master 3S Mouse',   'peripherals',
             'High-performance wireless mouse with ultra-fast MagSpeed scrolling and ergonomic design.',
             89.99, 109.99, 30, 'sale',
             'https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=600&q=80'),
            ('Elgato Key Light Air',          'lighting',
             'Professional app-controlled studio LED light panel — perfect for streaming and video calls.',
             129.99, None, 12, 'new',
             'https://images.unsplash.com/photo-1513506003901-1e6a229e2d15?w=600&q=80'),
            ('Anker 727 Charging Station',    'power',
             '100W GaNPrime desktop charging station with 2 USB-C and 4 USB-A ports for all your devices.',
             69.99, None, 40, None,
             'https://images.unsplash.com/photo-1615526675159-e248c3021d3f?w=600&q=80'),
            ('Targus 15.6" Laptop Backpack',  'bags',
             'Water-resistant laptop backpack with dedicated compartments and ergonomic shoulder straps.',
             79.99, None, 25, None,
             'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600&q=80'),
            ('Apple Watch SE (2nd Gen)',      'wearables',
             'A powerful smartwatch with crash detection, heart rate monitoring, and fitness tracking.',
             249.00, 299.00, 8, 'sale',
             'https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=600&q=80'),
            ('Samsung Galaxy S24',            'phones',
             'Flagship Android smartphone with 50MP camera, 6.2" display and 7 years of OS updates.',
             799.00, None, 10, 'new',
             'https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=600&q=80'),
            ('Dell XPS 13 Laptop',            'computers',
             'Ultra-compact laptop with Intel Core i7, 16GB RAM and a brilliant 13.4" InfinityEdge display.',
             1299.00, 1499.00, 5, None,
             'https://images.unsplash.com/photo-1593642702821-c8da6771f0c6?w=600&q=80'),
            ('Razer DeathAdder V3 Mouse',     'peripherals',
             'Ultra-lightweight esports mouse with 30K DPI optical sensor for pinpoint precision.',
             99.99, None, 20, 'hot',
             'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=600&q=80'),
            ('Jabra Evolve2 55 Headset',      'audio',
             'Professional wireless headset with hybrid ANC and all-day battery life for serious focus.',
             329.00, 399.00, 7, None,
             'https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&q=80'),
        ]

        for name, cat_slug, desc, price, orig, stock, badge, img in sample_products:
            if not Product.query.filter_by(name=name, vendor_id=vendor.id).first():
                p = Product(
                    vendor_id      = vendor.id,
                    category_id    = cat_map.get(cat_slug, cat_map['audio']).id,
                    name           = name,
                    description    = desc,
                    price_usd      = price,
                    orig_price_usd = orig,
                    stock          = stock,
                    badge          = badge or '',
                    image_url      = img,
                    is_active      = True,
                )
                db.session.add(p)

        db.session.commit()
        print('Done! Seed data inserted.')

    return app


app = create_app(os.getenv('FLASK_ENV', 'development'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
