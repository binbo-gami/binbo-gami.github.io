from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import re  # 正規表現モジュールを追加

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'  # 秘密鍵を設定 (本番環境ではより安全なものを)
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    employer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # 雇い主のID (バイトの場合)
    employer = db.relationship('User', remote_side=[id], backref='employees')
    bets = db.relationship('Bet', backref='user', lazy=True)
    invitations_received = db.relationship('Invitation', foreign_keys='Invitation.employee_id', backref='employee', lazy=True)
    invitations_sent = db.relationship('Invitation', foreign_keys='Invitation.employer_id', backref='employer', lazy=True)

class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now) # ← 修正しました
    result = db.Column(db.String(10), nullable=False)
    rule = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<Bet {self.timestamp} - {self.user.username} - {self.result} - {self.amount}>'

class Invitation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending') # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def login_required():
    def wrapper(fn):
        def decorated_view(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

def calculate_total_balance(user_id):
    total_balance = 0
    bets = Bet.query.filter_by(user_id=user_id).all()
    for bet in bets:
        if bet.result == '勝ち':
            total_balance += bet.amount
        elif bet.result == '負け':
            total_balance -= bet.amount
    return total_balance

def format_man_oku(amount):
    oku = amount // 100000000
    man = (amount % 100000000) // 10000
    return f"{oku}億{man:04d}万"

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None  # エラーメッセージを格納する変数
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not re.match(r'^[a-zA-Z0-9]+$', username):
            error = "ユーザーIDは半角アルファベットと数字のみ使用可能です。"
        elif User.query.filter_by(username=username).first():
            error = "そのユーザー名は既に登録されています。"
        else:
            hashed_password = generate_password_hash(password)
            new_user = User(username=username, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html', error=error) # テンプレートにエラーメッセージを渡す

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('home_page'))
        else:
            return "ユーザー名またはパスワードが間違っています。"
    return render_template('login.html')

@app.route('/logout', endpoint='logout')
@login_required()
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@login_required()
@app.route('/', methods=['GET', 'POST'])
def home_page():
    user_id = session['user_id']
    user = User.query.get(user_id)
    total_balance = calculate_total_balance(user_id)
    bets = Bet.query.filter_by(user_id=user_id).order_by(Bet.timestamp.desc()).all()

    return render_template('index.html', total_balance=total_balance, username=user.username, bets=bets)

@login_required()
@app.route('/bait', methods=['GET', 'POST'])
def bait_page():
    user_id = session['user_id']
    user = User.query.get(user_id)
    total_balance = calculate_total_balance(user_id)
    bets = Bet.query.filter_by(user_id=user_id).order_by(Bet.timestamp.desc()).all()

    employer = None
    if user.employer_id:
        employer = User.query.get(user.employer_id)

    if request.method == 'POST':
        result = request.form['result']
        rule = request.form['rule']
        oku_str = request.form.get('oku', '0')
        man_str = request.form.get('man', '0')

        amount = int(oku_str) * 100000000 + int(man_str) * 10000

        print(f"入力内容: 結果={result}, ルール={rule}, 億={oku_str}, 万={man_str}, 金額={amount}")

        new_bet = Bet(user_id=user_id, result=result, rule=rule, amount=amount)
        db.session.add(new_bet)
        db.session.commit()

        latest_bets = Bet.query.filter_by(user_id=user_id).order_by(Bet.timestamp.desc()).all()
        print("保存後のベットデータ:")
        for bet in latest_bets:
            print(f"  {bet.timestamp} - {bet.result} - {bet.rule} - {bet.amount}")
        bets = latest_bets

        return redirect(url_for('bait_page'))

    formatted_total_balance = format_man_oku(total_balance)
    formatted_bets = []
    print(f"betsの長さ: {len(bets)}")
    for bet in bets:
        print(f"betの型: {type(bet)}, bet.timestampの型: {type(bet.timestamp)}")
        formatted_bets.append({
            'timestamp': bet.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'result': bet.result,
            'rule': bet.rule,
            'amount': bet.amount  # ← ここを元の数値に戻しました
        })

    return render_template('bait.html', total_balance=formatted_total_balance, username=user.username, bets=formatted_bets, employer=employer)

# ... (app.pyの既存のコード)

@login_required()
@app.route('/koinushi', methods=['GET', 'POST'])
def koinushi_page():
    user_id = session['user_id']
    user = User.query.get(user_id)
    return render_template('koinushi.html', username=user.username)

@login_required()
@app.route('/employer/history')
def employer_history_page():
    user_id = session['user_id']
    employer = User.query.get(user_id)

    if not employer or not employer.employees:
        return "あなたにはまだバイトが登録されていません。"

    all_bets = []
    for employee in employer.employees:
        for bet in employee.bets:
            all_bets.append({
                'timestamp': bet.timestamp,
                'employee_username': employee.username,
                'result': bet.result,
                'rule': bet.rule,
                'amount': bet.amount
            })

    all_bets.sort(key=lambda x: x['timestamp'], reverse=True)

    formatted_bets = []
    for bet in all_bets:
        formatted_bets.append({
            'timestamp': bet['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'employee_username': bet['employee_username'],
            'result': bet['result'],
            'rule': bet['rule'],
            'amount': format_man_oku(bet['amount'])
        })

    return render_template('employer_history.html', username=employer.username, bets=formatted_bets)

@login_required()
@app.route('/employer/invite')
def employer_invite_page():
    user_id = session['user_id']
    employer = User.query.get(user_id)
    if not employer:
        return redirect(url_for('home_page')) # エラー処理

    # 自分自身と、既に自分の従業員であるユーザーを除外
    employees_ids = [employee.id for employee in employer.employees]
    employees_ids.append(employer.id)
    potential_employees = User.query.filter(User.id.notin_(employees_ids)).all()

    return render_template('employer_invite.html', username=employer.username, potential_employees=potential_employees)

@login_required()
@app.route('/employer/send_invite/<int:employee_id>')
def employer_send_invite(employee_id):
    employer_id = session['user_id']

    # 自分自身への招待は禁止
    if employer_id == employee_id:
        return "自分自身を招待することはできません。"

    # 既に招待済みか確認
    existing_invitation = Invitation.query.filter_by(employer_id=employer_id, employee_id=employee_id).first()
    if existing_invitation:
        return "既に招待を送っています。"

    # 従業員が存在するか確認
    employee = User.query.get(employee_id)
    employer = User.query.get(employer_id)
    if not employee or not employer:
        return "招待先のユーザーが見つかりません。"

    new_invitation = Invitation(employer_id=employer_id, employee_id=employee_id)
    db.session.add(new_invitation)
    db.session.commit()

    return redirect(url_for('employer_invite_page'))

@login_required()
@app.route('/employee/invitations')
def employee_invitations_page():
    user_id = session['user_id']
    employee = User.query.get(user_id)
    if not employee:
        return redirect(url_for('home_page')) # エラー処理
    invitations = Invitation.query.filter_by(employee_id=user_id, status='pending').all()
    return render_template('employee_invitations.html', username=employee.username, invitations=invitations)

@login_required()
@app.route('/employee/accept_invite/<int:invitation_id>')
def employee_accept_invite(invitation_id):
    user_id = session['user_id']
    invitation = Invitation.query.get(invitation_id)

    if not invitation or invitation.employee_id != user_id or invitation.status != 'pending':
        return redirect(url_for('employee_invitations_page')) # 不正なリクエスト

    employer = User.query.get(invitation.employer_id)
    employee = User.query.get(invitation.employee_id)

    if employer and employee:
        employee.employer_id = employer.id
        invitation.status = 'accepted'
        db.session.commit()
        return redirect(url_for('employee_invitations_page'))
    else:
        return "雇い主または従業員の情報が見つかりませんでした。"

@login_required()
@app.route('/employee/reject_invite/<int:invitation_id>')
def employee_reject_invite(invitation_id):
    user_id = session['user_id']
    invitation = Invitation.query.get(invitation_id)

    if not invitation or invitation.employee_id != user_id or invitation.status != 'pending':
        return redirect(url_for('employee_invitations_page')) # 不正なリクエスト

    invitation.status = 'rejected'
    db.session.commit()
    return redirect(url_for('employee_invitations_page'))

if __name__ == '__main__':
    with app.app_context():
        app.run(debug=True)