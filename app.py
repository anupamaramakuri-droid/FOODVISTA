from flask import Flask, render_template, request, redirect, session
import sqlite3
import csv
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "foodvista_secret_key"


# ==================================================
# DATABASE
# ==================================================

def init_db():

    conn = sqlite3.connect("database.db")

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ==================================================
# READ CSV
# ==================================================

def read_csv_file(filename):

    records = []

    if not os.path.exists(filename):
        return records

    with open(
        filename,
        "r",
        encoding="utf-8-sig",
        errors="ignore"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            records.append(row)

    return records


# ==================================================
# LOAD DATASETS
# ==================================================

swiggy_data = read_csv_file(
    "swiggy_foodvista_merged.csv"
)

zomato_data = read_csv_file(
    "zomato_menu_foodvista_updated.csv"
)
)


# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect("/login")

    return render_template(
        "index.html",
        logged_in=True,
        user_name=session.get("user_name", "")
    
    )


# ==================================================
# COMPARE PAGE
# ==================================================

@app.route("/compare")
def compare_page():

    return render_template("compare.html")


# ==================================================
# LOGIN
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip()

        password = request.form["password"]

        conn = sqlite3.connect("database.db")

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        )

        user = cursor.fetchone()

        if user:

            stored_password = user[3]

            password_valid = False

            # ------------------------------------------
            # CHECK HASHED PASSWORD
            # ------------------------------------------

            try:

                password_valid = check_password_hash(
                    stored_password,
                    password
                )

            except ValueError:

                password_valid = False


            # ------------------------------------------
            # OLD PASSWORD SUPPORT
            # ------------------------------------------

            if not password_valid and stored_password == password:

                password_valid = True

                new_password = generate_password_hash(
                    password
                )

                cursor.execute(
                    """
                    UPDATE users
                    SET password = ?
                    WHERE id = ?
                    """,
                    (
                        new_password,
                        user[0]
                    )
                )

                conn.commit()


            if password_valid:

                session["user_id"] = user[0]

                session["user_name"] = user[1]

                session["user_email"] = user[2]

                conn.close()

                return redirect("/")


        conn.close()

        return "Invalid email or password."

    return render_template("login.html")


# ==================================================
# REGISTER
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()

        email = request.form["email"].strip()

        password = request.form["password"]


        hashed_password = generate_password_hash(
            password
        )


        conn = sqlite3.connect("database.db")

        cursor = conn.cursor()

        try:

            cursor.execute(
                """
                INSERT INTO users
                (name, email, password)
                VALUES (?, ?, ?)
                """,
                (
                    name,
                    email,
                    hashed_password
                )
            )

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            return "Email already registered."

        conn.close()

        return redirect("/login")

    return render_template("register.html")


# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ==================================================
# SWIGGY RECOMMENDATION
# ==================================================

def choose_swiggy_recommendation(records):

    if not records:

        return {}


    def rating_value(row):

        value = str(
            row.get("Rating", "")
        ).strip()

        try:

            return float(value)

        except:

            return 0


    def rating_count_value(row):

        value = str(
            row.get("Rating Count", "")
        ).strip()

        value = value.replace(",", "")

        try:

            return int(float(value))

        except:

            return 0


    records = sorted(
        records,
        key=lambda row: (
            rating_value(row),
            rating_count_value(row)
        ),
        reverse=True
    )

    return records[0]


# ==================================================
# SEARCH API
# ==================================================

