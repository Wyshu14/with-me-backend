from app import create_app, db
from app.models.models import User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    user = User.query.filter_by(email="wyshnavi.t2000@gmail.com").first()

    if not user:
        user = User(
            name="Wyshnavi",
            email="wyshnavi.t2000@gmail.com",
            password_hash=generate_password_hash("123456"),
            role="guardian"
        )
        db.session.add(user)
        db.session.commit()
        print("User created successfully")
    else:
        print("User already exists")