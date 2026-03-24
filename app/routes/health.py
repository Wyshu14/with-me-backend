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

def extract_score(analysis_text):
    if not analysis_text:
        return None
    match = re.search(r'(\d+)%', analysis_text)
    if match:
        return int(match.group(1))
    return None

@health_bp.route('/ai-analysis', methods=['POST'])
@jwt_required()
def ai_analysis():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    note = data.get('note', '')
    diagnosis = data.get('diagnosis', '')
    record_id = data.get('record_id')
    member_id = data.get('member_id')

    previous_reports = []
    previous_scores = []

    if member_id:
        doctors = Doctor.query.filter_by(user_id=user_id, member_id=str(member_id)).all()
        doctor_ids = [d.id for d in doctors]
        past_records = MedicalRecord.query.filter(
            MedicalRecord.user_id == user_id,
            MedicalRecord.doctor_id.in_(doctor_ids),
            MedicalRecord.analysis != None
        ).order_by(MedicalRecord.created_at.desc()).limit(3).all()

        for r in past_records:
            score = extract_score(r.analysis)
            if score:
                previous_scores.append(score)
            if r.diagnosis:
                previous_reports.append(f"- Date: {r.date}, Diagnosis: {r.diagnosis}, Score: {score}%")

    comparison_context = ""
    if previous_reports:
        comparison_context = f"""
PREVIOUS MEDICAL HISTORY:
{chr(10).join(previous_reports)}

Previous health scores: {', '.join([str(s) + '%' for s in previous_scores])}
Please compare the current report with previous reports and show if health is IMPROVING or DECLINING.
"""

    prompt = f"""
You are an expert medical AI assistant for Sri Lankan elderly patients. 
Analyze the doctor's note carefully and provide detailed health guidance.

CURRENT DOCTOR'S NOTE:
Diagnosis: {diagnosis}
Note: {note}

{comparison_context}

Please provide a comprehensive analysis with these EXACT sections:

FOOD RECOMMENDATIONS:
- List 5-7 specific Sri Lankan foods that are beneficial (e.g., rice, dhal, gotukola, bitter gourd, turmeric milk)
- List 3-5 foods to avoid with clear reasons
- Mention best meal timings for Sri Lankan lifestyle

MEDICATION SCHEDULE:
- Morning (6AM-8AM): List medications with dosage if mentioned
- Afternoon (12PM-2PM): List medications with dosage if mentioned  
- Night (8PM-10PM): List medications with dosage if mentioned
- Important: Take with food or empty stomach instructions

SUGGESTED REMINDERS:
- List specific daily reminders with exact times
- Include medication reminders, exercise reminders, and meal reminders

HEALTH TIPS:
- 4-5 specific tips suitable for elderly Sri Lankan patients
- Include simple exercises (walking, yoga)
- Include traditional Sri Lankan remedies if appropriate

WARNING SIGNS:
- List 3-4 specific warning signs that require immediate doctor visit
- Make these very clear and simple to understand

EXERCISE RECOMMENDATIONS:
- Suggest 2-3 simple exercises suitable for elderly
- Include duration and frequency

HEALTH TREND ANALYSIS:
{f"Compare with previous scores {previous_scores} and explain if health is IMPROVING or DECLINING. Calculate the trend." if previous_scores else "This is the first report. Establish a baseline health score."}

HEALTH SCORE:
Give a single percentage (0-100%) based on current condition and potential for improvement if advice is followed.
Format: XX% - Brief explanation

Reply in simple English that elderly patients and families can easily understand.
Be specific, caring and encouraging in tone.
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
        print("AI error:", str(e))
        return jsonify({'error': str(e)}), 500

@health_bp.route('/records/<int:doctor_id>', methods=['GET'])
@jwt_required()
def get_records(doctor_id):
    user_id = int(get_jwt_identity())
    records = MedicalRecord.query.filter_by(user_id=user_id, doctor_id=doctor_id).order_by(MedicalRecord.created_at.desc()).all()
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
        note=data['note'],
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
    for record in records:
        score = extract_score(record.analysis)
        if score:
            progress.append({
                'date': record.date,
                'score': score,
                'diagnosis': record.diagnosis
            })
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
    ).order_by(MedicalRecord.created_at).all()

    scores = []
    for record in records:
        score = extract_score(record.analysis)
        if score:
            scores.append(score)

    if len(scores) < 2:
        trend = "insufficient_data"
        message = "Need more reports to analyse trend"
    else:
        diff = scores[-1] - scores[0]
        if diff > 5:
            trend = "improving"
            message = f"Health is IMPROVING! Score went from {scores[0]}% to {scores[-1]}%"
        elif diff < -5:
            trend = "declining"
            message = f"Health needs attention. Score went from {scores[0]}% to {scores[-1]}%"
        else:
            trend = "stable"
            message = f"Health is STABLE at around {scores[-1]}%"

    return jsonify({
        'trend': trend,
        'message': message,
        'scores': scores,
        'latest_score': scores[-1] if scores else 0,
        'first_score': scores[0] if scores else 0,
    }), 200

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
        age=data['age']
    )
    db.session.add(member)
    db.session.commit()
    return jsonify(member.to_dict()), 201

@health_bp.route('/members/<int:member_id>', methods=['DELETE'])
@jwt_required()
def delete_member(member_id):
    member = FamilyMember.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
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
    return jsonify(reminder.to_dict()), 201

@health_bp.route('/reminders/<int:reminder_id>', methods=['DELETE'])
@jwt_required()
def delete_reminder(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    db.session.delete(reminder)
    db.session.commit()
    return jsonify({'message': 'Deleted'}), 200

@health_bp.route('/reminders/<int:reminder_id>/acknowledge', methods=['PATCH'])
@jwt_required()
def acknowledge_reminder(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    data = request.get_json()
    reminder.status = data.get('status', 'acknowledged')
    db.session.commit()
    return jsonify(reminder.to_dict()), 200
```

Now save the file and run in terminal:
```
git add .
```
```
git commit -m "Remove API key from code"
```
```
git push -u origin main