
from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
import csv
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FOODVISTA_SECRET_KEY",
    "change-this-foodvista-secret-key"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
DATA_DIR = os.path.join(BASE_DIR, "multicity_data")

ALLOWED_CITIES = [
    "Visakhapatnam", "Hyderabad", "Chennai", "Delhi", "Mumbai"
]


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)


def read_csv_file(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8-sig",
              errors="replace", newline="") as file:
        return [
            {
                (key or "").strip(): (value or "").strip()
                for key, value in row.items()
            }
            for row in csv.DictReader(file)
        ]


def first_value(row, *keys):
    for key in keys:
        value = row.get(key, "")
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalise_city(value):
    aliases = {
        "vizag": "Visakhapatnam",
        "visakhapatnam": "Visakhapatnam",
        "hyderabad": "Hyderabad",
        "chennai": "Chennai",
        "delhi": "Delhi",
        "new delhi": "Delhi",
        "mumbai": "Mumbai"
    }
    return aliases.get((value or "").strip().lower(), "")


def normalise_record(row, platform):
    city = normalise_city(first_value(row, "city", "City"))
    restaurant = first_value(
        row, "restaurant_name", "Restaurant", "restaurant", "rest_names"
    )

    if not city or not restaurant:
        return None

    price = first_value(
        row, "price_inr", "Price", "average_price_raw",
        "price for two", "price for one"
    )

    return {
        "restaurant": restaurant,
        "city": city,
        "cuisine": first_value(
            row, "cuisines", "Cuisine", "Category", "rest_crusine"
        ) or "Not Available",
        "rating": first_value(
            row, "rating", "Rating", "rest_ratings"
        ) or "Not Available",
        "rating_count": first_value(row, "rating_count", "Rating Count")
            or "Not Available",
        "price": price or "Not Available",
        "area": first_value(row, "area", "Area", "address", "Address")
            or "Not Available",
        "platform": platform,
        "url": first_value(
            row, "url", "URL", "View on Swiggy",
            "View on Zomato", "rest_urls", "restaurant_link"
        ),
        "pure_veg": first_value(row, "pure_veg") or "Not Available",
        "delivery_time": first_value(row, "average_delivery_time")
            or "Not Available",
        "offers_count": first_value(row, "offers_count")
            or "Not Available",
        "offer_name": first_value(row, "offer_name")
            or "Not Available",
        "safety_measure": first_value(row, "safety_measure")
            or "Not Available",
        "restaurant_key": (
            first_value(row, "restaurant_key") or restaurant.lower()
        )
    }


def load_platform_data(platform):
    filename = (
        "swiggy_multicity_cleaned.csv"
        if platform == "Swiggy"
        else "zomato_multicity_cleaned.csv"
    )
    path = os.path.join(DATA_DIR, filename)
    rows = read_csv_file(path)

    records = [
        normalise_record(row, platform) for row in rows
    ]
    records = [row for row in records if row]

    # Fall back to the original Vizag datasets only if the new file
    # contains no usable records.
    if records:
        return records

    old_filename = (
        "swiggy_foodvista_merged.csv"
        if platform == "Swiggy"
        else "zomato_menu_foodvista_clean.csv"
    )

    old_rows = read_csv_file(os.path.join(BASE_DIR, old_filename))
    fallback = []

    for row in old_rows:
        restaurant = first_value(row, "Restaurant")
        if not restaurant:
            continue

        fallback.append({
            "restaurant": restaurant,
            "city": "Visakhapatnam",
            "cuisine": first_value(row, "Cuisine", "Category")
                or "Not Available",
            "rating": first_value(row, "Rating") or "Not Available",
            "rating_count": first_value(row, "Rating Count")
                or "Not Available",
            "price": first_value(row, "Price") or "Not Available",
            "area": "Not Available",
            "platform": platform,
            "url": first_value(
                row, "View on Swiggy", "View on Zomato"
            ),
            "pure_veg": "Not Available",
            "delivery_time": "Not Available",
            "offers_count": "Not Available",
            "offer_name": "Not Available",
            "safety_measure": "Not Available",
            "restaurant_key": restaurant.lower()
        })

    return fallback


init_db()
swiggy_data = load_platform_data("Swiggy")
zomato_data = load_platform_data("Zomato")


def current_city():
    city = request.args.get("city", "Visakhapatnam").strip()
    if city.lower() == "all":
        return "All"
    return normalise_city(city) or "Visakhapatnam"


