-- Runs once when the demo database is first created.
--
-- Two separate roles, each with only what it needs:
--   victim_app     the application itself (owns its database, nothing else)
--   autosre_agent  AutoSRE: can READ activity stats (pg_monitor), END other
--                  non-superuser sessions (pg_signal_backend), and use the
--                  reserved connection slots so it can still log in when the
--                  application has exhausted every normal slot.

CREATE ROLE victim_app LOGIN PASSWORD 'victim_app_pw';
ALTER DATABASE victim_db OWNER TO victim_app;

CREATE ROLE autosre_agent LOGIN PASSWORD 'autosre_agent_pw';
GRANT pg_monitor TO autosre_agent;
GRANT pg_signal_backend TO autosre_agent;
GRANT pg_use_reserved_connections TO autosre_agent;
GRANT CONNECT ON DATABASE victim_db TO autosre_agent;
