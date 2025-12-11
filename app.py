from flask import Flask, render_template, request, redirect, send_file
from models import db, User, Group, GroupMember, Expense, Balance

# Data & plotting
import io
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

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
    # Ensure all expenses have a category
    for exp in expenses:
        if not exp.category:
            exp.category = 'Other'
    db.session.commit()
    return render_template("expenses.html", expenses=expenses, groups=groups, users=users)


@app.route("/add_expense", methods=["POST"])
def add_expense():
    group_id = int(request.form['group_id'])
    paid_by = int(request.form['paid_by'])
    amount = float(request.form['amount'])
    description = request.form['description']
    category = request.form.get('category', 'Other')

    # Create expense entry
    expense = Expense(group_id=group_id, paid_by=paid_by, amount=amount, description=description, category=category)
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


@app.route('/group_chart.png')
def group_chart_png():
    """Per-group expense breakdown pie chart."""
    exp = Expense.query.all()
    groups = {g.id: g.name for g in Group.query.all()}
    
    if not exp:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, 'No expenses to display', ha='center', va='center', fontsize=14)
    else:
        rows = [{'group_id': e.group_id, 'amount': float(e.amount)} for e in exp]
        df = pd.DataFrame(rows)
        by_group = df.groupby('group_id')['amount'].sum()
        labels = [groups.get(int(gid), str(gid)) for gid in by_group.index]
        values = by_group.values
        
        fig, ax = plt.subplots(figsize=(8, 6))
        colors = plt.cm.Set3(range(len(labels)))
        wedges, texts, autotexts = ax.pie(values, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
        ax.set_title('Expense Breakdown by Group')
        for autotext in autotexts:
            autotext.set_color('black')
            autotext.set_fontsize(9)
    
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@app.route('/timeseries_chart.png')
def timeseries_chart_png():
    """Time-series chart of expenses over time."""
    exp = Expense.query.all()
    
    if not exp:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, 'No expenses to display', ha='center', va='center', fontsize=14)
    else:
        # Mock date generation: assume created_at or use id as proxy for ordering
        rows = []
        for i, e in enumerate(exp):
            # Create synthetic dates spread over the last 30 days
            date = datetime.now() - timedelta(days=max(0, len(exp) - i - 1))
            rows.append({'date': date, 'amount': float(e.amount)})
        
        df = pd.DataFrame(rows)
        df = df.sort_values('date')
        df['cumulative'] = df['amount'].cumsum()
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7))
        
        # Daily expenses bar chart
        ax1.bar(df['date'], df['amount'], color='steelblue', alpha=0.7)
        ax1.set_ylabel('Amount (₹)')
        ax1.set_title('Daily Expenses')
        ax1.tick_params(axis='x', rotation=45)
        
        # Cumulative expenses line chart
        ax2.plot(df['date'], df['cumulative'], marker='o', color='darkgreen', linewidth=2)
        ax2.fill_between(df['date'], df['cumulative'], alpha=0.3, color='green')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Cumulative (₹)')
        ax2.set_title('Cumulative Expenses Over Time')
        ax2.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@app.route('/export_expenses')
def export_expenses():
    """Export all expenses as CSV."""
    exp = Expense.query.all()
    users = {u.id: u.name for u in User.query.all()}
    groups = {g.id: g.name for g in Group.query.all()}
    
    rows = []
    for e in exp:
        rows.append({
            'ID': e.id,
            'Description': e.description,
            'Amount (₹)': f"{e.amount:.2f}",
            'Paid By': users.get(e.paid_by, 'Unknown'),
            'Group': groups.get(e.group_id, 'Unknown')
        })
    
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(columns=['ID', 'Description', 'Amount (₹)', 'Paid By', 'Group'])
    
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    
    return send_file(
        io.BytesIO(buf.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='expenses.csv'
    )


@app.route('/export_balances')
def export_balances():
    """Export all balances as CSV."""
    bal = Balance.query.all()
    users = {u.id: u.name for u in User.query.all()}
    
    rows = []
    for b in bal:
        rows.append({
            'From': users.get(b.from_user, 'Unknown'),
            'To': users.get(b.to_user, 'Unknown'),
            'Amount (₹)': f"{b.amount:.2f}"
        })
    
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(columns=['From', 'To', 'Amount (₹)'])
    
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    
    return send_file(
        io.BytesIO(buf.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='balances.csv'
    )


@app.route('/category_chart.png')
def category_chart_png():
    """Expense breakdown by category."""
    exp = Expense.query.all()
    
    if not exp:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, 'No expenses to display', ha='center', va='center', fontsize=14)
    else:
        rows = [{'category': e.category or 'Other', 'amount': float(e.amount)} for e in exp]
        df = pd.DataFrame(rows)
        by_cat = df.groupby('category')['amount'].sum()
        labels = by_cat.index.tolist()
        values = by_cat.values
        
        fig, ax = plt.subplots(figsize=(8, 6))
        colors = plt.cm.Pastel1(range(len(labels)))
        wedges, texts, autotexts = ax.pie(values, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
        ax.set_title('Expenses by Category')
        for autotext in autotexts:
            autotext.set_color('black')
            autotext.set_fontsize(9)
    
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
