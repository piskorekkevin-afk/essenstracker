import os
import json
import uuid
import base64
import secrets
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, session, send_from_directory, abort
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import db, User, Meal, Goal, DailyLimit

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///essenstracker.db'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_meal_image(image_path):
    """Analyze a meal image using Claude Vision API."""
    try:
        import anthropic
        client = anthropic.Anthropic()

        with open(image_path, 'rb') as f:
            image_data = base64.standard_b64encode(f.read()).decode('utf-8')

        ext = image_path.rsplit('.', 1)[1].lower()
        media_types = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}
        media_type = media_types.get(ext, 'image/jpeg')

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": """Analysiere dieses Bild einer Mahlzeit. Antworte NUR mit einem JSON-Objekt (kein Markdown, kein Text drumherum) in diesem Format:
{
    "name": "Name der Mahlzeit auf Deutsch",
    "description": "Kurze Beschreibung der Mahlzeit auf Deutsch",
    "calories": 0,
    "protein": 0,
    "carbs": 0,
    "fat": 0,
    "fiber": 0,
    "sugar": 0,
    "sodium": 0,
    "saturated_fat": 0,
    "cholesterol": 0,
    "potassium": 0,
    "vitamin_a": 0,
    "vitamin_c": 0,
    "calcium": 0,
    "iron": 0
}
Schätze die Nährwerte realistisch für eine typische Portion. Kalorien in kcal, Makronährstoffe in Gramm, Natrium/Cholesterin/Kalium in mg, Vitamine/Mineralien in % Tagesbedarf."""
                    }
                ],
            }],
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith('```'):
            response_text = response_text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        return json.loads(response_text)
    except Exception as e:
        print(f"AI analysis error: {e}")
        return None


def get_meal_suggestions(user_id):
    """Get meal suggestions based on eating history using Claude API."""
    try:
        import anthropic
        client = anthropic.Anthropic()

        recent_meals = Meal.query.filter_by(user_id=user_id).order_by(
            Meal.created_at.desc()
        ).limit(20).all()

        limits = db.session.get(User, user_id).get_limits()

        today_meals = Meal.query.filter_by(user_id=user_id, date=date.today()).all()
        today_calories = sum(m.calories for m in today_meals)
        today_protein = sum(m.protein for m in today_meals)
        today_carbs = sum(m.carbs for m in today_meals)
        today_fat = sum(m.fat for m in today_meals)
        today_fiber = sum(m.fiber for m in today_meals)

        meal_history = ", ".join([m.name for m in recent_meals]) if recent_meals else "Noch keine Mahlzeiten erfasst"

        prompt = f"""Basierend auf dem bisherigen Essensverlauf eines Nutzers, schlage 3 gesunde Mahlzeiten vor.

Bisherige Mahlzeiten: {meal_history}

Heutige Werte / Tageslimits:
- Kalorien: {today_calories:.0f} / {limits.calories:.0f} kcal
- Protein: {today_protein:.0f} / {limits.protein:.0f} g
- Kohlenhydrate: {today_carbs:.0f} / {limits.carbs:.0f} g
- Fett: {today_fat:.0f} / {limits.fat:.0f} g
- Ballaststoffe: {today_fiber:.0f} / {limits.fiber:.0f} g

