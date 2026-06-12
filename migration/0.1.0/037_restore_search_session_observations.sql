-- 037_restore_search_session_observations.sql
-- Session search RPC used by SessionService.search_sessions (GET /api/sessions?q=).
-- Full-text search over cortex_session_observations.search_vector (populated by the
-- update_observation_search_vector trigger from title + content + files), grouped to
-- one row per session and ranked by best observation match.
--
-- This function previously existed only in the live database with no repo SQL;
-- the 036 rename migration's function-rewrite pass dropped it without a surviving
-- definition, so this migration restores it (and gives it a home in the repo).

BEGIN;

CREATE OR REPLACE FUNCTION public.search_session_observations(
    search_query TEXT,
    result_limit INT DEFAULT 10,
    filter_project_id UUID DEFAULT NULL
)
RETURNS TABLE (
    session_id TEXT,
    project_id UUID,
    machine_id TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    summary TEXT,
    observation_count INT,
    match_count BIGINT,
    best_rank REAL,
    matched_titles TEXT[]
)
LANGUAGE sql STABLE AS $$
    SELECT
        s.session_id,
        s.project_id,
        s.machine_id,
        s.started_at,
        s.ended_at,
        s.summary,
        s.observation_count,
        COUNT(*) AS match_count,
        MAX(ts_rank(o.search_vector, websearch_to_tsquery('english', search_query))) AS best_rank,
        (ARRAY_AGG(o.title ORDER BY ts_rank(o.search_vector, websearch_to_tsquery('english', search_query)) DESC))[1:3]
            AS matched_titles
    FROM cortex_session_observations o
    JOIN cortex_sessions s ON s.session_id = o.session_id
    WHERE o.search_vector @@ websearch_to_tsquery('english', search_query)
      AND (filter_project_id IS NULL OR o.project_id = filter_project_id)
    GROUP BY s.id, s.session_id, s.project_id, s.machine_id, s.started_at,
             s.ended_at, s.summary, s.observation_count
    ORDER BY best_rank DESC
    LIMIT result_limit;
$$;

INSERT INTO cortex_migrations (version, migration_name)
VALUES ('0.1.0', '037_restore_search_session_observations')
ON CONFLICT DO NOTHING;

COMMIT;
