from flask import Flask, render_template, request, redirect, send_file
from models import db, User, Group, GroupMember, Expense, Balance

# Data & plotting
import io
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

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


@app.route('/charts')
def charts():
    return render_template('charts.html')


@app.route('/chart.png')
def chart_png():
    # Load balances
    bal = Balance.query.all()
    users = {u.id: u.name for u in User.query.all()}

    rows = []
    for b in bal:
        rows.append({'from_user': b.from_user, 'to_user': b.to_user, 'amount': float(b.amount)})

    if rows:
        df = pd.DataFrame(rows)
        received = df.groupby('to_user')['amount'].sum()
        owed = df.groupby('from_user')['amount'].sum()
        net = received.subtract(owed, fill_value=0)
        net = net.sort_values(ascending=False)
        labels = [users.get(int(uid), str(uid)) for uid in net.index]
        values = net.values
    else:
        labels = []
        values = []

    fig, ax = plt.subplots(figsize=(8, 4.5))
    if len(labels) == 0:
        ax.text(0.5, 0.5, 'No balances to display', ha='center', va='center', fontsize=14)
    else:
        colors = plt.cm.Blues(range(50, 250, max(1, int(200 / max(1, len(labels))))))
        ax.bar(labels, values, color=colors)
        ax.axhline(0, color='k', linewidth=0.6)
        ax.set_ylabel('Net (₹)')
        ax.set_title('Net balances per user')
        plt.xticks(rotation=45, ha='right')

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
