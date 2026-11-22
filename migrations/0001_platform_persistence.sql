-- C6 baseline for an empty PostgreSQL 17 database.
BEGIN;

CREATE TABLE schema_migrations (
    version integer PRIMARY KEY CHECK (version > 0),
    filename text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE test_runs (
    run_id text PRIMARY KEY,
    owner_id text NOT NULL,
    request jsonb NOT NULL CHECK (
        jsonb_typeof(request) = 'object' AND NOT (request ? 'credential_ref')
    ),
    credential_ref text,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'errored', 'cancelled')),
    verdict text,
    error jsonb CHECK (jsonb_typeof(error) = 'object'),
    total_cases integer,
    completed_cases integer NOT NULL DEFAULT 0 CHECK (completed_cases >= 0),
    cancellation_requested boolean NOT NULL DEFAULT false,
    last_event_sequence bigint NOT NULL DEFAULT 0
        CHECK (last_event_sequence BETWEEN 0 AND 9007199254740991),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    finished_at timestamptz,
    CHECK (
        (status = 'succeeded' AND verdict IS NOT NULL
            AND verdict IN ('passed', 'failed', 'blocked', 'inconclusive'))
        OR (status <> 'succeeded' AND verdict IS NULL)
    ),
    CHECK ((status = 'errored') = (error IS NOT NULL)),
    CHECK ((status IN ('succeeded', 'errored', 'cancelled')) = (finished_at IS NOT NULL)),
    CHECK (status <> 'queued' OR started_at IS NULL),
    CHECK (status NOT IN ('running', 'succeeded') OR started_at IS NOT NULL),
    CHECK (status <> 'cancelled' OR cancellation_requested),
    CHECK (status <> 'succeeded' OR NOT cancellation_requested),
    CHECK (
        (total_cases IS NULL AND completed_cases = 0)
        OR (total_cases IS NOT NULL AND total_cases >= completed_cases)
    )
);

CREATE INDEX test_runs_owner_listing ON test_runs
    (owner_id, created_at DESC, run_id DESC);
CREATE INDEX test_runs_queued ON test_runs (created_at, run_id)
    WHERE status = 'queued';

CREATE TABLE run_events (
    run_id text NOT NULL REFERENCES test_runs ON DELETE CASCADE,
    sequence bigint NOT NULL CHECK (sequence BETWEEN 1 AND 9007199254740991),
    event_id text NOT NULL,
    schema_version smallint NOT NULL CHECK (schema_version = 1),
    type text NOT NULL CHECK (
        type IN (
            'run.started', 'plan.created', 'case.started', 'agent.step.started',
            'tool.called', 'tool.completed', 'case.verified', 'report.generated',
            'run.completed', 'run.failed', 'run.cancelled'
        )
    ),
    occurred_at timestamptz NOT NULL,
    case_id text,
    step_id text,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (run_id, sequence),
    UNIQUE (run_id, event_id),
    CHECK (step_id IS NULL OR case_id IS NOT NULL)
);

CREATE UNIQUE INDEX run_events_one_terminal ON run_events (run_id)
    WHERE type IN ('run.completed', 'run.failed', 'run.cancelled');

CREATE TABLE run_reports (
    run_id text PRIMARY KEY REFERENCES test_runs ON DELETE CASCADE,
    result jsonb NOT NULL CHECK (jsonb_typeof(result) = 'object'),
    published_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE run_artifacts (
    artifact_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES test_runs ON DELETE CASCADE,
    case_id text,
    step_id text,
    tool_call_id text,
    kind text NOT NULL,
    mime_type text NOT NULL,
    captured_at timestamptz NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    storage_key text UNIQUE,
    expires_at timestamptz,
    purged_at timestamptz,
    CHECK (step_id IS NULL OR case_id IS NOT NULL),
    CHECK (
        (kind, mime_type) IN (
            ('observation', 'application/json'),
            ('screenshot', 'image/png'),
            ('playwright_trace', 'application/zip'),
            ('test_report', 'application/json')
        )
    ),
    CHECK ((purged_at IS NULL) = (storage_key IS NOT NULL)),
    CHECK (purged_at IS NULL OR (expires_at IS NOT NULL AND purged_at >= expires_at))
);

CREATE INDEX run_artifacts_run ON run_artifacts (run_id);

INSERT INTO schema_migrations (version, filename)
VALUES (1, '0001_platform_persistence.sql');

COMMIT;
