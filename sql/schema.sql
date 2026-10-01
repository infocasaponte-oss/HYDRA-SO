-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
-- HYDRA Cognitive Engine - PostgreSQL schema (idempotent).

CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL,
    request         JSONB NOT NULL,
    route           JSONB,
    final_response  JSONB
);

CREATE TABLE IF NOT EXISTS events (
    id          UUID PRIMARY KEY,
    task_id     UUID NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    event_type  TEXT NOT NULL,
    source      TEXT NOT NULL,
    payload     JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS events_task_idx ON events (task_id, created_at);

CREATE TABLE IF NOT EXISTS memories (
    id                UUID PRIMARY KEY,
    memory_type       TEXT NOT NULL,
    content           JSONB NOT NULL,
    text              TEXT NOT NULL,
    confidence        DOUBLE PRECISION,
    status            TEXT NOT NULL DEFAULT 'unverified',
    importance        DOUBLE PRECISION,
    embedding         DOUBLE PRECISION[],
    conflicts_with    UUID[] NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL,
    last_accessed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS memories_type_idx ON memories (memory_type, created_at DESC);

CREATE TABLE IF NOT EXISTS inference_runs (
    id              UUID PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL,
    task_id         UUID NOT NULL,
    task_type       TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    role            TEXT NOT NULL,
    latency_ms      DOUBLE PRECISION,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    success         BOOLEAN,
    verifier_score  DOUBLE PRECISION,
    user_feedback   DOUBLE PRECISION,
    complexity      DOUBLE PRECISION,
    mode            TEXT,
    arm             TEXT,
    task_confidence DOUBLE PRECISION
);
ALTER TABLE inference_runs ADD COLUMN IF NOT EXISTS complexity DOUBLE PRECISION;
ALTER TABLE inference_runs ADD COLUMN IF NOT EXISTS mode TEXT;
ALTER TABLE inference_runs ADD COLUMN IF NOT EXISTS arm TEXT;
ALTER TABLE inference_runs ADD COLUMN IF NOT EXISTS task_confidence DOUBLE PRECISION;
CREATE INDEX IF NOT EXISTS inference_runs_model_idx ON inference_runs (model_id, task_type);
CREATE INDEX IF NOT EXISTS inference_runs_task_idx ON inference_runs (task_id);

CREATE TABLE IF NOT EXISTS model_metrics (
    model_id        TEXT NOT NULL,
    task_type       TEXT NOT NULL,
    runs            INTEGER NOT NULL,
    success_rate    DOUBLE PRECISION,
    avg_latency_ms  DOUBLE PRECISION,
    avg_quality     DOUBLE PRECISION,
    PRIMARY KEY (model_id, task_type)
);


-- =====================================================================================
-- Execution Fabric (hydra.cluster.fabric_pg.PostgresWorkQueue, which also creates these tables).
-- Shared by every gateway and worker: leases, retries, dead letters, idempotency, checkpoints.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS fabric_work (
    id            TEXT PRIMARY KEY,
    capability    TEXT NOT NULL,
    priority      INTEGER NOT NULL,
    status        TEXT NOT NULL,
    available_at  DOUBLE PRECISION NOT NULL,
    lease_expires DOUBLE PRECISION,
    idem          TEXT NOT NULL,
    body          JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS fabric_work_claim ON fabric_work (status, capability, priority, available_at);
CREATE INDEX IF NOT EXISTS fabric_work_open_idem ON fabric_work (idem) WHERE status IN ('queued', 'leased');
CREATE TABLE IF NOT EXISTS fabric_idempotency (
    key    TEXT PRIMARY KEY,
    result JSONB NOT NULL,
    at     DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS fabric_checkpoints (
    task_id TEXT NOT NULL,
    step    INTEGER NOT NULL,
    state   JSONB NOT NULL,
    at      DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (task_id, step)
);


-- =====================================================================================
-- HYDRA 1.0 planes: RESERVED SCHEMA, NOT WIRED YET.
-- As of 1.1 the ledger, IP registry, artifacts, corpus and World Model persist ONLY in the local
-- file stores under HYDRA_DATA_DIR; no code reads or writes the tables below. They document the
-- target multi-node layout (docs/AUDITORIA_INTEGRAL_REPO_2026-10-01.md, section 5). Do not rely
-- on them for audit or recovery until a PostgreSQL repository is implemented for each plane.
-- =====================================================================================

-- Append-only, hash-chained, signed provenance / IP ledger.
CREATE TABLE IF NOT EXISTS ip_events (
    sequence_id        BIGSERIAL PRIMARY KEY,
    event_id           UUID NOT NULL UNIQUE,
    project_id         TEXT NOT NULL DEFAULT 'hydra',
    event_type         TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL,
    actor_type         TEXT NOT NULL,
    actor_id           TEXT NOT NULL,
    object_type        TEXT NOT NULL DEFAULT '',
    object_id          TEXT NOT NULL DEFAULT '',
    payload            JSONB NOT NULL,
    previous_hash      TEXT,
    event_hash         TEXT NOT NULL,
    signature          TEXT,
    signing_key_id     TEXT,
    confidentiality    TEXT NOT NULL,
    created_by_service TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ip_events_object ON ip_events (object_type, object_id);

CREATE OR REPLACE FUNCTION hydra_ledger_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ip_events is append-only: use an EVENT_CORRECTION event';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ip_events_no_update ON ip_events;
CREATE TRIGGER ip_events_no_update BEFORE UPDATE OR DELETE ON ip_events
    FOR EACH ROW EXECUTE FUNCTION hydra_ledger_immutable();

CREATE TABLE IF NOT EXISTS ledger_anchors (
    first_sequence   BIGINT NOT NULL,
    last_sequence    BIGINT NOT NULL,
    merkle_root      TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    external_timestamp_ref TEXT,
    PRIMARY KEY (first_sequence, last_sequence)
);

CREATE TABLE IF NOT EXISTS inventions (
    invention_id     TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    status           TEXT NOT NULL,
    conceived_at     TIMESTAMPTZ,
    technical_problem TEXT,
    technical_solution TEXT,
    technical_effect TEXT,
    confidentiality  TEXT,
    record           JSONB NOT NULL
);

-- Content-addressed artifacts (blobs live in object storage by sha256).
CREATE TABLE IF NOT EXISTS artifacts (
    id               UUID PRIMARY KEY,
    artifact_type    TEXT NOT NULL,
    sha256           TEXT NOT NULL,
    uri              TEXT NOT NULL,
    media_type       TEXT,
    size_bytes       BIGINT,
    metadata         JSONB NOT NULL DEFAULT '{}',
    parents          JSONB NOT NULL DEFAULT '[]',
    created_by_task  UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS artifacts_sha ON artifacts (sha256);

-- Corpus Engine (canonical records; training exports are Parquet/JSONL releases).
CREATE TABLE IF NOT EXISTS corpus_records (
    id               TEXT PRIMARY KEY,
    record_type      TEXT NOT NULL,
    content          JSONB NOT NULL,
    quality          DOUBLE PRECISION,
    verification     DOUBLE PRECISION,
    rights           JSONB NOT NULL,
    privacy          JSONB NOT NULL,
    provenance       JSONB NOT NULL,
    training_status  TEXT NOT NULL,
    classification   TEXT NOT NULL,
    tenant_id        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS corpus_lineage (
    parent_id        TEXT NOT NULL,
    child_id         TEXT NOT NULL,
    transformation   TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- World Model (bitemporal relations, beliefs with evidence).
CREATE TABLE IF NOT EXISTS world_entities (
    id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, canonical_name TEXT, attributes JSONB NOT NULL DEFAULT '{}',
    aliases JSONB NOT NULL DEFAULT '[]', visibility TEXT NOT NULL, confidence DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS world_relations (
    id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, predicate TEXT NOT NULL, object_id TEXT NOT NULL,
    valid_from TIMESTAMPTZ, valid_until TIMESTAMPTZ, recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confidence DOUBLE PRECISION, evidence_ids JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS world_rel_subject ON world_relations (subject_id, predicate);
CREATE TABLE IF NOT EXISTS beliefs (
    id TEXT PRIMARY KEY, proposition TEXT NOT NULL, subject_id TEXT, predicate TEXT, object_value JSONB,
    confidence DOUBLE PRECISION, status TEXT NOT NULL, supporting JSONB NOT NULL DEFAULT '[]',
    contradicting JSONB NOT NULL DEFAULT '[]', valid_from TIMESTAMPTZ, valid_until TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS world_deltas (
    world_version BIGSERIAL PRIMARY KEY, delta JSONB NOT NULL, source TEXT, applied_at TIMESTAMPTZ DEFAULT now()
);
