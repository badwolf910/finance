import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT symbol, shares FROM portfolios WHERE user_id = :user_id ORDER BY symbol DESC",
                    user_id = session["user_id"])

    if not stocks:
        return render_template("index.html", message = "Portfolio is empty.")

    total = 0

    for stock in stocks:
        name = price = lookup(stock["symbol"])["name"]
        stock.update({ "name": name })
        price = lookup(stock["symbol"])["price"]
        stock.update({ "price": usd(price) })
        value = price * stock["shares"]
        stock.update({ "value": usd(value) })
        total = total + value

    balance = db.execute("SELECT cash FROM users WHERE id = :user_id",
                    user_id = session["user_id"])[0]["cash"]

    total = total + balance

    return render_template("index.html", stocks = stocks, balance = usd(balance), value = usd(total))



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        input_symbol = request.form.get("symbol")
        input_shares = request.form.get("shares")

        if not lookup(input_symbol):
            return apology("stock not found", 403)

        elif int(input_shares) <= 0:
            return apology("number of shares must be a positive integer", 403)

        user_balance = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id = session["user_id"])[0]["cash"]

        total_price = lookup(input_symbol)["price"] * int(input_shares);

        if total_price > user_balance:
            return apology("insufficient funds", 403)

        db.execute("INSERT INTO transactions (user_id, type, symbol, shares, price) VALUES (:user_id, :transaction_type, :symbol, :shares, :price)",
            user_id = session["user_id"],
            transaction_type = "purchase",
            symbol = input_symbol,
            shares = int(input_shares),
            price = format(total_price, '.2f'))

        user_balance = user_balance - total_price

        db.execute("UPDATE users SET cash = :balance WHERE id = :user_id",
            user_id = session["user_id"],
            balance = user_balance)

        portfolio = db.execute("SELECT shares FROM portfolios WHERE user_id = :user_id AND symbol = :symbol",
                        user_id = session["user_id"],
                        symbol = input_symbol)

        if len(portfolio) == 1:

            shares = portfolio[0]["shares"] + int(input_shares)

            db.execute("UPDATE portfolios SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol",
                user_id = session["user_id"],
                symbol = input_symbol,
                shares = shares)

        else:
            # Query database to insert newly purchased shares info into portfolios
            db.execute("INSERT INTO portfolios (user_id, symbol, shares) VALUES (:user_id, :symbol, :shares)",
                user_id = session["user_id"],
                symbol = input_symbol,
                shares = int(input_shares))

        name = lookup(input_symbol)["name"]

        flash(f"Purchased {input_shares} of {name}")

        # Redirect user to homepage
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT date, type, symbol, shares, price FROM transactions WHERE user_id = :user_id ORDER BY date DESC",
                        user_id = session["user_id"])

    return render_template("history.html", transactions = transactions)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        input_symbol = request.form.get("symbol")

        if not input_symbol:
            return apology("must provide symbol", 403)

        elif not lookup(input_symbol):
            return apology("stock not found", 403)

        quote = lookup(input_symbol)

        quote["price"] = usd(quote["price"])

        return render_template("quoted.html", quote = quote)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        input_username = request.form.get("username")
        input_password = request.form.get("password")
        input_confirmation = request.form.get("confirmation")

        if not input_username:
            return apology("must provide username", 403)

        elif not input_password:
            return apology("must provide password", 403)

        elif not input_confirmation:
            return apology("must provide password confirmation", 418)

        elif not input_password == input_confirmation:
            return apology("passwords must match", 418)

        username = db.execute("SELECT username FROM users WHERE username = :username",
                          username = input_username)

        if len(username) == 1:
            return apology("sorry, username is already taken", 403)

        else:
            new_user = db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                            username = input_username,
                            password = generate_password_hash(input_password, method="pbkdf2:sha256", salt_length=8))

            if new_user:
                session["user_id"] = new_user

          
            flash(f"Registered as {input_username}")

           
            return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        input_symbol = request.form.get("symbol")
        input_shares = request.form.get("shares")

        if not input_symbol:
            return apology("must provide symbol", 403)

        elif int(input_shares) <= 0:
            return apology("number of shares must be a positive integer", 403)

        stocks = db.execute("SELECT shares FROM portfolios WHERE user_id = :user_id AND symbol = :symbol",
                        user_id = session["user_id"],
                        symbol = input_symbol)
        if len(stocks) != 1 or stocks[0]["shares"] < int(input_shares):
            return apology("not enough shares", 403)

        price = lookup(input_symbol)["price"] * int(input_shares)

        db.execute("INSERT INTO transactions (user_id, type, symbol, shares, price) VALUES (:user_id, :transaction_type, :symbol, :shares, :price)",
            user_id = session["user_id"],
            transaction_type = "sell",
            symbol = input_symbol,
            shares = int(input_shares),
            price = format(price,".2f"))

        balance = db.execute("SELECT cash FROM users WHERE id = :user_id",
                        user_id = session["user_id"])[0]["cash"]

        balance = balance + price

        db.execute("UPDATE users SET cash = :balance WHERE id = :user_id",
            user_id = session["user_id"],
            balance = balance)

        shares = stocks[0]["shares"] - int(input_shares)

        db.execute("UPDATE portfolios SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol",
            user_id = session["user_id"],
            symbol = input_symbol,
            shares = shares)

        name = lookup(input_symbol)["name"]

        flash(f"Sold {input_shares} of {name}")

        return redirect("/")

    else:
        stocks = db.execute(
            "SELECT symbol FROM portfolios WHERE user_id =:user_id ORDER BY symbol ASC",
                        user_id = session["user_id"])

        return render_template("sell.html", stocks = stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
