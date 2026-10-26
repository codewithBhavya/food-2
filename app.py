from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import DB_PATH, get_connection, init_db

app = Flask(__name__)
app.secret_key = "foodease-dev-secret"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access only.", "error")
            return redirect(url_for("home"))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def load_user():
    g.user = None
    g.cart_count = 0
    if not session.get("user_id"):
        return
    conn = get_connection()
    user = conn.execute(
        "SELECT user_id, full_name, email, phone, role FROM users WHERE user_id = ?",
        (session["user_id"],),
    ).fetchone()
    if user:
        g.user = user
        row = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS qty FROM cart_items WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()
        g.cart_count = row["qty"]
    conn.close()


@app.route("/")
def home():
    conn = get_connection()
    restaurants = conn.execute(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM menu_items m WHERE m.restaurant_id = r.restaurant_id AND m.is_available = 1) AS dish_count,
               (SELECT MIN(price) FROM menu_items m WHERE m.restaurant_id = r.restaurant_id) AS from_price
        FROM restaurants r
        WHERE r.is_open = 1
        ORDER BY r.name
        """
    ).fetchall()
    featured = conn.execute(
        """
        SELECT * FROM (
            SELECT * FROM v_public_menu
            WHERE is_available = 1 AND is_open = 1 AND category_name = 'Starters'
            ORDER BY price DESC
            LIMIT 2
        )
        UNION ALL
        SELECT * FROM (
            SELECT * FROM v_public_menu
            WHERE is_available = 1 AND is_open = 1 AND category_name = 'Desserts'
            ORDER BY price DESC
            LIMIT 2
        )
        """
    ).fetchall()
    conn.close()
    return render_template("home.html", restaurants=restaurants, featured=featured)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        line1 = request.form.get("line1", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        postal = request.form.get("postal_code", "").strip()
        if not all([name, email, phone, password, line1, city, state, postal]):
            flash("Fill every field to create an account.", "error")
            return render_template("register.html")
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO users (full_name, email, phone, password_hash, role)
                VALUES (?, ?, ?, ?, 'customer')
                """,
                (name, email, phone, generate_password_hash(password)),
            )
            conn.execute(
                """
                INSERT INTO addresses (user_id, line1, city, state, postal_code, is_default)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (cur.lastrowid, line1, city, state, postal),
            )
            conn.execute("COMMIT")
            flash("Account created. Sign in to order.", "success")
            return redirect(url_for("login"))
        except Exception:
            conn.execute("ROLLBACK")
            flash("That email or phone is already registered.", "error")
        finally:
            conn.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = get_connection()
        user = conn.execute(
            "SELECT user_id, password_hash, role, full_name FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["user_id"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name'].split()[0]}.", "success")
            nxt = request.args.get("next") or url_for("home")
            return redirect(nxt)
        flash("Incorrect email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Signed out.", "info")
    return redirect(url_for("home"))


@app.route("/menu")
def menu():
    q = request.args.get("q", "").strip()
    cuisine = request.args.get("cuisine", "").strip()
    restaurant_id = request.args.get("restaurant", type=int)
    conn = get_connection()
    cuisines = conn.execute(
        "SELECT DISTINCT cuisine FROM restaurants WHERE is_open = 1 ORDER BY cuisine"
    ).fetchall()
    restaurants = conn.execute(
        "SELECT restaurant_id, name FROM restaurants WHERE is_open = 1 ORDER BY name"
    ).fetchall()

    sql = """
        SELECT v.*,
               CASE
                   WHEN v.price >= 250 THEN 'Chef special'
                   WHEN v.price >= 150 THEN 'Popular'
                   ELSE 'Value'
               END AS price_tag
        FROM v_public_menu v
        WHERE v.is_available = 1 AND v.is_open = 1
    """
    params = []
    if q:
        sql += " AND (item_name LIKE ? OR description LIKE ? OR restaurant_name LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    if cuisine:
        sql += " AND cuisine = ?"
        params.append(cuisine)
    if restaurant_id:
        sql += " AND restaurant_id = ?"
        params.append(restaurant_id)
    sql += " ORDER BY restaurant_name, category_name, item_name"
    items = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template(
        "menu.html",
        items=items,
        cuisines=cuisines,
        restaurants=restaurants,
        q=q,
        cuisine=cuisine,
        restaurant_id=restaurant_id,
    )


@app.route("/restaurant/<int:restaurant_id>")
def restaurant(restaurant_id):
    conn = get_connection()
    rest = conn.execute(
        "SELECT * FROM restaurants WHERE restaurant_id = ?", (restaurant_id,)
    ).fetchone()
    if not rest:
        conn.close()
        flash("Restaurant not found.", "error")
        return redirect(url_for("home"))
    items = conn.execute(
        """
        SELECT v.*,
               CASE
                   WHEN v.price >= 250 THEN 'Chef special'
                   WHEN v.price >= 150 THEN 'Popular'
                   ELSE 'Value'
               END AS price_tag
        FROM v_public_menu v
        WHERE v.restaurant_id = ? AND v.is_available = 1
        ORDER BY v.category_name, v.item_name
        """,
        (restaurant_id,),
    ).fetchall()
    conn.close()
    grouped = {}
    for item in items:
        grouped.setdefault(item["category_name"], []).append(item)
    return render_template("restaurant.html", restaurant=rest, grouped=grouped)


@app.route("/cart/add", methods=["POST"])
@login_required
def cart_add():
    item_id = request.form.get("item_id", type=int)
    qty = request.form.get("quantity", default=1, type=int)
    if not item_id or qty < 1:
        flash("Choose a dish first.", "error")
        return redirect(url_for("menu"))
    conn = get_connection()
    item = conn.execute(
        "SELECT item_id, restaurant_id, is_available FROM menu_items WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    if not item or not item["is_available"]:
        conn.close()
        flash("That dish is not available.", "error")
        return redirect(url_for("menu"))

    existing = conn.execute(
        """
        SELECT m.restaurant_id
        FROM cart_items c
        JOIN menu_items m ON c.item_id = m.item_id
        WHERE c.user_id = ?
        LIMIT 1
        """,
        (session["user_id"],),
    ).fetchone()
    if existing and existing["restaurant_id"] != item["restaurant_id"]:
        conn.execute("DELETE FROM cart_items WHERE user_id = ?", (session["user_id"],))

    in_cart = conn.execute(
        "SELECT quantity FROM cart_items WHERE user_id = ? AND item_id = ?",
        (session["user_id"], item_id),
    ).fetchone()
    if in_cart:
        conn.execute(
            """
            UPDATE cart_items
            SET quantity = quantity + ?
            WHERE user_id = ? AND item_id = ?
            """,
            (qty, session["user_id"], item_id),
        )
    else:
        conn.execute(
            "INSERT INTO cart_items (user_id, item_id, quantity) VALUES (?, ?, ?)",
            (session["user_id"], item_id, qty),
        )
    conn.commit()
    conn.close()
    flash("Added to bag.", "success")
    return redirect(request.form.get("next") or url_for("cart"))


@app.route("/cart")
@login_required
def cart():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT c.item_id, c.quantity, m.item_name, m.price,
               (c.quantity * m.price) AS line_total,
               r.name AS restaurant_name, r.restaurant_id
        FROM cart_items c
        JOIN menu_items m ON c.item_id = m.item_id
        JOIN restaurants r ON m.restaurant_id = r.restaurant_id
        WHERE c.user_id = ?
        ORDER BY m.item_name
        """,
        (session["user_id"],),
    ).fetchall()
    total = sum(r["line_total"] for r in rows)
    conn.close()
    return render_template("cart.html", rows=rows, total=total)


