-- Add execution ownership for Worker recovery without changing existing runs.
BEGIN;

ALTER TABLE test_runs
    ADD COLUMN execution_token text,
    ADD COLUMN lease_expires_at timestamptz,
    ADD CONSTRAINT test_runs_execution_lease_consistent CHECK (
        (execution_token IS NULL) = (lease_expires_at IS NULL)
        AND (execution_token IS NULL OR status = 'running')
    );

CREATE INDEX test_runs_expired_lease ON test_runs (lease_expires_at, run_id)
    WHERE status = 'running';

CREATE INDEX run_events_verified_cases ON run_events (run_id, case_id)
    WHERE type = 'case.verified';

CREATE INDEX run_artifacts_expiration ON run_artifacts (expires_at, artifact_id)
    WHERE storage_key IS NOT NULL AND expires_at IS NOT NULL;

INSERT INTO schema_migrations (version, filename)
VALUES (2, '0002_run_execution_lease.sql');

COMMIT;
