from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.models import Doctor, Reminder, MedicalRecord, FamilyMember
import requests
import re
import os

health_bp = Blueprint('health', __name__)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def ask_groq(prompt):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2048
    }
    res = requests.post(GROQ_URL, headers=headers, json=body, timeout=30)
    data = res.json()
    if 'choices' not in data:
        raise Exception(f"Groq error: {data}")
    return data['choices'][0]['message']['content']


def extract_score(text):
    if not text:
        return None
    match = re.search(r'(\d+)%', text)
    return int(match.group(1)) if match else None


@health_bp.route('/ai-analysis', methods=['POST'])
@jwt_required()
def ai_analysis():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    note = data.get('note', '')
    diagnosis = data.get('diagnosis', '')
    record_id = data.get('record_id')
    member_id = data.get('member_id')

    previous_scores = []

    if member_id:
        doctors = Doctor.query.filter_by(user_id=user_id, member_id=str(member_id)).all()
        doctor_ids = [d.id for d in doctors]
        records = MedicalRecord.query.filter(
            MedicalRecord.user_id == user_id,
            MedicalRecord.doctor_id.in_(doctor_ids),
            MedicalRecord.analysis != None
        ).order_by(MedicalRecord.created_at.desc()).limit(3).all()
        for r in records:
            score = extract_score(r.analysis)
            if score:
                previous_scores.append(score)

    prompt = f"""
You are a medical AI assistant for elderly patients in Sri Lanka.

Diagnosis: {diagnosis}
Note: {note}

Previous scores: {previous_scores}

Give:
- Food recommendations
- Medication schedule
- Reminders
- Health tips
- Warning signs
- Exercises
- Trend (improving/declining)
- Health score (%)

Simple language.
"""

    try:
        result = ask_groq(prompt)
        if record_id:
            record = MedicalRecord.query.get(record_id)
            if record:
                record.analysis = result
                db.session.commit()
        return jsonify({'analysis': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@health_bp.route('/records/<int:doctor_id>', methods=['GET'])
@jwt_required()
def get_records(doctor_id):
    user_id = int(get_jwt_identity())
    records = MedicalRecord.query.filter_by(
        user_id=user_id,
        doctor_id=doctor_id
    ).order_by(MedicalRecord.created_at.desc()).all()
    return jsonify([r.to_dict() for r in records]), 200


@health_bp.route('/records', methods=['POST'])
@jwt_required()
def add_record():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    record = MedicalRecord(
        user_id=user_id,
        doctor_id=data['doctor_id'],
        diagnosis=data.get('diagnosis', ''),
        note=data['note']
    )
    db.session.add(record)
    db.session.commit()
    return jsonify(record.to_dict()), 201


@health_bp.route('/health-progress/<int:member_id>', methods=['GET'])
@jwt_required()
def health_progress(member_id):
    user_id = int(get_jwt_identity())
    doctors = Doctor.query.filter_by(user_id=user_id, member_id=str(member_id)).all()
    doctor_ids = [d.id for d in doctors]
    records = MedicalRecord.query.filter(
        MedicalRecord.user_id == user_id,
        MedicalRecord.doctor_id.in_(doctor_ids),
        MedicalRecord.analysis != None
    ).order_by(MedicalRecord.created_at).all()
    progress = []
    for r in records:
        score = extract_score(r.analysis)
        if score:
            progress.append({'date': r.date, 'score': score})
    return jsonify(progress), 200


@health_bp.route('/health-trend/<int:member_id>', methods=['GET'])
@jwt_required()
def health_trend(member_id):
    user_id = int(get_jwt_identity())
    doctors = Doctor.query.filter_by(user_id=user_id, member_id=str(member_id)).all()
    doctor_ids = [d.id for d in doctors]
    records = MedicalRecord.query.filter(
        MedicalRecord.user_id == user_id,
        MedicalRecord.doctor_id.in_(doctor_ids),
        MedicalRecord.analysis != None
    ).all()
    scores = [extract_score(r.analysis) for r in records if extract_score(r.analysis)]
    if len(scores) < 2:
        return jsonify({'trend': 'insufficient_data'}), 200
    diff = scores[-1] - scores[0]
    trend = "improving" if diff > 5 else "declining" if diff < -5 else "stable"
    return jsonify({'trend': trend, 'scores': scores}), 200


@health_bp.route('/members', methods=['GET'])
@jwt_required()
def get_members():
    user_id = int(get_jwt_identity())
    members = FamilyMember.query.filter_by(user_id=user_id).all()
    return jsonify([m.to_dict() for m in members]), 200


@health_bp.route('/members', methods=['POST'])
@jwt_required()
def add_member():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    member = FamilyMember(
        user_id=user_id,
        name=data['name'],
        relation=data['relation'],
        age=data['age'],
        phone=data.get('phone', '')
    )
    db.session.add(member)
    db.session.commit()

    # ✅ REAL-TIME: Notify all clients new member added
    from app import socketio
    socketio.emit('member_added', {'member': member.to_dict()})

    return jsonify(member.to_dict()), 201


@health_bp.route('/members/<int:member_id>', methods=['DELETE'])
@jwt_required()
def delete_member(member_id):
    member = FamilyMember.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()

    # ✅ REAL-TIME: Notify all clients member deleted
    from app import socketio
    socketio.emit('member_deleted', {'member_id': member_id})

    return jsonify({'message': 'Deleted'}), 200


@health_bp.route('/doctors', methods=['GET'])
@jwt_required()
def get_doctors():
    user_id = int(get_jwt_identity())
    member_id = request.args.get('member_id')
    doctors = Doctor.query.filter_by(user_id=user_id, member_id=member_id).all()
    return jsonify([d.to_dict() for d in doctors]), 200


@health_bp.route('/doctors', methods=['POST'])
@jwt_required()
def add_doctor():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    doctor = Doctor(
        user_id=user_id,
        member_id=str(data['member_id']),
        name=data['name'],
        speciality=data['speciality']
    )
    db.session.add(doctor)
    db.session.commit()

    # ✅ REAL-TIME: Notify all clients new doctor added
    from app import socketio
    socketio.emit('doctor_added', {
        'doctor': doctor.to_dict(),
        'member_id': str(data['member_id'])
    })

    return jsonify(doctor.to_dict()), 201


@health_bp.route('/doctors/<int:doctor_id>', methods=['DELETE'])
@jwt_required()
def delete_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    db.session.delete(doctor)
    db.session.commit()
    return jsonify({'message': 'Deleted'}), 200


@health_bp.route('/reminders', methods=['GET'])
@jwt_required()
def get_reminders():
    user_id = int(get_jwt_identity())
    member_id = request.args.get('member_id')
    reminders = Reminder.query.filter_by(user_id=user_id, member_id=member_id).all()
    return jsonify([r.to_dict() for r in reminders]), 200


@health_bp.route('/reminders', methods=['POST'])
@jwt_required()
def add_reminder():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    reminder = Reminder(
        user_id=user_id,
        member_id=str(data['member_id']),
        title=data['title'],
        type=data['type'],
        food_timing=data.get('foodTiming', ''),
        time=data['time'],
        status='pending'
    )
    db.session.add(reminder)
    db.session.commit()

    # ✅ REAL-TIME: Push new reminder instantly to all connected clients
    from app import socketio
    socketio.emit('new_reminder', {
        'reminder': reminder.to_dict(),
        'member_id': str(data['member_id'])
    })

    return jsonify(reminder.to_dict()), 201


@health_bp.route('/reminders/<int:reminder_id>', methods=['DELETE'])
@jwt_required()
def delete_reminder(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    db.session.delete(reminder)
    db.session.commit()

    # ✅ REAL-TIME: Notify all clients reminder deleted
    from app import socketio
    socketio.emit('reminder_deleted', {'reminder_id': reminder_id})

    return jsonify({'message': 'Deleted'}), 200


@health_bp.route('/reminders/<int:reminder_id>/acknowledge', methods=['PATCH'])
@jwt_required()
def acknowledge_reminder(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    data = request.get_json()
    reminder.status = data.get('status', 'acknowledged')
    db.session.commit()

    # ✅ REAL-TIME: Notify guardian that elder marked reminder as done
    from app import socketio
    socketio.emit('reminder_acknowledged', {
        'reminder_id': reminder_id,
        'member_id': reminder.member_id,
        'title': reminder.title,
        'status': reminder.status
    })

    return jsonify(reminder.to_dict()), 200