@app.route("/cart/update", methods=["POST"])
@login_required
def cart_update():
    item_id = request.form.get("item_id", type=int)
    qty = request.form.get("quantity", type=int)
    conn = get_connection()
    if qty is not None and qty <= 0:
        conn.execute(
            "DELETE FROM cart_items WHERE user_id = ? AND item_id = ?",
            (session["user_id"], item_id),
        )
    else:
        conn.execute(
            "UPDATE cart_items SET quantity = ? WHERE user_id = ? AND item_id = ?",
            (qty, session["user_id"], item_id),
        )
    conn.commit()
    conn.close()
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT c.item_id, c.quantity, m.item_name, m.price, m.restaurant_id,
               (c.quantity * m.price) AS line_total
        FROM cart_items c
        JOIN menu_items m ON c.item_id = m.item_id
        WHERE c.user_id = ?
        """,
        (session["user_id"],),
    ).fetchall()
    addresses = conn.execute(
        "SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC",
        (session["user_id"],),
    ).fetchall()

    if not rows:
        conn.close()
        flash("Your bag is empty.", "info")
        return redirect(url_for("menu"))

    total = sum(r["line_total"] for r in rows)
    restaurant_id = rows[0]["restaurant_id"]

    if request.method == "POST":
        address_id = request.form.get("address_id", type=int)
        method = request.form.get("method", "upi")
        if method not in ("card", "upi", "cod"):
            method = "upi"
        addr = conn.execute(
            "SELECT address_id FROM addresses WHERE address_id = ? AND user_id = ?",
            (address_id, session["user_id"]),
        ).fetchone()
        if not addr:
            conn.close()
            flash("Choose a delivery address.", "error")
            return redirect(url_for("checkout"))

        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO orders (customer_id, restaurant_id, address_id, status, total_amount)
                VALUES (?, ?, ?, 'placed', ?)
                """,
                (session["user_id"], restaurant_id, address_id, total),
            )
            order_id = cur.lastrowid
            conn.executemany(
                """
                INSERT INTO order_items (order_id, item_id, quantity, unit_price)
                VALUES (?, ?, ?, ?)
                """,
                [(order_id, r["item_id"], r["quantity"], r["price"]) for r in rows],
            )
            pay_status = "pending" if method == "cod" else "success"
            conn.execute(
                """
                INSERT INTO payments (order_id, amount, method, status)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, total, method, pay_status),
            )
            if method == "cod":
                conn.execute(
                    "UPDATE orders SET status = 'preparing' WHERE order_id = ?",
                    (order_id,),
                )
            conn.execute("DELETE FROM cart_items WHERE user_id = ?", (session["user_id"],))
            conn.execute("COMMIT")
            conn.close()
            flash("Order placed. Track it under My orders.", "success")
            return redirect(url_for("order_detail", order_id=order_id))
        except Exception as exc:
            conn.execute("ROLLBACK")
            conn.close()
            flash(f"Payment could not be completed. Changes were rolled back. ({exc})", "error")
            return redirect(url_for("checkout"))

    conn.close()
    return render_template("checkout.html", rows=rows, total=total, addresses=addresses)


@app.route("/orders")
@login_required
def orders():
    conn = get_connection()
    if session.get("role") == "admin":
        rows = conn.execute(
            "SELECT * FROM v_order_summary ORDER BY order_date DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT v.*
            FROM v_order_summary v
            JOIN orders o ON v.order_id = o.order_id
            WHERE o.customer_id = ?
            ORDER BY v.order_date DESC
            """,
            (session["user_id"],),
        ).fetchall()
    conn.close()
    return render_template("orders.html", rows=rows)


