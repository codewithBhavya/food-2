-- FoodEase schema
-- DBMS syllabus (102040305): DDL, constraints, ER-to-relational mapping,
-- 3NF design, views, indexes, triggers, transaction-ready tables.

PRAGMA foreign_keys = ON;

-- ---------- DROP (fresh install) ----------
DROP VIEW IF EXISTS v_public_menu;
DROP VIEW IF EXISTS v_order_summary;
DROP VIEW IF EXISTS v_restaurant_sales;
DROP TABLE IF EXISTS order_audit;
DROP TABLE IF EXISTS deliveries;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS cart_items;
DROP TABLE IF EXISTS menu_items;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS restaurants;
DROP TABLE IF EXISTS addresses;
DROP TABLE IF EXISTS users;

-- ---------- CORE ENTITIES ----------
CREATE TABLE users (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      VARCHAR(100) NOT NULL,
    email          VARCHAR(120) NOT NULL UNIQUE,
    phone          VARCHAR(15)  NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    role           VARCHAR(20)  NOT NULL DEFAULT 'customer',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_user_role CHECK (role IN ('customer', 'admin', 'delivery')),
    CONSTRAINT chk_email_fmt CHECK (email LIKE '%@%.%')
);

CREATE TABLE addresses (
    address_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    line1       VARCHAR(255) NOT NULL,
    city        VARCHAR(50)  NOT NULL,
    state       VARCHAR(50)  NOT NULL,
    postal_code VARCHAR(10)  NOT NULL,
    is_default  INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT fk_addr_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT chk_default CHECK (is_default IN (0, 1))
);

CREATE TABLE restaurants (
    restaurant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name          VARCHAR(120) NOT NULL,
    cuisine       VARCHAR(50)  NOT NULL,
    city          VARCHAR(50)  NOT NULL,
    description   VARCHAR(500),
    is_open       INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT chk_rest_open CHECK (is_open IN (0, 1)),
    CONSTRAINT uq_rest_name UNIQUE (name)
);

CREATE TABLE categories (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE menu_items (
    item_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id  INTEGER NOT NULL,
    category_id    INTEGER NOT NULL,
    item_name      VARCHAR(120) NOT NULL,
    description    VARCHAR(500),
    price          INTEGER NOT NULL,
    is_available   INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT fk_item_rest FOREIGN KEY (restaurant_id) REFERENCES restaurants(restaurant_id),
    CONSTRAINT fk_item_cat  FOREIGN KEY (category_id) REFERENCES categories(category_id),
    CONSTRAINT chk_price    CHECK (price > 0),
    CONSTRAINT chk_avail    CHECK (is_available IN (0, 1))
);

CREATE TABLE cart_items (
    user_id   INTEGER NOT NULL,
    item_id   INTEGER NOT NULL,
    quantity  INTEGER NOT NULL,
    PRIMARY KEY (user_id, item_id),
    CONSTRAINT fk_cart_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_cart_item FOREIGN KEY (item_id) REFERENCES menu_items(item_id),
    CONSTRAINT chk_qty CHECK (quantity > 0)
);

CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   INTEGER NOT NULL,
    restaurant_id INTEGER NOT NULL,
    address_id    INTEGER NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'placed',
    order_date    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount  INTEGER NOT NULL,
    CONSTRAINT fk_ord_cust FOREIGN KEY (customer_id) REFERENCES users(user_id),
    CONSTRAINT fk_ord_rest FOREIGN KEY (restaurant_id) REFERENCES restaurants(restaurant_id),
    CONSTRAINT fk_ord_addr FOREIGN KEY (address_id) REFERENCES addresses(address_id),
    CONSTRAINT chk_ord_status CHECK (status IN ('placed', 'paid', 'preparing', 'out_for_delivery', 'delivered', 'cancelled')),
    CONSTRAINT chk_ord_total CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL,
    item_id    INTEGER NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    PRIMARY KEY (order_id, item_id),
    CONSTRAINT fk_oi_ord  FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    CONSTRAINT fk_oi_item FOREIGN KEY (item_id) REFERENCES menu_items(item_id),
    CONSTRAINT chk_oi_qty CHECK (quantity > 0),
    CONSTRAINT chk_oi_price CHECK (unit_price > 0)
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL UNIQUE,
    amount     INTEGER NOT NULL,
    method     VARCHAR(20) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    paid_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pay_ord FOREIGN KEY (order_id) REFERENCES orders(order_id),
    CONSTRAINT chk_pay_amt CHECK (amount > 0),
    CONSTRAINT chk_pay_method CHECK (method IN ('card', 'upi', 'cod')),
    CONSTRAINT chk_pay_status CHECK (status IN ('pending', 'success', 'failed'))
);

