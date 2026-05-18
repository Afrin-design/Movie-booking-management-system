"""
routes/theater_owners.py
Brand-Owner mapping management for CineHub Admin.
"""

import secrets
import string
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func

from database.db import db
from models.user_model import User
from models.theater_model import Theater
from models.brand_model import TheaterBrand

theater_owners_bp = Blueprint("theater_owners", __name__)


# ── Guard ─────────────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _gen_temp_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _next_user_id():
    from models.user_model import User
    last = db.session.query(func.max(User.user_id)).scalar()
    if not last:
        return "U001"
    try:
        num = int(last.lstrip("U")) + 1
        return f"U{num:03d}"
    except ValueError:
        return secrets.token_hex(4).upper()


# ── Helper: owners-with-theater-count query ───────────────────────────────────
def _owners_with_count(brand_id=None, status=None, search=None):
    """
    Returns list of dicts:
      { user_id, name, email, brand_name, theater_count, status }

    Counts theaters by brand_id (owner.brand_id == theater.brand_id)
    so even unassigned theaters roll up correctly.
    """
    theater_count_sq = (
        db.session.query(
            Theater.brand_id,
            func.count(Theater.theater_id).label("cnt")
        )
        .filter(Theater.brand_id.isnot(None))
        .group_by(Theater.brand_id)
        .subquery()
    )

    q = (
        db.session.query(
            User,
            TheaterBrand.brand_name,
            func.coalesce(theater_count_sq.c.cnt, 0).label("theater_count")
        )
        .join(TheaterBrand, TheaterBrand.id == User.brand_id, isouter=True)
        .outerjoin(theater_count_sq, theater_count_sq.c.brand_id == User.brand_id)
        .filter(User.role == "theater_owner")
    )

    if brand_id:
        q = q.filter(User.brand_id == brand_id)
    if status:
        q = q.filter(User.status == status)
    if search:
        term = f"%{search}%"
        q = q.filter(
            db.or_(User.name.ilike(term), User.email.ilike(term))
        )

    return q.order_by(User.name).all()


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

# ── Theater Owners list ───────────────────────────────────────────────────────
@theater_owners_bp.route("/theater-owners")
@admin_required
def theater_owners():
    brands  = TheaterBrand.query.order_by(TheaterBrand.brand_name).all()
    brand_f  = request.args.get("brand", "", type=str)
    status_f = request.args.get("status", "")
    search   = request.args.get("q", "").strip()

    rows = _owners_with_count(
        brand_id=int(brand_f) if brand_f.isdigit() else None,
        status=status_f or None,
        search=search or None,
    )

    return render_template(
        "admin/theater_owners.html",
        rows=rows,
        brands=brands,
        brand_f=brand_f,
        status_f=status_f,
        search=search,
    )


# ── API: owners-with-theater-count (JSON) ─────────────────────────────────────
@theater_owners_bp.route("/api/owners-with-theater-count")
@admin_required
def api_owners_with_theater_count():
    brand_id = request.args.get("brand_id", type=int)
    status   = request.args.get("status", "")
    search   = request.args.get("q", "")

    rows = _owners_with_count(
        brand_id=brand_id,
        status=status or None,
        search=search or None,
    )

    data = [
        {
            "user_id":       owner.user_id,
            "name":          owner.name,
            "email":         owner.email,
            "brand_id":      owner.brand_id,
            "brand_name":    brand_name or "—",
            "theater_count": theater_count,
            "status":        owner.status,
        }
        for owner, brand_name, theater_count in rows
    ]
    return jsonify({"owners": data, "total": len(data)})


