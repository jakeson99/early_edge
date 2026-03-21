import sqlite3
import os

DB_PATH = os.environ.get('DB_PATH', 'early_edge.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            email           TEXT NOT NULL UNIQUE,
            role            TEXT,
            industry        TEXT,
            career_stage    TEXT,
            primary_goal    TEXT,
            timeline        TEXT,
            secondary_goals TEXT,
            admired_orgs    TEXT,
            domains         TEXT,
            knowledge_gaps  TEXT,
            skills          TEXT,
            regions         TEXT,
            countries       TEXT,
            intl_ties       TEXT,
            culture_score   INTEGER DEFAULT 2,
            engage_style    TEXT,
            depth_score     INTEGER DEFAULT 2,
            prompts_freq    TEXT DEFAULT 'Yes, every day',
            exclusions      TEXT,
            delivery_time   TEXT DEFAULT '7:00 – 8:00 AM',
            delivery_days   TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri',
            timezone        TEXT DEFAULT 'Europe/London',
            extra_notes     TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            active          INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sends (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            sent_date   TEXT NOT NULL,
            sent_at     TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, sent_date)
        );
    """)
    conn.commit()
    conn.close()


def insert_user(data: dict) -> int:
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO users
            (name, email, role, industry, career_stage, primary_goal, timeline,
             secondary_goals, admired_orgs, domains, knowledge_gaps, skills, regions,
             countries, intl_ties, culture_score, engage_style, depth_score, prompts_freq,
             exclusions, delivery_time, delivery_days, timezone, extra_notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET
            name=excluded.name, role=excluded.role, industry=excluded.industry,
            career_stage=excluded.career_stage, primary_goal=excluded.primary_goal,
            timeline=excluded.timeline, secondary_goals=excluded.secondary_goals,
            admired_orgs=excluded.admired_orgs, domains=excluded.domains,
            knowledge_gaps=excluded.knowledge_gaps, skills=excluded.skills,
            regions=excluded.regions, countries=excluded.countries,
            intl_ties=excluded.intl_ties, culture_score=excluded.culture_score,
            engage_style=excluded.engage_style, depth_score=excluded.depth_score,
            prompts_freq=excluded.prompts_freq, exclusions=excluded.exclusions,
            delivery_time=excluded.delivery_time, delivery_days=excluded.delivery_days,
            timezone=excluded.timezone, extra_notes=excluded.extra_notes
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
    ))
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id


def get_active_users() -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM users WHERE active = 1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_sent_today(user_id: int, local_date: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM sends WHERE user_id = ? AND sent_date = ?",
        (user_id, local_date)
    ).fetchone()
    conn.close()
    return row is not None


def record_send(user_id: int, local_date: str):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO sends (user_id, sent_date) VALUES (?, ?)",
        (user_id, local_date)
    )
    conn.commit()
    conn.close()