CREATE TABLE deliveries (
    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL UNIQUE,
    partner_id  INTEGER,
    status      VARCHAR(20) NOT NULL DEFAULT 'assigned',
    CONSTRAINT fk_del_ord FOREIGN KEY (order_id) REFERENCES orders(order_id),
    CONSTRAINT fk_del_partner FOREIGN KEY (partner_id) REFERENCES users(user_id),
    CONSTRAINT chk_del_status CHECK (status IN ('assigned', 'picked_up', 'delivered'))
);

CREATE TABLE order_audit (
    audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    action     VARCHAR(80) NOT NULL,
    logged_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_ord FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- Indexing (Unit 6: query processing / indexing)
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_menu_rest ON menu_items(restaurant_id);
CREATE INDEX idx_menu_cat ON menu_items(category_id);
CREATE INDEX idx_orders_cust ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);

-- ---------- VIEWS (Unit 4: views; Practical 9: hide sensitive columns) ----------
CREATE VIEW v_public_menu AS
SELECT
    m.item_id,
    m.item_name,
    m.description,
    m.price,
    m.is_available,
    c.category_name,
    r.restaurant_id,
    r.name AS restaurant_name,
    r.cuisine,
    r.city,
    r.is_open
FROM menu_items m
JOIN categories c ON m.category_id = c.category_id
JOIN restaurants r ON m.restaurant_id = r.restaurant_id;

CREATE VIEW v_order_summary AS
SELECT
    o.order_id,
    u.full_name AS customer_name,
    u.email AS customer_email,
    r.name AS restaurant_name,
    o.status,
    o.order_date,
    o.total_amount,
    (SELECT SUM(oi.quantity) FROM order_items oi WHERE oi.order_id = o.order_id) AS item_count
FROM orders o
JOIN users u ON o.customer_id = u.user_id
JOIN restaurants r ON o.restaurant_id = r.restaurant_id;

CREATE VIEW v_restaurant_sales AS
SELECT
    r.restaurant_id,
    r.name AS restaurant_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS revenue
FROM restaurants r
LEFT JOIN orders o ON r.restaurant_id = o.restaurant_id
    AND o.status <> 'cancelled'
GROUP BY r.restaurant_id, r.name;

-- ---------- TRIGGERS (Unit 4 / Practical 11) ----------
CREATE TRIGGER trg_order_insert_audit
AFTER INSERT ON orders
BEGIN
    INSERT INTO order_audit (order_id, action)
    VALUES (NEW.order_id, 'ORDER_PLACED');
END;

CREATE TRIGGER trg_order_status_audit
AFTER UPDATE OF status ON orders
WHEN OLD.status <> NEW.status
BEGIN
    INSERT INTO order_audit (order_id, action)
    VALUES (NEW.order_id, 'STATUS:' || OLD.status || '->' || NEW.status);
END;

CREATE TRIGGER trg_payment_success
AFTER INSERT ON payments
WHEN NEW.status = 'success'
BEGIN
    UPDATE orders SET status = 'paid' WHERE order_id = NEW.order_id;
END;

CREATE TRIGGER trg_assign_delivery
AFTER UPDATE OF status ON orders
WHEN NEW.status IN ('paid', 'preparing')
 AND NOT EXISTS (SELECT 1 FROM deliveries WHERE order_id = NEW.order_id)
BEGIN
    INSERT INTO deliveries (order_id, partner_id, status)
    SELECT NEW.order_id, u.user_id, 'assigned'
    FROM users u
    WHERE u.role = 'delivery'
    ORDER BY u.user_id
    LIMIT 1;
END;
