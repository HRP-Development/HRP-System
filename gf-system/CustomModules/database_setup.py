import sqlite3


class database():
    def __init__(self, c: sqlite3.Cursor):
        self.c = c

    async def setup_database(self):
        self.c.executescript('''
        CREATE TABLE IF NOT EXISTS "SERVER" (
	        "ID"	INTEGER,
	        "GUILD"	INTEGER NOT NULL,
	        "HOST"	TEXT NOT NULL,
	        "PORT"	INTEGER NOT NULL,
	        "PASS"	TEXT NOT NULL,
	        PRIMARY KEY("ID" AUTOINCREMENT)
        );
        CREATE TABLE IF NOT EXISTS "EMBEDS" (
	        "ID"	        INTEGER,
	        "GUILD"	        INTEGER NOT NULL,
	        "CHANNEL"	    INTEGER NOT NULL,
	        "MESSAGE_ID"	INTEGER NOT NULL,
            "SERVER_ID"	    INTEGER UNIQUE,
	        PRIMARY KEY("ID" AUTOINCREMENT)
        );
        CREATE TABLE IF NOT EXISTS "GUILD_SETTINGS" (
            "GUILD_ID"	        INTEGER NOT NULL,
            "welcome_channel"	INTEGER,
            "leave_channel"	    INTEGER,
            "logging_channel"	INTEGER,
            "announce_channel"  INTEGER,
            "team_update_channel"	INTEGER,
            "free_games_channel" INTEGER,   
            "team_list_channel"	INTEGER,
            PRIMARY KEY("GUILD_ID")
        );
        CREATE TABLE IF NOT EXISTS "TICKET_SYSTEM" (
            "ID"	        INTEGER,
            "GUILD_ID"	        INTEGER NOT NULL,
            "CHANNEL"	    INTEGER NOT NULL,
            "EMBED_ID"      INTEGER,
            PRIMARY KEY("ID" AUTOINCREMENT)
        );
        CREATE TABLE IF NOT EXISTS "warns" (
            "ID"	        INTEGER,
            "GUILD_ID"	    INTEGER NOT NULL,
            "USER_ID"	    INTEGER NOT NULL,
            "WARNED_BY"	    INTEGER NOT NULL,
            "REASON"	    TEXT NOT NULL,
            "TIME"	        INTEGER NOT NULL,
            PRIMARY KEY("ID" AUTOINCREMENT)
        );
        CREATE TABLE IF NOT EXISTS "CREATED_TICKETS" (
            "ID"            INTEGER,
            "USER_ID"       INTEGER NOT NULL,
            "CHANNEL_ID"    INTEGER NOT NULL,
            "GUILD_ID"      INTEGER NOT NULL,
            "CATEGORY"      TEXT NOT NULL,
            PRIMARY KEY("ID" AUTOINCREMENT)            
        );
        CREATE TABLE IF NOT EXISTS "SERVER" (
	        "ID"	INTEGER,
	        "GUILD"	INTEGER NOT NULL,
	        "HOST"	TEXT NOT NULL,
	        "PORT"	INTEGER NOT NULL,
	        "PASS"	TEXT NOT NULL,
	        PRIMARY KEY("ID" AUTOINCREMENT)
        );
        CREATE TABLE IF NOT EXISTS "EMBEDS" (
	        "ID"	        INTEGER,
	        "GUILD"	        INTEGER NOT NULL,
	        "CHANNEL"	    INTEGER NOT NULL,
	        "MESSAGE_ID"	INTEGER NOT NULL,
            "SERVER_ID"	    INTEGER UNIQUE,
	        PRIMARY KEY("ID" AUTOINCREMENT)
        );
        CREATE TABLE IF NOT EXISTS "free_games" (
            "ID"	        INTEGER,
            "TITEL_ID"	    TEXT NOT NULL, 
            "DATUM"	        INTEGER NOT NULL,
            PRIMARY KEY("ID" AUTOINCREMENT)                      
        );
        CREATE TABLE IF NOT EXISTS panels (
                guild_id INTEGER PRIMARY KEY,
                panel_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS temp_bans (
            guild_id INTEGER,
            user_id INTEGER,
            unban_time INTEGER
        );

        CREATE TABLE IF NOT EXISTS processing_joined (
            guild_id INTEGER,
            user_id INTEGER,
            join_time INTEGER
        );
        CREATE TABLE IF NOT EXISTS servers (
            guild_id INTEGER PRIMARY KEY,
            verify_channel INTEGER,
            verify_role INTEGER,
            log_channel INTEGER,
            timeout INTEGER,
            action TEXT,
            ban_time INTEGER
        )
        ''')

        queries = [
            'ALTER TABLE TICKET_SYSTEM ADD COLUMN "ARCHIVE_CHANNEL_ID" INTEGER;',
            'ALTER TABLE TICKET_SYSTEM ADD COLUMN "SUPPORT_ROLE_ID" INTEGER;',
            'ALTER TABLE servers ADD COLUMN "account_age_min" INTEGER;',
            ]
        for query in queries:
            try:
                self.c.execute(query)
            except Exception:
                pass