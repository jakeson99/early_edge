import os
from datetime import date
from jinja2 import Environment, FileSystemLoader
import db
import perplexity_client
import claude_client
import email_client

_template_env = Environment(loader=FileSystemLoader('templates'))

BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')


def send_welcome_email(user: dict):
    """Sends a one-time welcome email immediately after signup."""
    try:
        template = _template_env.get_template('email_welcome.html')
        html = template.render(
            user=user,
            profile_url=f"{BASE_URL}/profile?email={user['email']}",
            unsubscribe_url=f"{BASE_URL}/unsubscribe?email={user['email']}",
            delete_url=f"{BASE_URL}/delete",
        )
    except Exception as e:
        print(f"[welcome] Template error for {user.get('email')}: {e}")
        return

    subject = f"Welcome to Early Edge, {user['name']} ☕"
    success = email_client.send_email(user['email'], subject, html)

    if success:
        print(f"[welcome] ✓ Welcome email sent to {user['email']}")
    else:
        print(f"[welcome] ✗ Failed to send welcome email to {user['email']}")

FINANCIAL_PHRASES = [
    "you should buy",
    "you should sell",
    "i recommend investing",
    "consider purchasing shares",
    "buy this stock",
    "sell this stock",
    "i recommend buying",
    "i recommend selling",
]


def check_content_filters(briefing: dict, user: dict) -> list:
    """Returns list of flag strings. Empty list = all checks passed."""
    flags = []
    items = briefing.get('items', [])

    # 1. Financial advice keyword filter
    for item in items:
        text = (item.get('summary', '') + ' ' + item.get('why_it_matters', '')).lower()
        for phrase in FINANCIAL_PHRASES:
            if phrase in text:
                flags.append(
                    f"Financial advice phrase in item {item.get('number', '?')}: '{phrase}'"
                )

    # 2. Source count — at least 4 distinct named publications
    sources = {item.get('source', '').strip().lower() for item in items if item.get('source')}
    if len(sources) < 4:
        flags.append(f"Only {len(sources)} distinct source(s) cited — minimum is 4")

    # 3. Length sanity check — summary must be 40–200 words
    for item in items:
        summary = item.get('summary', '')
        word_count = len(summary.split())
        if word_count < 40 or word_count > 200:
            flags.append(
                f"Item {item.get('number', '?')} summary is {word_count} words "
                f"(must be 40–200)"
            )

    # 4. Personalisation check — goal must appear/be paraphrased in ≥3 of 5 why_it_matters
    goal = (user.get('primary_goal') or '').lower()
    if goal:
        # Use significant words (>4 chars) to check for goal reference
        goal_words = {w for w in goal.split() if len(w) > 4}
        personalised_count = 0
        for item in items:
            why = item.get('why_it_matters', '').lower()
            matches = sum(1 for w in goal_words if w in why)
            if goal_words and matches >= max(2, len(goal_words) // 4):
                personalised_count += 1
        if personalised_count < 3:
            flags.append(
                f"Only {personalised_count}/5 'why it matters' lines reference the "
                f"subscriber's goal — minimum is 3"
            )

    return flags


def send_briefing(user: dict):
    today = date.today()
    local_date = today.isoformat()

    if db.has_sent_today(user['id'], local_date):
        print(f"[job] Already sent to {user['email']} today — skipping.")
        return

    print(f"[job] Generating briefing for {user['name']} ({user['email']})…")

    # ── Steps 1+2: Fetch + Personalise with up to 5 quality-check retries ───
    import time
    briefing = None
    code_flags = []
    raw_articles = None

    for attempt in range(1, 6):
        # Re-fetch from Perplexity if we have no articles or source diversity failed
        need_new_articles = raw_articles is None or any(
            'source' in f.lower() for f in code_flags
        )
        if need_new_articles:
            try:
                raw_articles = perplexity_client.fetch_articles(user, today)
                print(f"[job] Attempt {attempt}: Perplexity returned {len(raw_articles)} articles for {user['email']}")
            except Exception as e:
                print(f"[job] Attempt {attempt}: Perplexity error for {user['email']}: {e}")
                if attempt < 5:
                    time.sleep(10)
                continue

        # Personalise with Claude, passing flags from previous attempt if any
        try:
            briefing = claude_client.personalise_briefing(
                user, raw_articles, today,
                fix_flags=code_flags if code_flags else None
            )
            if not isinstance(briefing, dict) or 'items' not in briefing:
                print(f"[job] Attempt {attempt}: unexpected briefing structure for {user['email']} — retrying")
                briefing = None
                continue
        except Exception as e:
            print(f"[job] Attempt {attempt}: Claude error for {user['email']}: {e}")
            briefing = None
            continue

        # Check quality filters
        code_flags = check_content_filters(briefing, user)
        if not code_flags:
            print(f"[job] Attempt {attempt}: briefing passed all checks for {user['email']}")
            break

        print(f"[job] Attempt {attempt}: flags for {user['email']}: {code_flags} — retrying with fixes")
        if attempt < 5:
            time.sleep(5)

    if not briefing or code_flags:
        print(f"[job] Failed to produce clean briefing for {user['email']} after 5 attempts — aborting")
        if briefing:
            db.log_flagged_briefing(user['id'], local_date, code_flags, briefing)
        return

    # ── Render and send ────────────────────────────────────────────────────
    try:
        template = _template_env.get_template('email.html')
        html = template.render(
            user=user,
            briefing=briefing,
            date_str=today.strftime('%A, %d %B %Y'),
            unsubscribe_url=f"{BASE_URL}/unsubscribe?email={user['email']}",
            profile_url=f"{BASE_URL}/profile?email={user['email']}",
        )
    except Exception as e:
        print(f"[job] Template error for {user['email']}: {e}")
        return

    subject = f"Your Early Edge, {user['name']} — {today.strftime('%a %d %b')}"
    success = email_client.send_email(user['email'], subject, html)

    if success:
        db.record_send(user['id'], local_date)
        print(f"[job] ✓ Sent to {user['email']}")
    else:
        print(f"[job] ✗ Failed to send to {user['email']}")
