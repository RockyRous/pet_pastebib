CREATE DATABASE pastebin_hash;
-- CREATE USER my_user WITH ENCRYPTED PASSWORD 'my_password';
-- GRANT ALL PRIVILEGES ON DATABASE my_database TO my_user;
SELECT EXISTS (
                SELECT 1
                FROM pg_class
                WHERE relkind = 'S'
                  AND relname = 'my_sequence'
            );