import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 5 * 1024 * 1024))
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'static/uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

    # MySQL
    MYSQL_HOST     = os.getenv('MYSQL_HOST', 'localhost')
    MYSQL_PORT     = int(os.getenv('MYSQL_PORT', 3306))
    MYSQL_USER     = os.getenv('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    MYSQL_DB       = os.getenv('MYSQL_DB', 'voltr_shop')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('MYSQL_USER','root')}:"
        f"{os.getenv('MYSQL_PASSWORD','')}@"
        f"{os.getenv('MYSQL_HOST','localhost')}:"
        f"{os.getenv('MYSQL_PORT','3306')}/"
        f"{os.getenv('MYSQL_DB','voltr_shop')}?charset=utf8mb4"
    )

    # M-Pesa Daraja
    MPESA_CONSUMER_KEY    = os.getenv('MPESA_CONSUMER_KEY', '')
    MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET', '')
    MPESA_SHORTCODE       = os.getenv('MPESA_SHORTCODE', '174379')
    MPESA_PASSKEY         = os.getenv('MPESA_PASSKEY', '')
    MPESA_CALLBACK_URL    = os.getenv('MPESA_CALLBACK_URL', 'https://example.com/api/payment/mpesa/callback')
    MPESA_ENV             = os.getenv('MPESA_ENV', 'sandbox')

    MPESA_BASE_URL = (
        'https://sandbox.safaricom.co.ke'
        if os.getenv('MPESA_ENV', 'sandbox') == 'sandbox'
        else 'https://api.safaricom.co.ke'
    )

    # PayPal
    PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID', 'sb')
    PAYPAL_ENV       = os.getenv('PAYPAL_ENV', 'sandbox')

    # Currency
    CURRENCY_API_URL = os.getenv('CURRENCY_API_URL', 'https://api.frankfurter.app/latest')


class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig,
}