# ── Create Owner ──────────────────────────────────────────────────────────────
@theater_owners_bp.route("/theater-owners/create", methods=["GET", "POST"])
@admin_required
def create_theater_owner():
    brands = TheaterBrand.query.filter_by(status="Active").order_by(TheaterBrand.brand_name).all()

    if request.method == "POST":
        name     = request.form.get("name",  "").strip()
        email    = request.form.get("email", "").strip().lower()
        phone    = request.form.get("phone", "").strip()
        brand_id = request.form.get("brand_id", type=int)

        if not name or not email:
            flash("Name and email are required.", "danger")
            return render_template("admin/create_theater_owner.html", brands=brands)

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return render_template("admin/create_theater_owner.html", brands=brands)

        # Enforce one owner per brand
        if brand_id:
            existing = User.query.filter_by(brand_id=brand_id, role="theater_owner").first()
            if existing:
                brand = TheaterBrand.query.get(brand_id)
                flash(
                    f"Brand '{brand.brand_name}' is already managed by '{existing.name}'. "
                    "Each brand can have only one owner.",
                    "danger"
                )
                return render_template("admin/create_theater_owner.html", brands=brands)

        temp_pwd = _gen_temp_password()
        owner = User(
            user_id              = _next_user_id(),
            name                 = name,
            email                = email,
            phone_number         = phone,
            role                 = "theater_owner",
            brand_id             = brand_id or None,
            status               = "Active",
            must_change_password = True,
        )
        owner.set_password(temp_pwd)
        db.session.add(owner)

        # Auto-assign all theaters of this brand to this owner
        if brand_id:
            Theater.query.filter_by(brand_id=brand_id).update(
                {"owner_id": owner.user_id},
                synchronize_session="fetch"
            )

        db.session.commit()

        try:
            from routes.auth import _send_mail
            sent = _send_mail(
                to_email=email,
                subject="Your CineHub Theater Owner Account",
                body=(
                    f"Hello {name},\n\n"
                    f"Your Theater Owner account has been created.\n\n"
                    f"Email    : {email}\n"
                    f"Password : {temp_pwd}\n\n"
                    f"Please log in and change your password immediately.\n\n"
                    f"— CineHub Admin"
                )
            )
            if sent:
                flash(f"Owner '{name}' created. Credentials emailed to {email}.", "success")
            else:
                flash(f"Owner '{name}' created. Temp password: {temp_pwd} (share manually!)", "warning")
        except Exception:
            flash(f"Owner '{name}' created. Temp password: {temp_pwd} (email not sent).", "warning")

        return redirect(url_for("theater_owners.theater_owners"))

    return render_template("admin/create_theater_owner.html", brands=brands)


