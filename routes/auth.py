import logging
import random
import re
import string

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import (current_user, login_required, login_user,
                         logout_user)
from werkzeug.security import generate_password_hash

from database.db import db
from models.user_model import User

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


def _next_user_id():
    rows = db.session.query(User.user_id).all()
    max_n = 0
    for (uid,) in rows:
        m = re.match(r"^US_(\d+)$", uid or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"US_{max_n + 1}"


def _send_mail(to_email: str, subject: str, body: str) -> bool:
    """
    Backward-compatible mail helper.
    Delegates to mail_utils.send_mail so all sending logic is centralised.
    """
    from mail_utils import send_mail
    return send_mail(to_email=to_email, subject=subject, body=body)


# ── Login ──────────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)

    next_url = request.args.get("next", "")

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)

            if user.must_change_password:
                flash(
                    "You are using a temporary password. "
                    "Please set a new permanent password.",
                    "warning",
                )
                return redirect(url_for("auth.change_password"))

            flash(f"Welcome back, {user.name}! 🎬", "success")
            if next_url:
                return redirect(next_url)
            return _redirect_by_role(user.role)

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", next=next_url)


# ── Register ───────────────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("user.home"))

    if request.method == "POST":
        name     = request.form.get("name",     "").strip()
        email    = request.form.get("email",    "").strip().lower()
        phone    = request.form.get("phone",    "").strip()
        city     = request.form.get("city",     "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm",  "")

        if not name or not email or not password:
            flash("Name, email and password are required.", "danger")
            return render_template("auth/register.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in.", "danger")
            return redirect(url_for("auth.login"))

        user = User(
            user_id      = _next_user_id(),
            name         = name,
            email        = email,
            phone_number = phone,
            city         = city,
            role         = "user",
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


# ── Logout ─────────────────────────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("user.home"))


# ── Change Password ────────────────────────────────────────────────────────────
@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user = User.query.get(current_user.user_id)
    mode = "first_login" if user.must_change_password else "dashboard"

    if request.method == "POST":
        new_pw  = request.form.get("new_password",     "")
        confirm = request.form.get("confirm_password", "")

        if mode == "dashboard":
            current_pw = request.form.get("current_password", "")
            if not user.check_password(current_pw):
                flash("Current password is incorrect.", "danger")
                return render_template("auth/change_password.html", mode=mode)

        if len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "danger")
            return render_template("auth/change_password.html", mode=mode)

        if new_pw != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/change_password.html", mode=mode)

        user.password_hash        = generate_password_hash(new_pw)
        user.must_change_password = False
        db.session.commit()

        flash("Password updated successfully! 🎉", "success")
        return _redirect_by_role(user.role)

    return render_template("auth/change_password.html", mode=mode)


# ── Forgot Password ────────────────────────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        try:
            email = request.form.get("email", "").strip().lower()
            user  = User.query.filter_by(email=email).first()

            if user:
                chars    = string.ascii_letters + string.digits + "!@#$"
                temp_pwd = "".join(random.choice(chars) for _ in range(8))

                from mail_utils import send_temp_password_email

                sent = send_temp_password_email(
                    user_name=user.name,
                    user_email=email,
                    temp_password=temp_pwd,
                    login_url=url_for("auth.login", _external=True),
                )

                if sent:
                    user.password_hash        = generate_password_hash(temp_pwd)
                    user.must_change_password = True
                    db.session.commit()
                    flash("A temporary password has been sent to your email.", "success")
                else:
                    logger.warning("[FORGOT-PW] Email failed for %s", email)
                    flash(
                        "Could not send email right now. "
                        "Please check your email address or contact support.",
                        "danger",
                    )
            else:
                flash(
                    "If that email is registered, a temporary password will be sent.",
                    "info",
                )

            return redirect(url_for("auth.login"))

        except Exception as exc:
            logger.error("[FORGOT-PW] Unexpected error: %s", exc, exc_info=True)
            db.session.rollback()
            flash("An unexpected error occurred. Please try again.", "danger")

    return render_template("auth/forgot_password.html")

# ── Helper ─────────────────────────────────────────────────────────────────────
def _redirect_by_role(role):
    if role == "admin":
        return redirect(url_for("admin.dashboard"))
    if role == "theater_owner":
        return redirect(url_for("owner.dashboard"))
    return redirect(url_for("user.home"))