def rating_number(value):
    try:
        return float(str(value or "").strip().replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def filter_records(records, query="", city="All"):
    query = (query or "").strip().lower()
    results = []

    for row in records:
        if city != "All" and row["city"] != city:
            continue

        searchable = " ".join([
            row.get("restaurant", ""),
            row.get("cuisine", ""),
            row.get("area", ""),
            row.get("city", "")
        ]).lower()

        if query and query not in searchable:
            continue

        results.append(row)

    return results


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")

    return render_template(
        "index.html",
        logged_in=True,
        user_name=session.get("user_name", ""),
        cities=ALLOWED_CITIES
    )


@app.route("/compare")
def compare_page():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("compare.html", cities=ALLOWED_CITIES)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with sqlite3.connect(DB_PATH) as conn:
            user = conn.execute(
                """SELECT id, name, email, password
                   FROM users WHERE lower(email) = ?""",
                (email,)
            ).fetchone()

            valid = False
            if user:
                try:
                    valid = check_password_hash(user[3], password)
                except (ValueError, TypeError):
                    valid = False

                # Upgrade legacy plain-text passwords.
                if not valid and user[3] == password:
                    valid = True
                    conn.execute(
                        "UPDATE users SET password = ? WHERE id = ?",
                        (generate_password_hash(password), user[0])
                    )

        if valid and user:
            session["user_id"] = user[0]
            session["user_name"] = user[1]
            session["user_email"] = user[2]
            return redirect("/")

        return "Invalid email or password.", 401

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return "Please fill in all fields.", 400

        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """INSERT INTO users (name, email, password)
                       VALUES (?, ?, ?)""",
                    (name, email, generate_password_hash(password))
                )
        except sqlite3.IntegrityError:
            return "Email already registered.", 409

        return redirect("/login")

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/cities")
def api_cities():
    coverage = {
        city: {
            "swiggy": sum(r["city"] == city for r in swiggy_data),
            "zomato": sum(r["city"] == city for r in zomato_data)
        }
        for city in ALLOWED_CITIES
    }
    return jsonify({"cities": ALLOWED_CITIES, "coverage": coverage})


@app.route("/api/search")
def search():
    query = request.args.get("q", "").strip()
    city = current_city()

    swiggy = filter_records(swiggy_data, query, city)
    zomato = filter_records(zomato_data, query, city)

    swiggy.sort(key=lambda r: rating_number(r["rating"]), reverse=True)
    zomato.sort(key=lambda r: rating_number(r["rating"]), reverse=True)

    # Recommend actual records with a valid rating.
    # Search terms and city filters are applied before ranking.
    candidates = [
        row for row in swiggy + zomato
        if rating_number(row.get("rating")) > 0
    ]
    candidates.sort(
        key=lambda r: rating_number(r["rating"]),
        reverse=True
    )

    recommendations = []
    seen = set()

    for row in candidates:
        key = (
            row["restaurant"].strip().lower(),
            row["city"].strip().lower(),
            row["platform"].strip().lower()
        )
        if key not in seen:
            seen.add(key)
            recommendations.append(row)
        if len(recommendations) == 6:
            break

    return jsonify({
        "city": city,
        "swiggy": swiggy[:100],
        "zomato": zomato[:100],
        "total_swiggy": len(swiggy),
        "total_zomato": len(zomato),
        "recommendations": recommendations[:1],
        "data_type": "restaurant-level"
    })


@app.route("/api/compare")
def compare():
    query = request.args.get("q", "").strip()
    city = current_city()

    swiggy = filter_records(swiggy_data, query, city)
    zomato = filter_records(zomato_data, query, city)

    swiggy_map = {
        r["restaurant_key"].lower(): r for r in swiggy
    }
    zomato_map = {
        r["restaurant_key"].lower(): r for r in zomato
    }

    common = sorted(set(swiggy_map) & set(zomato_map))
    comparisons = [
        {
            "restaurant": swiggy_map[key]["restaurant"],
            "city": city,
            "swiggy": swiggy_map[key],
            "zomato": zomato_map[key]
        }
        for key in common
    ]

    return jsonify({
        "city": city,
        "comparison": comparisons[:100],
        "data_type": "restaurant-level"
    })


if __name__ == "__main__":
    app.run(debug=True)
