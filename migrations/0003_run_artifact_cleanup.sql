BEGIN;

CREATE TABLE deleted_run_artifacts (
    storage_key text PRIMARY KEY,
    run_id text NOT NULL,
    mime_type text NOT NULL,
    retry_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX deleted_run_artifacts_due ON deleted_run_artifacts (retry_at, storage_key);
CREATE INDEX deleted_run_artifacts_run ON deleted_run_artifacts (run_id);

INSERT INTO schema_migrations (version, filename)
VALUES (3, '0003_run_artifact_cleanup.sql');

COMMIT;
