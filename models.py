from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    share_token = db.Column(db.String(64), unique=True)

    # Relationships
    meals = db.relationship('Meal', backref='user', lazy=True, cascade='all, delete-orphan')
    goals = db.relationship('Goal', backref='user', lazy=True, cascade='all, delete-orphan')
    daily_limits = db.relationship('DailyLimit', backref='user', lazy=True, cascade='all, delete-orphan')

    def get_limits(self):
        limits = DailyLimit.query.filter_by(user_id=self.id).first()
        if not limits:
            limits = DailyLimit(user_id=self.id)
            db.session.add(limits)
            db.session.commit()
        return limits


class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    image_path = db.Column(db.String(500))
    meal_type = db.Column(db.String(20))  # breakfast, lunch, dinner, snack
    date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Nutritional values
    calories = db.Column(db.Float, default=0)
    protein = db.Column(db.Float, default=0)  # grams
    carbs = db.Column(db.Float, default=0)  # grams
    fat = db.Column(db.Float, default=0)  # grams
    fiber = db.Column(db.Float, default=0)  # grams
    sugar = db.Column(db.Float, default=0)  # grams
    sodium = db.Column(db.Float, default=0)  # mg
    saturated_fat = db.Column(db.Float, default=0)  # grams
    cholesterol = db.Column(db.Float, default=0)  # mg
    potassium = db.Column(db.Float, default=0)  # mg
    vitamin_a = db.Column(db.Float, default=0)  # % daily value
    vitamin_c = db.Column(db.Float, default=0)  # % daily value
    calcium = db.Column(db.Float, default=0)  # % daily value
    iron = db.Column(db.Float, default=0)  # % daily value


class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_type = db.Column(db.String(50))  # calories, protein, weight, etc.
    target_value = db.Column(db.Float)
    current_value = db.Column(db.Float, default=0)
    unit = db.Column(db.String(20))
    start_date = db.Column(db.Date, default=date.today)
    end_date = db.Column(db.Date)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DailyLimit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    calories = db.Column(db.Float, default=2000)
    protein = db.Column(db.Float, default=50)
    carbs = db.Column(db.Float, default=300)
    fat = db.Column(db.Float, default=65)
    fiber = db.Column(db.Float, default=25)
    sugar = db.Column(db.Float, default=50)
    sodium = db.Column(db.Float, default=2300)
    saturated_fat = db.Column(db.Float, default=20)
    cholesterol = db.Column(db.Float, default=300)
    potassium = db.Column(db.Float, default=3500)
