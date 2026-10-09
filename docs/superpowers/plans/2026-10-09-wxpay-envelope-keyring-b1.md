# WeChat Pay Secret Envelope/Keyring B1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned Fernet envelope and root-managed immutable keyring with compatible legacy reads, fail-closed writes, readiness parity, and MySQL-safe `TEXT` schema convergence.

**Architecture:** A focused `wxpay_secret_crypto` module owns keyring loading, value classification, field validation, encryption, and decryption. Existing payment runtime, readiness, and Super Admin write paths call that single contract; no migration runner or production key is introduced. A guarded Alembic migration and schema compatibility update converge `wx_private_key` to `TEXT`.

**Tech Stack:** Python 3.10, FastAPI, cryptography/Fernet, SQLAlchemy, Alembic, MySQL 5.7, pytest, GitHub Actions.

---

### Task 1: Freeze B1 contracts with failing tests

**Files:**
- Create: `saas-base/tests/test_wxpay_secret_envelope.py`
- Create: `saas-base/tests/test_wxpay_secret_schema_mysql.py`
- Modify: `.github/workflows/backend-candidate-certification.yml`

- [ ] Add tests for envelope parsing, strict key IDs, immutable keyring validation, legacy plaintext/raw-Fernet compatibility, strict mode, corruption, unknown keys, double encryption, rotation, concurrency, field validators, secret-free errors, and capacity boundaries.
- [ ] Add integration tests proving Super Admin writes only envelopes when enabled, rejects writes when disabled/missing, preserves Step-up, and keeps tenant isolation.
- [ ] Add runtime/readiness tests proving both paths use the same classification and validation contract without leaking secrets.
- [ ] Add a MySQL 5.7 CI service job that upgrades from the previous Alembic revision, verifies `TEXT`, reruns upgrade idempotently, and checks no truncation.
- [ ] Commit and push the test-only RED candidate.
- [ ] Dispatch Backend Candidate Certification and record expected Gate A failure caused only by the missing B1 implementation.

### Task 2: Implement the envelope and immutable keyring

**Files:**
- Create: `saas-base/app/core/wxpay_secret_crypto.py`
- Modify: `saas-base/app/config.py`
- Modify: `saas-base/app/core/crypto.py`

- [ ] Define `SecretField`, `SecretFormat`, sanitized exception types, and `enc:v1:<key-id>:<token>` parsing.
- [ ] Load `/run/secrets/saas-base/wxpay-keyring.json` at startup/use into an immutable cached snapshot; validate exact JSON keys, owner/mode, unique IDs, one active encrypt/decrypt key, Fernet keys, algorithms, and usages.
- [ ] Implement APIv3 and RSA PEM validation, compatible classified reads, strict reads, raw-Fernet legacy reads, and versioned strict encryption.
- [ ] Make `ENVELOPE_WRITE_ENABLED` default false; disabled writes reject and never fall back to plaintext/raw Fernet.
- [ ] Keep legacy crypto entry points as narrow compatibility wrappers so existing imports do not bypass the new contract.

### Task 3: Integrate payment runtime, Readiness, and Super Admin

**Files:**
- Modify: `saas-base/app/services/wxpay_service.py`
- Modify: `saas-base/app/services/payment_readiness_service.py`
- Modify: `saas-base/app/api/v1/super_admin.py`

- [ ] Decrypt and validate both Tenant secrets before SDK construction; on any secret error leave the SDK disabled without logging secret material or provider exception bodies.
- [ ] Replace readiness's independent Fernet implementation with the shared evaluator while keeping static-valid state `UNKNOWN`, invalid keyring not ready, and no remote WeChat call.
- [ ] Preserve Step-up, field-aware PATCH, row lock, copy disablement, verification invalidation, and transaction atomicity.
- [ ] Remove the obsolete private-key 4096-character envelope rejection and apply the shared capacity contract.

### Task 4: Converge schema safely

**Files:**
- Modify: `saas-base/app/models/tenant.py`
- Modify: `saas-base/app/core/schema_compat.py`
- Create: `saas-base/alembic/versions/20261009_0001_widen_wxpay_private_key_to_text.py`

- [ ] Declare `wx_private_key` as SQLAlchemy `Text`.
- [ ] Make AUTO_CREATE_TABLES/schema compatibility create or widen only this column to `TEXT`, preserving nullability and data.
- [ ] Add an Alembic revision after `20260830_0001` that inspects MySQL and changes `VARCHAR(4096)` to `TEXT`, while treating an existing `TEXT` column as a safe no-op.
- [ ] Keep downgrade fail-safe: only narrow back when every stored value is at most 4096 characters; otherwise abort rather than truncate.

### Task 5: GREEN certification and candidate freeze

**Files:**
- Modify only files listed in Tasks 1–4 plus this plan.

- [ ] Review the diff for API, Billing, callback-route, payment-timing, production-secret, and migration scope drift.
- [ ] Commit implementation without amend/rebase/force push.
- [ ] Push `candidate/wxpay-envelope-keyring-b1` normally.
- [ ] Dispatch Backend Candidate Certification for the exact candidate SHA.
- [ ] Require Gate A, Gate B, Backend Full, certification summary, Alembic migration gate, and isolated MySQL schema gate to succeed on the same SHA.
- [ ] Confirm no local test/build, no production access, no key generation/install, and no production data migration occurred.
