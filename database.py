import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "foodease.db"
SCHEMA_PATH = ROOT / "schema.sql"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn):
    customer_hash = generate_password_hash("demo123")
    admin_hash = generate_password_hash("admin123")
    rider_hash = generate_password_hash("rider123")

    conn.executemany(
        """
        INSERT INTO users (full_name, email, phone, password_hash, role)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("Aarav Shah", "demo@foodease.com", "9876500001", customer_hash, "customer"),
            ("FoodEase Admin", "admin@foodease.com", "9876500002", admin_hash, "admin"),
            ("Kiran Rider", "rider@foodease.com", "9876500003", rider_hash, "delivery"),
            ("Meera Patel", "meera@foodease.com", "9876500004", generate_password_hash("meera123"), "customer"),
        ],
    )

    conn.execute(
        """
        INSERT INTO addresses (user_id, line1, city, state, postal_code, is_default)
        VALUES (1, '12 Riverfront Road, Navrangpura', 'Ahmedabad', 'Gujarat', '380009', 1),
               (4, '44 CG Road, Ellisbridge', 'Ahmedabad', 'Gujarat', '380006', 1)
        """
    )

    conn.executemany(
        """
        INSERT INTO restaurants (name, cuisine, city, description, is_open)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("Spice Route Kitchen", "North Indian", "Ahmedabad", "Tandoor grills, dals, and weekday thalis.", 1),
            ("Coastal Bowl", "South Indian", "Ahmedabad", "Dosas, filter coffee, and coconut curries.", 1),
            ("Noodle House", "Chinese", "Ahmedabad", "Wok-tossed noodles, dumplings, and soups.", 1),
            ("Sweet Crumb", "Desserts", "Ahmedabad", "Cakes, kulfi, and late-night sweets.", 1),
        ],
    )

    conn.executemany(
        "INSERT INTO categories (category_name) VALUES (?)",
        [("Starters",), ("Mains",), ("Breads & Rice",), ("Beverages",), ("Desserts",)],
    )

    items = [
        (1, 1, "Paneer Tikka", "Charred cottage cheese with mint chutney.", 240),
        (1, 1, "Veg Seekh Kebab", "Spiced vegetable kebabs off the grill.", 190),
        (1, 2, "Butter Chicken", "Tomato-butter gravy with tender chicken.", 320),
        (1, 2, "Dal Makhani", "Slow-cooked black lentils finished with cream.", 210),
        (1, 2, "Paneer Butter Masala", "Cottage cheese in a rich tomato gravy.", 260),
        (1, 3, "Garlic Naan", "Tandoor bread brushed with garlic butter.", 50),
        (1, 3, "Jeera Rice", "Basmati rice tempered with cumin.", 120),
        (1, 4, "Masala Chaas", "Spiced buttermilk.", 40),
        (2, 1, "Medu Vada", "Crisp lentil doughnuts with sambar.", 90),
        (2, 2, "Masala Dosa", "Crisp rice crepe with potato masala.", 140),
        (2, 2, "Idli Sambar", "Steamed rice cakes with lentil stew.", 110),
        (2, 2, "Veg Biryani", "Layered basmati with vegetables and spices.", 220),
        (2, 4, "Filter Coffee", "South Indian decoction with milk.", 60),
        (3, 1, "Veg Spring Rolls", "Crisp rolls with sweet chilli dip.", 150),
        (3, 2, "Hakka Noodles", "Wok-tossed noodles with mixed vegetables.", 180),
        (3, 2, "Chilli Paneer", "Indo-Chinese paneer in a spicy sauce.", 230),
        (3, 2, "Manchurian Bowl", "Fried vegetable balls in garlic gravy.", 200),
        (3, 4, "Jasmine Tea", "Light floral tea.", 70),
        (4, 5, "Gulab Jamun", "Warm milk dumplings in rose syrup.", 90),
        (4, 5, "Mango Kulfi", "Dense mango ice cream on a stick.", 80),
        (4, 5, "Chocolate Lava Cake", "Warm cake with a molten centre.", 160),
        (4, 4, "Cold Coffee", "Iced coffee blended with ice cream.", 130),
    ]
    conn.executemany(
        """
        INSERT INTO menu_items (restaurant_id, category_id, item_name, description, price, is_available)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        items,
    )