@app.route("/api/search")
def search():

    query = request.args.get(
        "q",
        ""
    ).strip().lower()


    if query == "":

        return {
            "swiggy": [],
            "zomato": [],
            "total_swiggy": 0,
            "total_zomato": 0,
            "recommendation": None
        }


    swiggy_food_matches = []
    swiggy_restaurant_matches = []
    swiggy_cuisine_matches = []

    zomato_food_matches = []
    zomato_restaurant_matches = []
    zomato_category_matches = []


    # ==================================================
    # SWIGGY
    # ==================================================

    for row in swiggy_data:

        restaurant = str(
            row.get("Restaurant", "")
        ).strip()

        food_item = str(
            row.get("Food Item", "")
        ).strip()

        cuisine = str(
            row.get("Cuisine", "")
        ).strip()


        if query in food_item.lower():

            swiggy_food_matches.append(row)

        elif query in restaurant.lower():

            swiggy_restaurant_matches.append(row)

        elif query in cuisine.lower():

            swiggy_cuisine_matches.append(row)


    # ==================================================
    # ZOMATO
    # ==================================================

    for row in zomato_data:

        restaurant = str(
            row.get("Restaurant", "")
        ).strip()

        food_item = str(
            row.get("Food Item", "")
        ).strip()

        category = str(
            row.get("Category", "")
        ).strip()


        if query in food_item.lower():

            zomato_food_matches.append(row)

        elif query in restaurant.lower():

            zomato_restaurant_matches.append(row)

        elif query in category.lower():

            zomato_category_matches.append(row)


    # ==================================================
    # COMBINE RESULTS
    # ==================================================

    swiggy_results = (
        swiggy_food_matches
        + swiggy_restaurant_matches
        + swiggy_cuisine_matches
    )

    zomato_results = (
        zomato_food_matches
        + zomato_restaurant_matches
        + zomato_category_matches
    )


    swiggy_results = swiggy_results[:100]

    zomato_results = zomato_results[:100]


    # ==================================================
    # RECOMMENDATION
    # ==================================================

    recommendation = None


    if swiggy_food_matches:

        best = choose_swiggy_recommendation(
            swiggy_food_matches
        )

        recommendation = {

            "platform": "Swiggy",

            "restaurant": best.get(
                "Restaurant",
                ""
            ),

            "food": best.get(
                "Food Item",
                ""
            ),

            "cuisine": best.get(
                "Cuisine",
                ""
            ),

            "price": best.get(
                "Price",
                ""
            ),

            "rating": best.get(
                "Rating",
                ""
            ),

            "rating_count": best.get(
                "Rating Count",
                ""
            ),

            "url": best.get(
                "View on Swiggy",
                ""
            )
        }


    elif zomato_food_matches:

        best = zomato_food_matches[0]

        recommendation = {

            "platform": "Zomato",

            "restaurant": best.get(
                "Restaurant",
                ""
            ),

            "food": best.get(
                "Food Item",
                ""
            ),

            "cuisine": best.get(
                "Category",
                ""
            ),

            "price": best.get(
                "Price",
                ""
            ),

            "rating": "",

            "rating_count": "",

            "url": best.get(
                "View on Zomato",
                ""
            )
        }


    return {

        "swiggy": swiggy_results,

        "zomato": zomato_results,

        "total_swiggy": len(
            swiggy_results
        ),

        "total_zomato": len(
            zomato_results
        ),

        "recommendation": recommendation
    }


# ==================================================
# COMPARISON API
# ==================================================

@app.route("/api/compare")
def compare():

    query = request.args.get(
        "q",
        ""
    ).strip().lower()


    if query == "":

        return {
            "comparison": []
        }


    swiggy_matches = []

    zomato_matches = []


    # ==================================================
    # FIND SWIGGY FOOD ITEMS
    # ==================================================

    for row in swiggy_data:

        food = str(
            row.get("Food Item", "")
        ).strip()


        if query in food.lower():

            swiggy_matches.append(row)


    # ==================================================
    # FIND ZOMATO FOOD ITEMS
    # ==================================================

    for row in zomato_data:

        food = str(
            row.get("Food Item", "")
        ).strip()


        if query in food.lower():

            zomato_matches.append(row)


    # ==================================================
    # CREATE FOOD MAPS
    # ==================================================

    swiggy_map = {}

    zomato_map = {}


    for row in swiggy_matches:

        food = str(
            row.get("Food Item", "")
        ).strip()

        key = food.lower()


        if key not in swiggy_map:

            swiggy_map[key] = row


    for row in zomato_matches:

        food = str(
            row.get("Food Item", "")
        ).strip()

        key = food.lower()


        if key not in zomato_map:

            zomato_map[key] = row


    # ==================================================
    # COMMON FOOD ITEMS
    # ==================================================

    common_foods = (
        set(swiggy_map.keys())
        &
        set(zomato_map.keys())
    )


    comparison = []


    for key in sorted(common_foods):

        swiggy_row = swiggy_map[key]

        zomato_row = zomato_map[key]


        comparison.append({

            "food_item": swiggy_row.get(
                "Food Item",
                ""
            ),

            "swiggy": {

                "restaurant":
                    swiggy_row.get(
                        "Restaurant",
                        ""
                    ),

                "price":
                    swiggy_row.get(
                        "Price",
                        ""
                    ),

                "rating":
                    swiggy_row.get(
                        "Rating",
                        ""
                    ),

                "rating_count":
                    swiggy_row.get(
                        "Rating Count",
                        ""
                    ),

                "url":
                    swiggy_row.get(
                        "View on Swiggy",
                        ""
                    )
            },

            "zomato": {

                "restaurant":
                    zomato_row.get(
                        "Restaurant",
                        ""
                    ),

                "price":
                    zomato_row.get(
                        "Price",
                        ""
                    ),

                "rating": "",

                "rating_count": "",

                "url":
                    zomato_row.get(
                        "View on Zomato",
                        ""
                    )
            }
        })


    return {

        "comparison": comparison[:50]

    }


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    app.run(debug=True)
