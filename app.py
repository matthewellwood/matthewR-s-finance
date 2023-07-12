import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET"])
@login_required
def index():
    """Show portfolio of stocks"""
    if request.method == "GET":
        # Get list of symbols that we have shares of
        db.execute("delete from current_price;")
        symbol = db.execute("SELECT symbol FROM stock GROUP BY symbol;")
        # Lookup current price of those shares
        for row in symbol:
            get = row["symbol"]
            current = lookup(get)
            # set the database with the current price
            db.execute(
                "INSERT INTO current_price (symbol, current) values (?,?);",
                current["symbol"],
                current["price"],
            )
        # get total list of everything
        set_up_stock = db.execute(
            "SELECT history.symbol,current,sum(shares) AS [total_shares] FROM history JOIN current_price ON history.symbol = lower(current_price.symbol) WHERE user_id = (?) GROUP BY history.symbol;",
            session["user_id"],
        )
        for row in set_up_stock:
            price = row["current"]
            symbol = row["symbol"]
            Quant = row["total_shares"]
            Amount = Quant * price
            db.execute(
                "UPDATE stock SET amount = (?), Shares_tot = (?) WHERE symbol = (?);",
                Amount,
                Quant,
                symbol,
            )
        db.execute("UPDATE stock SET amount = 0 WHERE Shares_tot <= 0;")
        all = db.execute(
            "SELECT stock.symbol, current, Shares_tot, amount, name, cash FROM stock JOIN current_price ON lower(current_price.symbol) = stock.symbol JOIN users ON user_id = stock.user_id WHERE Shares_tot > 0 AND stock.symbol IN (SELECT symbol FROM (SELECT Shares_tot, symbol FROM stock WHERE user_id = (?) GROUP BY symbol) WHERE Shares_tot > 0) GROUP BY stock.symbol;",
            session["user_id"],
        )
        cash = db.execute("SELECT cash FROM users WHERE id = (?);", session["user_id"])
        Cash_in_bank = 0
        for row in cash:
            Cash_in_bank = row["cash"]
        final = db.execute(
            "select current_price.symbol,current,name,Shares_tot,amount from current_price JOIN stock on lower(current_price.symbol)=stock.symbol WHERE Shares_tot > 0 group by current_price.symbol;"
        )
        Final_tot = 0
        for row in final:
            hold_tot = row["amount"]
            Final_tot += hold_tot
        Final_tot += Cash_in_bank
        current_stock = db.execute("SELECT symbol FROM stock GROUP BY symbol;")
        return render_template(
            "index.html",
            all=all,
            cash=Cash_in_bank,
            current_stock=current_stock,
            Final_tot=Final_tot,
            final=final,
        )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)
        if not request.form.get("shares"):
            return apology("must provide quantity", 400)
        shares = request.form.get("shares")
        # Checking response conforms
        if shares.isdigit():
            buy_quant = int(float(shares))
        else:
            return apology("must provide a positive number", 400)
        if buy_quant <= 0:
            return apology("must provide a positive number", 400)
        sym = request.form.get("symbol")
        symbol = sym.lower()
        display = lookup(symbol)
        if not display:
            return apology("must provide Valid Symbol", 400)
        for row in display:
            price_each = display["price"]
            round_price_each = round(price_each, 2)
            name = display["name"]
            cost = round_price_each * buy_quant
            round_cost = round(cost)

        if not display:
            return apology("must provide Valid Symbol", 400)
        available = db.execute(
            "SELECT cash FROM users WHERE id = (?);", session["user_id"]
        )
        for row in available:
            amount = row["cash"]
            new_cash = amount - round_cost
            round_new_cash = "{0:.2f}".format(new_cash)
        if new_cash > 0:
            ## buy the shares ##
            db.execute(
                "INSERT INTO current_price (symbol, current) values (?,?);",
                symbol,
                round_price_each,
            )
            db.execute(
                "UPDATE users set cash = (?) WHERE id = (?);",
                round_new_cash,
                session["user_id"],
            )
            have = db.execute(
                "SELECT symbol, Shares_tot, amount FROM stock WHERE symbol = (?) AND user_id = (?);",
                symbol,
                session["user_id"],
            )
            if not have:
                db.execute(
                    "INSERT INTO stock (symbol, name, Shares_tot, user_id, amount) VALUES (?, ?, ?, ?, ?);",
                    symbol,
                    name,
                    buy_quant,
                    session["user_id"],
                    cost,
                )
            else:
                for row in have:
                    have_symbol = row["symbol"]
                    current_tot = row["Shares_tot"]
                    now_amount = row["amount"]
                    new_quant = current_tot + buy_quant
                    new_amount = now_amount + cost
                    db.execute(
                        "UPDATE stock SET Shares_tot = (?), amount = (?) WHERE symbol = (?) AND user_id = (?);",
                        new_quant,
                        new_amount,
                        symbol,
                        session["user_id"],
                    )

            db.execute(
                "INSERT INTO history (symbol,name, shares, price, total, user_id, PurchaseDateTime) VALUES (?, ?, ?, ?, ?, ?, (SELECT datetime()) );",
                symbol,
                name,
                buy_quant,
                price_each,
                cost,
                session["user_id"],
            )
            flash("Bought")
            return redirect("/")

        else:
            ## Don't buy the shares ##
            return apology(
                "You dont have enough cash left to purchase these shares", 200
            )
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    if request.method == "GET":
        history = db.execute(
            "SELECT symbol,shares, total, PurchaseDateTime from history;"
        )
        return render_template("history.html", history=history)
    return apology("Nothin to see here", 400)


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
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?;", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
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
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not quote:
            return apology("must provide Valid Symbol", 400)
        return render_template("quoted.html", quote=quote, symbol=symbol)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        # Ensure username not already in use
        username = request.form.get("username")
        current_users = db.execute("SELECT username FROM users;")
        for user in current_users:
            if username == user["username"]:
                return apology("That name is already in use, Please try another", 400)

        # create link to hash password

        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        hash_word = generate_password_hash(password)
        if check_password_hash(hash_word, confirmation):
            db.execute(
                "INSERT INTO users (username, hash) VALUES(?, ?)", username, hash_word
            )
        else:
            return apology("Please Ensure passwords match", 400)

    else:
        return render_template("register.html")
    return redirect("/")


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """change_password"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password was submitted
        elif not request.form.get("old_password"):
            return apology("must provide password", 400)
        # create link to hash password
        username = request.form.get("username")
        new_password = request.form.get("new_password")
        confirm_new_password = request.form.get("confirm_new_password")

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("old_password")
        ):
            return apology("invalid username and/or password", 400)

        hash_word = generate_password_hash(new_password)

        if check_password_hash(hash_word, confirm_new_password):
            db.execute(
                "UPDATE users SET hash = (?) WHERE username = (?)", hash_word, username
            )
            flash("Password Succesfully Changed")
            return redirect("/")
        else:
            return apology("Please Ensure passwords match", 400)
    else:
        return render_template("change_password.html")


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add Cash to Your Account"""
    if request.method == "POST":
        if not request.form.get("amount"):
            return apology("must provide amount", 400)
        amount = request.form.get("amount")
        confirm = request.form.get("confirmation")
        if confirm == amount:
            now = db.execute(
                "SELECT cash FROM users WHERE id = (?);", session["user_id"]
            )
            for row in now:
                current = float(row["cash"])
                new_amount = float(amount) + current
                db.execute(
                    "UPDATE users SET cash = (?) WHERE id = (?);",
                    new_amount,
                    session["user_id"],
                )
            flash("Your Cash account has been updated!")
            return redirect("/")
        else:
            return apology("The amounts don't match, Please try again!", 400)

    else:
        return render_template("add_cash.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)
        if not request.form.get("shares"):
            return apology("must provide quantity", 400)
        shares = request.form.get("shares")
        # Checking response conforms
        if shares.isdigit():
            sell_quant = int(float(shares))
        else:
            return apology("must provide a positive number", 400)
        if sell_quant <= 0:
            return apology("must provide a positive number", 400)
        sym = request.form.get("symbol")
        sell_sym = sym.lower()
        display = lookup(sell_sym)
        if not display:
            return apology("must provide Valid Symbol", 400)
        else:
            for row in display:
                sell_price = display["price"]
                name = display["name"]
                round_sell_price = round(sell_price, 2)
                profit = round_sell_price * int(sell_quant)
                round_profit = round(profit, 2)

        ## calculate shares to sell and update databases accordingly ###
        alter = db.execute("SELECT cash FROM users WHERE id = (?);", session["user_id"])
        for row in alter:
            amount = row["cash"]
            new_cash = amount + round_profit
            rounded_new_cash = "{0:.2f}".format(new_cash)
        db.execute(
            "UPDATE users set cash = (?) WHERE id = (?);",
            rounded_new_cash,
            session["user_id"],
        )
        have = db.execute(
            "SELECT symbol, sum(shares) AS [total_shares] FROM history WHERE symbol = (?) AND user_id = (?) GROUP BY symbol;",
            sell_sym,
            session["user_id"],
        )
        for row in have:
            if sell_sym == row["symbol"]:
                current_stock = row["total_shares"]
                if current_stock >= sell_quant:
                    sold = 0
                    sold -= sell_quant
                    db.execute(
                        "INSERT INTO history (symbol, name, shares, price, total, PurchaseDateTime, user_id) VALUES(?,?,?,?,?,(SELECT datetime()), ?)",
                        sell_sym,
                        name,
                        sold,
                        round_sell_price,
                        round_profit,
                        session["user_id"],
                    )
                    new_stock = current_stock - sell_quant
                    db.execute(
                        "UPDATE stock SET Shares_tot = (?) WHERE symbol = (?) AND user_id = (?);",
                        new_stock,
                        sell_sym,
                        session["user_id"],
                    )
                else:
                    return apology("You don't have enough stock to sell that many", 400)
            else:
                return apology("You don't have any of that stock to sell!", 400)
        flash("Sold!")
        return redirect("/")

    else:
        current_stock = db.execute(
            "SELECT symbol FROM stock WHERE user_id = (?) AND Shares_tot > 0 group by symbol;",
            session["user_id"],
        )
        return render_template("sell.html", current_stock=current_stock)
