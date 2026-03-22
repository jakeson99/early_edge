import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get('DATABASE_URL')


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def create_tables():
    conn = get_db()
    cur = get_cursor(conn)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                  SERIAL PRIMARY KEY,
            name                TEXT NOT NULL,
            email               TEXT NOT NULL UNIQUE,
            role                TEXT,
            industry            TEXT,
            career_stage        TEXT,
            primary_goal        TEXT,
            timeline            TEXT,
            secondary_goals     TEXT,
            admired_orgs        TEXT,
            domains             TEXT,
            knowledge_gaps      TEXT,
            skills              TEXT,
            regions             TEXT,
            countries           TEXT,
            intl_ties           TEXT,
            culture_score       INTEGER DEFAULT 2,
            engage_style        TEXT,
            depth_score         INTEGER DEFAULT 2,
            prompts_freq        TEXT DEFAULT 'Yes, every day',
            exclusions          TEXT,
            delivery_time       TEXT DEFAULT '7:00 – 8:00 AM',
            delivery_days       TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri',
            timezone            TEXT DEFAULT 'Europe/London',
            extra_notes         TEXT,
            consent_timestamp   TEXT,
            consent_version     TEXT DEFAULT '1.0',
            marketing_consent   INTEGER DEFAULT 0,
            deletion_requested  INTEGER DEFAULT 0,
            created_at          TIMESTAMP DEFAULT NOW(),
            active              INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sends (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            sent_date   TEXT NOT NULL,
            sent_at     TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, sent_date)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS flagged_briefings (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL,
            flagged_date TEXT NOT NULL,
            flags        TEXT NOT NULL,
            content      TEXT,
            flagged_at   TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


def insert_user(data: dict) -> int:
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("""
        INSERT INTO users
            (name, email, role, industry, career_stage, primary_goal, timeline,
             secondary_goals, admired_orgs, domains, knowledge_gaps, skills, regions,
             countries, intl_ties, culture_score, engage_style, depth_score, prompts_freq,
             exclusions, delivery_time, delivery_days, timezone, extra_notes,
             consent_timestamp, consent_version, marketing_consent)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(email) DO UPDATE SET
            name=EXCLUDED.name, role=EXCLUDED.role, industry=EXCLUDED.industry,
            career_stage=EXCLUDED.career_stage, primary_goal=EXCLUDED.primary_goal,
            timeline=EXCLUDED.timeline, secondary_goals=EXCLUDED.secondary_goals,
            admired_orgs=EXCLUDED.admired_orgs, domains=EXCLUDED.domains,
            knowledge_gaps=EXCLUDED.knowledge_gaps, skills=EXCLUDED.skills,
            regions=EXCLUDED.regions, countries=EXCLUDED.countries,
            intl_ties=EXCLUDED.intl_ties, culture_score=EXCLUDED.culture_score,
            engage_style=EXCLUDED.engage_style, depth_score=EXCLUDED.depth_score,
            prompts_freq=EXCLUDED.prompts_freq, exclusions=EXCLUDED.exclusions,
            delivery_time=EXCLUDED.delivery_time, delivery_days=EXCLUDED.delivery_days,
            timezone=EXCLUDED.timezone, extra_notes=EXCLUDED.extra_notes,
            consent_timestamp=EXCLUDED.consent_timestamp,
            consent_version=EXCLUDED.consent_version,
            marketing_consent=EXCLUDED.marketing_consent
        RETURNING id
    """, (
        data.get('name'), data.get('email'), data.get('role'),
        data.get('industry'), data.get('career_stage'), data.get('primary_goal'),
        data.get('timeline'), data.get('secondary_goals'), data.get('admired_orgs'),
        data.get('domains'), data.get('knowledge_gaps'), data.get('skills'),
        data.get('regions'), data.get('countries'), data.get('intl_ties'),
        int(data.get('culture_score') or 2),
        data.get('engage_style'),
        int(data.get('depth_score') or 2),
        data.get('prompts_freq') or 'Yes, every day',
        data.get('exclusions'), data.get('delivery_time'),
        data.get('delivery_days'), data.get('timezone') or 'Europe/London',
        data.get('extra_notes'),
        data.get('consent_timestamp'),
        data.get('consent_version', '1.0'),
        1 if data.get('marketing_consent') else 0,
    ))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row['id']


def get_active_users() -> list:
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("SELECT * FROM users WHERE active = 1 AND deletion_requested = 0")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("SELECT * FROM users WHERE email = %s", (email.lower(),))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def has_sent_today(user_id: int, local_date: str) -> bool:
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(
        "SELECT 1 FROM sends WHERE user_id = %s AND sent_date = %s",
        (user_id, local_date)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row is not None


def record_send(user_id: int, local_date: str):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(
        "INSERT INTO sends (user_id, sent_date) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user_id, local_date)
    )
    conn.commit()
    cur.close()
    conn.close()


def log_flagged_briefing(user_id: int, flagged_date: str, flags: list, content: dict):
    import json
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(
        "INSERT INTO flagged_briefings (user_id, flagged_date, flags, content) VALUES (%s, %s, %s, %s)",
        (user_id, flagged_date, json.dumps(flags), json.dumps(content))
    )
    conn.commit()
    cur.close()
    conn.close()


def deactivate_user(user_id: int):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("UPDATE users SET active = 0 WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


def delete_user_data(user_id: int):
    """Wipe all personal data."""
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("""
        UPDATE users SET
            name = '[deleted]',
            email = '[deleted-' || id::text || ']',
            role = NULL, industry = NULL, career_stage = NULL,
            primary_goal = NULL, timeline = NULL, secondary_goals = NULL,
            admired_orgs = NULL, domains = NULL, knowledge_gaps = NULL,
            skills = NULL, regions = NULL, countries = NULL,
            intl_ties = NULL, exclusions = NULL, extra_notes = NULL,
            active = 0,
            deletion_requested = 1
        WHERE id = %s
    """, (user_id,))
    conn.commit()
    cur.close()
    conn.close()
