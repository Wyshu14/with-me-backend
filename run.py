from app import create_app, db, socketio
from app.models.models import User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    db.create_all()
    
    existing = User.query.filter_by(email='wthaneswaran14@gmail.com').first()
    if not existing:
        default_user = User(
            name='wyshnavi thaneswaran',
            email='wthaneswaran14@gmail.com',
            password_hash=generate_password_hash('Wyshnavi123'),
            role='guardian'
        )
        db.session.add(default_user)
        db.session.commit()
        print('✅ Default account created!')
    else:
        print('✅ Default account already exists!')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)