import os, sys
from flask import Flask, render_template
from datetime import datetime

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-vercel')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Use MySQL if configured, else SQLite (works immediately with no setup)
    if os.environ.get('MYSQL_HOST'):
        uri = (f"mysql+pymysql://{os.environ['MYSQL_USER']}:{os.environ['MYSQL_PASSWORD']}"
               f"@{os.environ['MYSQL_HOST']}:{os.environ.get('MYSQL_PORT','3306')}"
               f"/{os.environ.get('MYSQL_DB','voltr_shop')}?charset=utf8mb4")
    else:
        db_path = '/tmp/voltr.db' if os.environ.get('VERCEL') else 'voltr.db'
        uri = f'sqlite:///{db_path}'

    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    app.config['UPLOAD_FOLDER'] = '/tmp/uploads' if os.environ.get('VERCEL') else 'static/uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # M-Pesa
    app.config['MPESA_CONSUMER_KEY']    = os.environ.get('MPESA_CONSUMER_KEY', '')
    app.config['MPESA_CONSUMER_SECRET'] = os.environ.get('MPESA_CONSUMER_SECRET', '')
    app.config['MPESA_SHORTCODE']       = os.environ.get('MPESA_SHORTCODE', '174379')
    app.config['MPESA_PASSKEY']         = os.environ.get('MPESA_PASSKEY', '')
    app.config['MPESA_CALLBACK_URL']    = os.environ.get('MPESA_CALLBACK_URL', '')
    app.config['MPESA_ENV']             = os.environ.get('MPESA_ENV', 'sandbox')
    app.config['MPESA_BASE_URL']        = (
        'https://sandbox.safaricom.co.ke'
        if app.config['MPESA_ENV'] == 'sandbox'
        else 'https://api.safaricom.co.ke'
    )
    app.config['PAYPAL_CLIENT_ID'] = os.environ.get('PAYPAL_CLIENT_ID', 'sb')

    from models import db, User
    db.init_app(app)

    from flask_login import LoginManager
    lm = LoginManager(app)
    lm.login_view = 'auth.login'
    lm.login_message_category = 'info'

    @lm.user_loader
    def load_user(uid):
        return User.query.get(int(uid))

    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            app.logger.warning(f'DB init warning: {e}')

    from routes.auth    import auth_bp
    from routes.vendor  import vendor_bp
    from routes.shop    import shop_bp
    from routes.payment import payment_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(vendor_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(payment_bp)

    @app.errorhandler(404)
    def not_found(e): return render_template('errors/404.html'), 404
    @app.errorhandler(500)
    def server_error(e): return render_template('errors/500.html'), 500

    @app.context_processor
    def globals():
        from routes.shop import CURRENCY_SYMBOLS, get_rates
        from flask import session
        cur = session.get('currency', 'KES')
        return {'current_year': datetime.utcnow().year, 'currency': cur,
                'symbol': CURRENCY_SYMBOLS.get(cur, 'KSh '), 'CURRENCY_SYMBOLS': CURRENCY_SYMBOLS}

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