Antworte NUR mit einem JSON-Array (kein Markdown) in diesem Format:
[
    {{"name": "Name", "description": "Beschreibung und warum es passt", "calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0}}
]
Die Vorschläge sollen abwechslungsreich sein und die noch fehlenden Nährwerte ergänzen."""

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith('```'):
            response_text = response_text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        return json.loads(response_text)
    except Exception as e:
        print(f"Suggestion error: {e}")
        return []


# ── Auth Routes ──────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('Bitte alle Felder ausfüllen.', 'error')
            return redirect(url_for('register'))

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Benutzername oder E-Mail bereits vergeben.', 'error')
            return redirect(url_for('register'))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            share_token=secrets.token_urlsafe(32)
        )
        db.session.add(user)
        db.session.commit()

        # Create default daily limits
        user.get_limits()

        login_user(user)
        flash('Willkommen bei EssenTracker!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Ungültige Anmeldedaten.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ── Dashboard ────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    today = date.today()
    today_meals = Meal.query.filter_by(user_id=current_user.id, date=today).order_by(Meal.created_at).all()
    limits = current_user.get_limits()

    totals = {
        'calories': sum(m.calories for m in today_meals),
        'protein': sum(m.protein for m in today_meals),
        'carbs': sum(m.carbs for m in today_meals),
        'fat': sum(m.fat for m in today_meals),
        'fiber': sum(m.fiber for m in today_meals),
        'sugar': sum(m.sugar for m in today_meals),
        'sodium': sum(m.sodium for m in today_meals),
    }

    # Week data for chart
    week_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_meals = Meal.query.filter_by(user_id=current_user.id, date=d).all()
        week_data.append({
            'date': d.strftime('%a'),
            'calories': sum(m.calories for m in day_meals),
            'protein': sum(m.protein for m in day_meals),
            'carbs': sum(m.carbs for m in day_meals),
            'fat': sum(m.fat for m in day_meals),
        })

    goals = Goal.query.filter_by(user_id=current_user.id, completed=False).all()

    return render_template('dashboard.html',
                           meals=today_meals, limits=limits,
                           totals=totals, week_data=week_data, goals=goals)


# ── Meal Routes ──────────────────────────────────────────────────

@app.route('/meal/add', methods=['GET', 'POST'])
@login_required
def add_meal():
    if request.method == 'POST':
        image = request.files.get('image')
        analysis = None

        if image and allowed_file(image.filename):
            filename = f"{uuid.uuid4().hex}_{secure_filename(image.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(filepath)
            analysis = analyze_meal_image(filepath)
        else:
            filename = None

        if analysis:
            meal = Meal(
                user_id=current_user.id,
                name=analysis.get('name', 'Unbekannte Mahlzeit'),
                description=analysis.get('description', ''),
                image_path=filename,
                meal_type=request.form.get('meal_type', 'snack'),
                date=date.today(),
                calories=analysis.get('calories', 0),
                protein=analysis.get('protein', 0),
                carbs=analysis.get('carbs', 0),
                fat=analysis.get('fat', 0),
                fiber=analysis.get('fiber', 0),
                sugar=analysis.get('sugar', 0),
                sodium=analysis.get('sodium', 0),
                saturated_fat=analysis.get('saturated_fat', 0),
                cholesterol=analysis.get('cholesterol', 0),
                potassium=analysis.get('potassium', 0),
                vitamin_a=analysis.get('vitamin_a', 0),
                vitamin_c=analysis.get('vitamin_c', 0),
                calcium=analysis.get('calcium', 0),
                iron=analysis.get('iron', 0),
            )
        else:
            meal = Meal(
                user_id=current_user.id,
                name=request.form.get('name', 'Mahlzeit'),
                description=request.form.get('description', ''),
                image_path=filename,
                meal_type=request.form.get('meal_type', 'snack'),
                date=date.today(),
                calories=float(request.form.get('calories', 0) or 0),
                protein=float(request.form.get('protein', 0) or 0),
                carbs=float(request.form.get('carbs', 0) or 0),
                fat=float(request.form.get('fat', 0) or 0),
                fiber=float(request.form.get('fiber', 0) or 0),
                sugar=float(request.form.get('sugar', 0) or 0),
                sodium=float(request.form.get('sodium', 0) or 0),
            )

        db.session.add(meal)
        db.session.commit()

        if request.headers.get('Accept') == 'application/json':
            return jsonify({'success': True, 'meal_id': meal.id, 'name': meal.name})

        flash(f'"{meal.name}" wurde hinzugefügt!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_meal.html')


@app.route('/meal/<int:meal_id>/delete', methods=['POST'])
@login_required
def delete_meal(meal_id):
    meal = Meal.query.get_or_404(meal_id)
    if meal.user_id != current_user.id:
        abort(403)
    if meal.image_path:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], meal.image_path)
        if os.path.exists(img_path):
            os.remove(img_path)
    db.session.delete(meal)
    db.session.commit()
    flash('Mahlzeit gelöscht.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ── Weekly Plan ──────────────────────────────────────────────────

@app.route('/weekly')
@login_required
def weekly_plan():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    limits = current_user.get_limits()

    days = []
    for i in range(7):
        d = start_of_week + timedelta(days=i)
        day_meals = Meal.query.filter_by(user_id=current_user.id, date=d).order_by(Meal.created_at).all()
        totals = {
            'calories': sum(m.calories for m in day_meals),
            'protein': sum(m.protein for m in day_meals),
            'carbs': sum(m.carbs for m in day_meals),
            'fat': sum(m.fat for m in day_meals),
            'fiber': sum(m.fiber for m in day_meals),
        }
        days.append({
            'date': d,
            'name': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][d.weekday()],
            'is_today': d == today,
            'meals': day_meals,
            'totals': totals,
        })

    return render_template('weekly.html', days=days, limits=limits)


# ── Goals ────────────────────────────────────────────────────────

@app.route('/goals')
@login_required
def goals():
    active_goals = Goal.query.filter_by(user_id=current_user.id, completed=False).order_by(Goal.created_at.desc()).all()
    completed_goals = Goal.query.filter_by(user_id=current_user.id, completed=True).order_by(Goal.created_at.desc()).limit(10).all()
    return render_template('goals.html', active_goals=active_goals, completed_goals=completed_goals)


@app.route('/goals/add', methods=['POST'])
@login_required
def add_goal():
    goal = Goal(
        user_id=current_user.id,
        title=request.form.get('title', ''),
        description=request.form.get('description', ''),
        target_type=request.form.get('target_type', 'calories'),
        target_value=float(request.form.get('target_value', 0) or 0),
        unit=request.form.get('unit', ''),
        end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form.get('end_date') else None,
    )
    db.session.add(goal)
    db.session.commit()
    flash('Ziel erstellt!', 'success')
    return redirect(url_for('goals'))


@app.route('/goals/<int:goal_id>/complete', methods=['POST'])
@login_required
def complete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        abort(403)
    goal.completed = True
    db.session.commit()
    flash('Ziel erreicht! Glückwunsch!', 'success')
    return redirect(url_for('goals'))


@app.route('/goals/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        abort(403)
    db.session.delete(goal)
    db.session.commit()
    flash('Ziel gelöscht.', 'success')
    return redirect(url_for('goals'))


# ── Daily Limits ─────────────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    limits = current_user.get_limits()
    if request.method == 'POST':
        limits.calories = float(request.form.get('calories', 2000) or 2000)
        limits.protein = float(request.form.get('protein', 50) or 50)
        limits.carbs = float(request.form.get('carbs', 300) or 300)
        limits.fat = float(request.form.get('fat', 65) or 65)
        limits.fiber = float(request.form.get('fiber', 25) or 25)
        limits.sugar = float(request.form.get('sugar', 50) or 50)
        limits.sodium = float(request.form.get('sodium', 2300) or 2300)
        limits.saturated_fat = float(request.form.get('saturated_fat', 20) or 20)
        limits.cholesterol = float(request.form.get('cholesterol', 300) or 300)
        limits.potassium = float(request.form.get('potassium', 3500) or 3500)
        db.session.commit()
        flash('Tageslimits aktualisiert!', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html', limits=limits)


# ── Suggestions ──────────────────────────────────────────────────

@app.route('/suggestions')
@login_required
def suggestions():
    return render_template('suggestions.html')


@app.route('/api/suggestions')
@login_required
def api_suggestions():
    results = get_meal_suggestions(current_user.id)
    return jsonify(results)


# ── Sharing ──────────────────────────────────────────────────────

@app.route('/share')
@login_required
def share():
    return render_template('share.html', token=current_user.share_token)


@app.route('/shared/<token>')
def shared_profile(token):
    user = User.query.filter_by(share_token=token).first_or_404()
    today = date.today()
    today_meals = Meal.query.filter_by(user_id=user.id, date=today).all()
    limits = user.get_limits()

    totals = {
        'calories': sum(m.calories for m in today_meals),
        'protein': sum(m.protein for m in today_meals),
        'carbs': sum(m.carbs for m in today_meals),
        'fat': sum(m.fat for m in today_meals),
        'fiber': sum(m.fiber for m in today_meals),
    }

    week_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_meals = Meal.query.filter_by(user_id=user.id, date=d).all()
        week_data.append({
            'date': d.strftime('%a'),
            'calories': sum(m.calories for m in day_meals),
        })

    goals = Goal.query.filter_by(user_id=user.id, completed=False).all()

    return render_template('shared.html', user=user, meals=today_meals,
                           totals=totals, limits=limits, week_data=week_data, goals=goals)


# ── History ──────────────────────────────────────────────────────

@app.route('/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    meals = Meal.query.filter_by(user_id=current_user.id).order_by(
        Meal.date.desc(), Meal.created_at.desc()
    ).paginate(page=page, per_page=20)
    return render_template('history.html', meals=meals)


# ── Init ─────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
