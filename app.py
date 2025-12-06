from flask import Flask, render_template, request, redirect
from models import db, User, Group, GroupMember, Expense, Balance

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


with app.app_context():
    db.create_all()


@app.route("/")
def index():
    return render_template("index.html")


# ---------------- USERS ----------------

@app.route("/users")
def users():
    all_users = User.query.all()
    return render_template("users.html", users=all_users)


@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form['name']
    db.session.add(User(name=name))
    db.session.commit()
    return redirect("/users")


# ---------------- GROUPS ----------------

@app.route("/groups")
def groups():
    all_groups = Group.query.all()
    users = User.query.all()
    return render_template("groups.html", groups=all_groups, users=users)


@app.route("/add_group", methods=["POST"])
def add_group():
    name = request.form['name']
    db.session.add(Group(name=name))
    db.session.commit()
    return redirect("/groups")


@app.route("/add_user_to_group", methods=["POST"])
def add_user_to_group():
    user_id = request.form['user_id']
    group_id = request.form['group_id']

    db.session.add(GroupMember(user_id=user_id, group_id=group_id))
    db.session.commit()
    return redirect("/groups")


# ---------------- EXPENSES ----------------

@app.route("/expenses")
def expenses():
    expenses = Expense.query.all()
    groups = Group.query.all()
    users = User.query.all()
    return render_template("expenses.html", expenses=expenses, groups=groups, users=users)


@app.route("/add_expense", methods=["POST"])
def add_expense():
    group_id = int(request.form['group_id'])
    paid_by = int(request.form['paid_by'])
    amount = float(request.form['amount'])
    description = request.form['description']

    # Create expense entry
    expense = Expense(group_id=group_id, paid_by=paid_by, amount=amount, description=description)
    db.session.add(expense)
    db.session.commit()

    # Split equally among members
    members = GroupMember.query.filter_by(group_id=group_id).all()
    split_amount = amount / len(members)

    for member in members:
        if member.user_id != paid_by:
            existing = Balance.query.filter_by(from_user=member.user_id, to_user=paid_by).first()
            if existing:
                existing.amount += split_amount
            else:
                db.session.add(Balance(from_user=member.user_id, to_user=paid_by, amount=split_amount))

    db.session.commit()
    return redirect("/expenses")


# ---------------- BALANCES ----------------

@app.route("/balances")
def balances():
    balances = Balance.query.all()
    users = User.query.all()
    return render_template("balances.html", balances=balances, users={u.id: u.name for u in users})


if __name__ == "__main__":
    app.run(debug=True)
