import os
import sqlite3
from contextlib import closing

db_path = os.getenv("DB_PATH", "bot.db")


def init_db():
    with closing(sqlite3.connect(db_path)) as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS verify(
                roblox_name TEXT,
                roblox_id TEXT UNIQUE,
                discord_name TEXT,
                discord_id TEXT UNIQUE
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS role_mappings(
                guild_id TEXT,
                achievement TEXT,
                role_id TEXT,
                PRIMARY KEY(guild_id, achievement)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS booster_claims(
                discord_id TEXT PRIMARY KEY,
                last_claim INTEGER
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS pending_rewards(
                discord_id TEXT,
                roblox_id TEXT,
                amount INTEGER,
                delivered INTEGER DEFAULT 0
            )
        """)
        c.execute("""
CREATE TABLE IF NOT EXISTS whitelist_applications(
    discord_id TEXT PRIMARY KEY,
    started_at INTEGER,
    current_question INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
)
""")

        c.execute("""
CREATE TABLE IF NOT EXISTS whitelist_answers(
    discord_id TEXT,
    question_number INTEGER,
    question TEXT,
    answer TEXT,
    PRIMARY KEY(discord_id, question_number)
)
""")

        c.execute("""
CREATE TABLE IF NOT EXISTS whitelist_reviews(
    discord_id TEXT PRIMARY KEY,
    status TEXT,
    reviewer_id TEXT,
    reason TEXT,
    reviewed_at INTEGER
)
""")

        c.execute("""
CREATE TABLE IF NOT EXISTS whitelist_review_messages(
    message_id TEXT PRIMARY KEY,
    applicant_discord_id TEXT NOT NULL,
    created_at INTEGER
)
""")

        c.execute("""
CREATE TABLE IF NOT EXISTS oauth_states(
    state TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL
)
""")
        conn.commit()


def query_one(query: str, params=()):
    with closing(sqlite3.connect(db_path)) as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchone()


def execute(query: str, params=()):
    with closing(sqlite3.connect(db_path)) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c.rowcount