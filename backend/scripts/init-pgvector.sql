-- Runs once, automatically, the first time the db container's data volume is
-- created (Postgres's docker-entrypoint-initdb.d convention). Not re-run on
-- restarts, so this alone won't fix a volume created before this file existed
-- — drop the volume (docker-compose down -v) if you need it to re-run.
CREATE EXTENSION IF NOT EXISTS vector;
