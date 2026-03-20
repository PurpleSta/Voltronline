from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Vendor

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('shop.index'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            nxt = request.args.get('next')
            if user.is_vendor:
                return redirect(nxt or url_for('vendor.dashboard'))
            if user.is_admin:
                return redirect(nxt or url_for('vendor.dashboard'))
            return redirect(nxt or url_for('shop.index'))
        flash('Invalid email or password.', 'error')
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('shop.index'))
    if request.method == 'POST':
        role      = request.form.get('role', 'customer')
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip().lower()
        phone     = request.form.get('phone', '').strip()
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')

        if not all([full_name, email, password]):
            flash('Please fill in all required fields.', 'error')
            return render_template('auth/register.html')
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/register.html')
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return render_template('auth/register.html')

        user = User(full_name=full_name, email=email, phone=phone, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if role == 'vendor':
            store_name = request.form.get('store_name', full_name + ' Store').strip()
            description = request.form.get('store_description', '').strip()
            vendor = Vendor(user_id=user.id, store_name=store_name, description=description)
            db.session.add(vendor)

        db.session.commit()
        login_user(user)
        flash(f'Welcome to VOLTR, {full_name}!', 'success')
        if role == 'vendor':
            return redirect(url_for('vendor.dashboard'))
        return redirect(url_for('shop.index'))
    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('shop.index'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name', current_user.full_name).strip()
        current_user.phone     = request.form.get('phone', current_user.phone)
        new_pw = request.form.get('new_password', '')
        if new_pw:
            if not current_user.check_password(request.form.get('current_password', '')):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('auth.profile'))
            if new_pw != request.form.get('confirm_password', ''):
                flash('New passwords do not match.', 'error')
                return redirect(url_for('auth.profile'))
            current_user.set_password(new_pw)
        db.session.commit()
        flash('Profile updated.', 'success')
    return render_template('auth/profile.html')
