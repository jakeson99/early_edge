import os
from datetime import datetime, timezone

import pytz
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

import db
import email_job

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')

DELIVERY_HOUR_MAP = {
    "5:00 AM": 5,
    "6:00 AM": 6,
    "7:00 AM": 7,
    "8:00 AM": 8,
}


# ── Scheduler ────────────────────────────────────────────────────────────────

def hourly_check():
    print("[scheduler] Running hourly check…")
    users = db.get_active_users()
    now_utc = datetime.now(pytz.utc)

    for user in users:
        try:
            tz_name = user.get('timezone') or 'UTC'
            tz = pytz.timezone(tz_name)
            now_local = now_utc.astimezone(tz)
            local_hour = now_local.hour
            local_day = now_local.strftime('%a')
            local_date = now_local.strftime('%Y-%m-%d')

            target_hour = DELIVERY_HOUR_MAP.get(user.get('delivery_time', ''), 7)
            delivery_days = [
                d.strip()
                for d in (user.get('delivery_days') or 'Mon,Tue,Wed,Thu,Fri').split(',')
                if d.strip()
            ]

            if local_hour == target_hour and local_day in delivery_days:
                if not db.has_sent_today(user['id'], local_date):
                    email_job.send_briefing(user)

        except Exception as e:
            print(f"[scheduler] Error for {user.get('email')}: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/profile')
def profile():
    email = request.args.get('email', '')
    user = db.get_user_by_email(email) if email else None
    return render_template('form.html', prefill_email=email, user=user)


@app.route('/submit', methods=['POST'])
def submit():
    consent = request.form.get('consent')
    if not consent:
        return jsonify({'error': 'You must agree to the Privacy Policy to sign up.'}), 400

    data = {
        'name':             request.form.get('name', '').strip(),
        'email':            request.form.get('email', '').strip().lower(),
        'role':             request.form.get('role', '').strip(),
        'industry':         request.form.get('industry', ''),
        'career_stage':     request.form.get('career_stage', ''),
        'primary_goal':     request.form.get('primary_goal', '').strip(),
        'timeline':         request.form.get('timeline', ''),
        'secondary_goals':  request.form.get('secondary_goals', '').strip(),
        'admired_orgs':     request.form.get('admired_orgs', '').strip(),
        'domains':          request.form.get('domains', ''),
        'knowledge_gaps':   request.form.get('knowledge_gaps', '').strip(),
        'skills':           request.form.get('skills', ''),
        'regions':          request.form.get('regions', ''),
        'countries':        request.form.get('countries', '').strip(),
        'intl_ties':        request.form.get('intl_ties', '').strip(),
        'culture_score':    request.form.get('culture_score', 2),
        'engage_style':     request.form.get('engage_style', ''),
        'depth_score':      request.form.get('depth_score', 2),
        'prompts_freq':     request.form.get('prompts_freq', 'Yes, every day'),
        'exclusions':       request.form.get('exclusions', '').strip(),
        'delivery_time':    request.form.get('delivery_time', '7:00 AM'),
        'delivery_days':    request.form.get('delivery_days', 'Mon,Tue,Wed,Thu,Fri'),
        'timezone':         request.form.get('timezone', 'Europe/London'),
        'extra_notes':      request.form.get('extra_notes', '').strip(),
        'consent_timestamp': datetime.now(timezone.utc).isoformat(),
        'consent_version':  '1.0',
        'marketing_consent': bool(request.form.get('marketing_consent')),
    }

    if not data['name'] or not data['email']:
        return jsonify({'error': 'Name and email are required.'}), 400

    try:
        user_id = db.insert_user(data)
    except Exception as e:
        print(f"[submit] DB error: {e}")
        return jsonify({'error': 'Something went wrong saving your profile.'}), 500

    # Send welcome email in background (don't block the response)
    try:
        saved_user = db.get_user_by_email(data['email'])
        if saved_user:
            import threading
            threading.Thread(
                target=email_job.send_welcome_email,
                args=(saved_user,),
                daemon=True
            ).start()
    except Exception as e:
        print(f"[submit] Welcome email error: {e}")

    return jsonify({'status': 'ok', 'name': data['name']})


@app.route('/unsubscribe')
def unsubscribe():
    email = request.args.get('email', '').strip().lower()
    unsubscribed = False
    if email:
        user = db.get_user_by_email(email)
        if user and user.get('active'):
            db.deactivate_user(user['id'])
            unsubscribed = True
    return render_template('unsubscribe.html', email=email, unsubscribed=unsubscribed)


@app.route('/delete', methods=['GET', 'POST'])
def delete_data():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        deleted = False
        if email:
            user = db.get_user_by_email(email)
            if user:
                db.delete_user_data(user['id'])
                deleted = True
        return render_template('delete.html', confirmed=True, deleted=deleted, email=email)
    return render_template('delete.html', confirmed=False)


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/admin/send-now', methods=['POST'])
def admin_send_now():
    """Manually trigger briefing emails to all active subscribers."""
    token = request.headers.get('X-Admin-Token') or request.args.get('token')
    secret = os.environ.get('SECRET_KEY', '')
    if not token or token != secret:
        return jsonify({'error': 'Unauthorized'}), 401

    users = db.get_active_users()
    results = {'queued': 0, 'skipped': 0, 'emails': []}

    import threading
    from datetime import date
    local_date = date.today().isoformat()

    for user in users:
        if db.has_sent_today(user['id'], local_date):
            results['skipped'] += 1
            results['emails'].append({'email': user['email'], 'status': 'skipped (already sent today)'})
        else:
            threading.Thread(target=email_job.send_briefing, args=(user,), daemon=True).start()
            results['queued'] += 1
            results['emails'].append({'email': user['email'], 'status': 'queued'})

    print(f"[admin] Manual send triggered — {results['queued']} queued, {results['skipped']} skipped")
    return jsonify(results)


# ── Boot ──────────────────────────────────────────────────────────────────────

db.create_tables()

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(hourly_check, 'interval', hours=1, id='hourly_check',
                  misfire_grace_time=300)
scheduler.start()
print("[app] Scheduler started — running hourly_check every hour.")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
