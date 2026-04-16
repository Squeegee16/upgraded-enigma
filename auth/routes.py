"""
Authentication Routes
=====================
Handles user registration, login, and logout.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from auth.forms import LoginForm, RegistrationForm
from models import db
from models.user import User
from urllib.parse import urlparse

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handle user login.
    
    GET: Display login form
    POST: Validate credentials and create session
    """
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        # Query user by callsign (case-insensitive)
        user = User.query.filter_by(
            callsign=form.callsign.data.upper()
        ).first()
        
        # Verify user exists and password is correct
        if user is None or not user.check_password(form.password.data):
            flash('Invalid callsign or password', 'danger')
            return redirect(url_for('auth.login'))
        
        # Update last login timestamp
        user.update_last_login()
        
        # Log user in
        login_user(user, remember=form.remember_me.data)
        
        # Redirect to next page or dashboard
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('dashboard.index')
        
        flash(f'Welcome back, {user.callsign}!', 'success')
        return redirect(next_page)
    
    return render_template('auth/login.html', title='Sign In', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handle user registration.
    
    GET: Display registration form
    POST: Create new user account
    """
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = RegistrationForm()
    
    if form.validate_on_submit():
        # Create new user
        # Handle optional email - store None if empty, otherwise lowercase trimmed version
        email_value = None
        if form.email.data and form.email.data.strip():
            email_value = form.email.data.strip().lower()
        
        user = User(
            callsign=form.callsign.data.upper(),
            email=email_value
        )
        user.set_password(form.password.data)
        
        # Save to database
        try:
            db.session.add(user)
            db.session.commit()
            flash(f'Registration successful! Welcome, {user.callsign}!', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            # Check if it's a unique constraint violation
            if 'UNIQUE constraint failed' in str(e) or 'unique constraint' in str(e).lower():
                if 'email' in str(e).lower():
                    flash('Email address already registered. Please use a different email.', 'danger')
                else:
                    flash('Callsign already registered. Please use a different callsign.', 'danger')
            else:
                flash(f'An error occurred during registration: {str(e)}', 'danger')
            return redirect(url_for('auth.register'))
    
    return render_template('auth/register.html', title='Register', form=form)

@auth_bp.route('/logout')
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