# ── Edit Owner ────────────────────────────────────────────────────────────────
@theater_owners_bp.route("/theater-owners/<user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_theater_owner(user_id):
    owner  = User.query.filter_by(user_id=user_id, role="theater_owner").first_or_404()
    brands = TheaterBrand.query.order_by(TheaterBrand.brand_name).all()

    if request.method == "POST":
        name     = request.form.get("name",  "").strip()
        email    = request.form.get("email", "").strip().lower()
        phone    = request.form.get("phone", "").strip()
        brand_id = request.form.get("brand_id", type=int)

        if not name or not email:
            flash("Name and email are required.", "danger")
            return render_template("admin/create_theater_owner.html", owner=owner, brands=brands)

        conflict = User.query.filter(
            User.email == email, User.user_id != user_id
        ).first()
        if conflict:
            flash("Email already in use by another account.", "danger")
            return render_template("admin/create_theater_owner.html", owner=owner, brands=brands)

        # Enforce one owner per brand (excluding self)
        if brand_id and brand_id != owner.brand_id:
            existing = User.query.filter(
                User.brand_id == brand_id,
                User.role == "theater_owner",
                User.user_id != user_id
            ).first()
            if existing:
                brand = TheaterBrand.query.get(brand_id)
                flash(
                    f"Brand '{brand.brand_name}' is already managed by '{existing.name}'.",
                    "danger"
                )
                return render_template("admin/create_theater_owner.html", owner=owner, brands=brands)

        old_brand_id = owner.brand_id

        owner.name         = name
        owner.email        = email
        owner.phone_number = phone
        owner.brand_id     = brand_id or None

        # Re-assign theaters: detach old brand theaters, assign new brand theaters
        if old_brand_id and old_brand_id != brand_id:
            Theater.query.filter_by(brand_id=old_brand_id, owner_id=user_id).update(
                {"owner_id": None}, synchronize_session="fetch"
            )
        if brand_id:
            Theater.query.filter_by(brand_id=brand_id).update(
                {"owner_id": user_id}, synchronize_session="fetch"
            )

        db.session.commit()
        flash(f"Owner '{name}' updated successfully.", "success")
        return redirect(url_for("theater_owners.theater_owners"))

    return render_template("admin/create_theater_owner.html", owner=owner, brands=brands)


# ── Toggle Status (Activate / Disable) ───────────────────────────────────────
@theater_owners_bp.route("/theater-owners/<user_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_owner_status(user_id):
    owner = User.query.filter_by(user_id=user_id, role="theater_owner").first_or_404()
    owner.status = "Inactive" if owner.status == "Active" else "Active"
    db.session.commit()
    flash(
        f"Owner '{owner.name}' has been {'activated' if owner.status == 'Active' else 'disabled'}.",
        "success"
    )
    return redirect(url_for("theater_owners.theater_owners"))


# ── Delete Owner ──────────────────────────────────────────────────────────────
@theater_owners_bp.route("/theater-owners/<user_id>/delete", methods=["POST"])
@admin_required
def delete_theater_owner(user_id):
    owner = User.query.filter_by(user_id=user_id, role="theater_owner").first_or_404()
    # Unassign their theaters instead of cascade-deleting
    Theater.query.filter_by(owner_id=user_id).update(
        {"owner_id": None}, synchronize_session="fetch"
    )
    name = owner.name
    db.session.delete(owner)
    db.session.commit()
    flash(f"Owner '{name}' deleted. Their theaters have been unassigned.", "warning")
    return redirect(url_for("theater_owners.theater_owners"))


# ── Send Credentials ──────────────────────────────────────────────────────────
@theater_owners_bp.route("/theater-owners/<user_id>/send-credentials", methods=["POST"])
@admin_required
def send_owner_credentials(user_id):
    owner    = User.query.filter_by(user_id=user_id, role="theater_owner").first_or_404()
    temp_pwd = _gen_temp_password()
    owner.set_password(temp_pwd)
    owner.must_change_password = True
    db.session.commit()

    try:
        from routes.auth import _send_mail
        sent = _send_mail(
            to_email=owner.email,
            subject="Your CineHub Theater Owner — New Password",
            body=(
                f"Hello {owner.name},\n\n"
                f"Your password has been reset by an admin.\n\n"
                f"Email    : {owner.email}\n"
                f"Password : {temp_pwd}\n\n"
                f"Please log in and change your password immediately.\n\n"
                f"— CineHub Admin"
            )
        )
        if sent:
            flash(f"New credentials sent to {owner.email}.", "success")
        else:
            flash(f"Password reset. Temp: {temp_pwd} (email failed — share manually).", "warning")
    except Exception:
        flash(f"Password reset to {temp_pwd} (email not configured).", "warning")

    return redirect(url_for("theater_owners.theater_owners"))


# ── Brands Management ─────────────────────────────────────────────────────────
@theater_owners_bp.route("/brands")
@admin_required
def brands():
    all_brands = (
        db.session.query(
            TheaterBrand,
            func.count(Theater.theater_id).label("theater_count"),
        )
        .outerjoin(Theater, Theater.brand_id == TheaterBrand.id)
        .group_by(TheaterBrand.id)
        .order_by(TheaterBrand.brand_name)
        .all()
    )
    return render_template("admin/brands.html", brands=all_brands)


@theater_owners_bp.route("/brands/add", methods=["POST"])
@admin_required
def add_brand():
    name = request.form.get("brand_name", "").strip()
    if not name:
        flash("Brand name is required.", "danger")
        return redirect(url_for("theater_owners.brands"))
    if TheaterBrand.query.filter_by(brand_name=name).first():
        flash(f"Brand '{name}' already exists.", "danger")
        return redirect(url_for("theater_owners.brands"))
    db.session.add(TheaterBrand(brand_name=name))
    db.session.commit()
    flash(f"Brand '{name}' added.", "success")
    return redirect(url_for("theater_owners.brands"))


@theater_owners_bp.route("/brands/<int:brand_id>/edit", methods=["POST"])
@admin_required
def edit_brand(brand_id):
    brand      = TheaterBrand.query.get_or_404(brand_id)
    brand.brand_name = request.form.get("brand_name", brand.brand_name).strip()
    brand.status     = request.form.get("status", brand.status)
    db.session.commit()
    flash(f"Brand '{brand.brand_name}' updated.", "success")
    return redirect(url_for("theater_owners.brands"))


@theater_owners_bp.route("/brands/<int:brand_id>/delete", methods=["POST"])
@admin_required
def delete_brand(brand_id):
    brand = TheaterBrand.query.get_or_404(brand_id)
    count = Theater.query.filter_by(brand_id=brand_id).count()
    if count > 0:
        flash(f"Cannot delete '{brand.brand_name}' — it has theaters assigned.", "danger")
        return redirect(url_for("theater_owners.brands"))
    name = brand.brand_name
    db.session.delete(brand)
    db.session.commit()
    flash(f"Brand '{name}' deleted.", "warning")
    return redirect(url_for("theater_owners.brands"))
