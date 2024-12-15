CREATE DATABASE pastebin_text;
-- CREATE USER my_user WITH ENCRYPTED PASSWORD 'my_password';
-- GRANT ALL PRIVILEGES ON DATABASE my_database TO my_user;
CREATE TABLE IF NOT EXISTS posts (
                hash TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                ttl INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);