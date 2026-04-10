"""
Secure login & registration using Flask-Login + bcrypt.
"""

from flask import Blueprint, render_template, redirect, url_for, flash
from extensions import db, bcrypt
from models import User
from .forms import RegisterForm, LoginForm
from flask_login import login_user, logout_user, login_required

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["GET","POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hash_pw = bcrypt.generate_password_hash(form.password.data).decode()
        user = User(callsign=form.callsign.data.upper(), password_hash=hash_pw)
        db.session.add(user)
        db.session.commit()
        flash("Registered successfully")
        return redirect(url_for("auth.login"))
    return render_template("register.html", form=form)

@auth_bp.route("/login", methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(callsign=form.callsign.data.upper()).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            return redirect(url_for("dashboard.dashboard"))
        flash("Invalid credentials")
    return render_template("login.html", form=form)

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))