@app.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    conn = get_connection()
    order = conn.execute(
        """
        SELECT o.*, u.full_name, u.phone, r.name AS restaurant_name,
               a.line1, a.city, a.state, a.postal_code
        FROM orders o
        JOIN users u ON o.customer_id = u.user_id
        JOIN restaurants r ON o.restaurant_id = r.restaurant_id
        JOIN addresses a ON o.address_id = a.address_id
        WHERE o.order_id = ?
        """,
        (order_id,),
    ).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect(url_for("orders"))
    if session.get("role") != "admin" and order["customer_id"] != session["user_id"]:
        conn.close()
        flash("You cannot view that order.", "error")
        return redirect(url_for("orders"))

    items = conn.execute(
        """
        SELECT oi.quantity, oi.unit_price, m.item_name,
               (oi.quantity * oi.unit_price) AS line_total
        FROM order_items oi
        JOIN menu_items m ON oi.item_id = m.item_id
        WHERE oi.order_id = ?
        """,
        (order_id,),
    ).fetchall()
    payment = conn.execute(
        "SELECT * FROM payments WHERE order_id = ?", (order_id,)
    ).fetchone()
    delivery = conn.execute(
        """
        SELECT d.*, u.full_name AS partner_name, u.phone AS partner_phone
        FROM deliveries d
        LEFT JOIN users u ON d.partner_id = u.user_id
        WHERE d.order_id = ?
        """,
        (order_id,),
    ).fetchone()
    audit = conn.execute(
        "SELECT * FROM order_audit WHERE order_id = ? ORDER BY logged_at",
        (order_id,),
    ).fetchall()
    conn.close()
    return render_template(
        "order_detail.html",
        order=order,
        items=items,
        payment=payment,
        delivery=delivery,
        audit=audit,
    )


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    conn = get_connection()
    if request.method == "POST":
        line1 = request.form.get("line1", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        postal = request.form.get("postal_code", "").strip()
        if not all([line1, city, state, postal]):
            flash("Enter a complete address.", "error")
        else:
            conn.execute(
                """
                INSERT INTO addresses (user_id, line1, city, state, postal_code, is_default)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (session["user_id"], line1, city, state, postal),
            )
            conn.commit()
            flash("Address saved.", "success")
        conn.close()
        return redirect(url_for("account"))

    addresses = conn.execute(
        "SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC, address_id",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return render_template("account.html", addresses=addresses)


@app.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        order = conn.execute(
            "SELECT customer_id, status FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if not order:
            raise ValueError("missing")
        if session.get("role") != "admin" and order["customer_id"] != session["user_id"]:
            raise ValueError("forbidden")
        if order["status"] in ("delivered", "cancelled", "out_for_delivery"):
            raise ValueError("locked")
        conn.execute(
            "UPDATE orders SET status = 'cancelled' WHERE order_id = ?",
            (order_id,),
        )
        conn.execute(
            "UPDATE payments SET status = 'failed' WHERE order_id = ? AND status = 'pending'",
            (order_id,),
        )
        conn.execute("COMMIT")
        flash("Order cancelled. The status change was committed.", "success")
    except Exception:
        conn.execute("ROLLBACK")
        flash("That order cannot be cancelled. No rows were changed.", "error")
    finally:
        conn.close()
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@login_required
@admin_required
def admin_status(order_id):
    nxt = request.form.get("status", "")
    allowed = ("preparing", "out_for_delivery", "delivered", "cancelled")
    if nxt not in allowed:
        flash("Unknown status.", "error")
        return redirect(url_for("order_detail", order_id=order_id))
    conn = get_connection()
    conn.execute("UPDATE orders SET status = ? WHERE order_id = ?", (nxt, order_id))
    if nxt == "delivered":
        conn.execute(
            "UPDATE deliveries SET status = 'delivered' WHERE order_id = ?",
            (order_id,),
        )
    elif nxt == "out_for_delivery":
        conn.execute(
            "UPDATE deliveries SET status = 'picked_up' WHERE order_id = ?",
            (order_id,),
        )
    conn.commit()
    conn.close()
    flash("Order status updated.", "success")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/admin")
@login_required
@admin_required
def admin():
    conn = get_connection()
    # Practical 12: three reporting queries — aggregates, joins, subquery
    kpis = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM orders) AS orders_total,
            (SELECT COUNT(*) FROM users WHERE role = 'customer') AS customers,
            (SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status <> 'cancelled') AS revenue,
            (SELECT COUNT(*) FROM menu_items WHERE is_available = 1) AS dishes
        """
    ).fetchone()
    sales = conn.execute(
        "SELECT * FROM v_restaurant_sales ORDER BY revenue DESC"
    ).fetchall()
    top_dishes = conn.execute(
        """
        SELECT m.item_name, r.name AS restaurant_name, SUM(oi.quantity) AS sold,
               SUM(oi.quantity * oi.unit_price) AS sales
        FROM order_items oi
        JOIN menu_items m ON oi.item_id = m.item_id
        JOIN restaurants r ON m.restaurant_id = r.restaurant_id
        GROUP BY m.item_id, m.item_name, r.name
        HAVING SUM(oi.quantity) >= 1
        ORDER BY sold DESC
        LIMIT 8
        """
    ).fetchall()
    high_value = conn.execute(
        """
        SELECT full_name, email
        FROM users
        WHERE user_id IN (
            SELECT customer_id
            FROM orders
            GROUP BY customer_id
            HAVING SUM(total_amount) > (
                SELECT AVG(total_amount) FROM orders
            )
        )
        AND role = 'customer'
        """
    ).fetchall()
    conn.close()
    return render_template(
        "admin.html",
        kpis=kpis,
        sales=sales,
        top_dishes=top_dishes,
        high_value=high_value,
    )


if __name__ == "__main__":
    if not DB_PATH.exists():
        init_db()
    app.run(debug=True, port=5000)
