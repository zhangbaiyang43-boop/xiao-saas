# WeChat Pay secret migration (B4): production authorization model and runbook

Status: **tooling certified, migration NOT authorized.** This document describes how a production
migration would be authorized and run. Nothing here issues, signs or runs a production grant.
Production at the time of writing: backend `995b425e`, Keyring loaded by the running service,
4 plaintext fields (2 tenants), 0 envelopes, envelope writes off.

## 1. Two completely separate modes

| | REHEARSAL (`--target rehearsal`, default) | PRODUCTION (`--target production`) |
|---|---|---|
| Database | only one carrying the `b2_rehearsal_marker` row | must **not** carry the marker |
| Authority | env acknowledgement + marker (B2) | Ed25519-signed, single-use, single-tenant grant |
| Scope | all tenants, or `--tenant-id` | exactly one tenant, named by the grant |
| Options | `--continue-on-failure`, `--retry-conflicts` | refused (`OPTION_NOT_ALLOWED_IN_PRODUCTION`) |

No single environment variable can enable a production write. The application never imports the
executor (a test scans `app/`), so nothing starts a migration at service start-up. Read-only modes
(`inventory`, `dry-run`, `verify`, `plan`) need no grant.

## 2. The grant

Signed by the owner's **offline** authority key (Ed25519); the server holds only the public key at
`/etc/saas-base/migration-authority.pub` (root-owned, not group/other writable, not in the repo).
The grant contains no secret and is not an encryption key. It binds:

`host`, `tenant_id`, `fields` (subset of `wx_api_key_v3`, `wx_private_key`), `backend_sha` (git HEAD,
clean worktree), `alembic_revision`, `db_fingerprint` (sha256 of schema name + `@@server_uuid`),
`keyring_active_key_id`, `backup_path` + `backup_sha256` (backup must exist, match, and be < 24 h old),
`recovery_attested_at` (owner attests Keyring recovery verified; < 90 days), `plan_digest`, and a
validity window (<= 1 hour).

`plan_digest` is computed by the executor from the live state (all of the above plus each field's
format and the SHA-256 of the exact old value the compare-and-swap will pin). Any drift between
approval and execution (a merchant edits a key, the code is updated, the DB is restored...) changes
the digest and the run is refused.

Consumption: the grant id is appended to a root-only, `flock`-guarded, fsync'ed ledger
(`/var/lib/saas-base/wxpay-migration-ledger.jsonl`) **before the first write**. A crash therefore burns
the grant (it can never be replayed) and the owner issues a new one from the then-current state. Only
one migration can run at a time (the lock is held for the whole run).

Stable refusal codes (exit 4, database and ledger untouched): `GRANT_MISSING`, `GRANT_MALFORMED`,
`GRANT_SIGNATURE_INVALID`, `GRANT_EXPIRED`, `GRANT_NOT_YET_VALID`, `GRANT_LIFETIME_INVALID`,
`GRANT_REUSED`, `GRANT_FIELD_NOT_ALLOWED`, `GRANT_TENANT_INVALID`, `FIELD_NOT_WHITELISTED`,
`AUTHORITY_KEY_MISSING|UNTRUSTED|INVALID`, `TENANT_SCOPE_NOT_SINGLE`, `TENANT_MISMATCH`,
`HOST_MISMATCH`, `DB_FINGERPRINT_MISMATCH`, `BACKEND_SHA_MISMATCH`, `WORKTREE_DIRTY`,
`ALEMBIC_MISMATCH`, `KEYRING_UNAVAILABLE`, `KEYRING_KEY_ID_MISMATCH`, `SERVICE_WRITE_FLAG_ON`,
`EXECUTOR_WRITE_FLAG_OFF`, `BACKUP_UNAVAILABLE|HASH_MISMATCH|STALE`, `RECOVERY_ATTESTATION_STALE`,
`PLAN_DIGEST_MISMATCH`, `REHEARSAL_MARKER_PRESENT_IN_PRODUCTION`, `LEDGER_*`, `APPLY_FLAG_MISSING`.

## 3. Evidence (isolated rehearsal on MySQL 5.7.44 + CI)

* Production-mode rehearsal through the real CLI on a throwaway socket-only `mysqld` restored from the
  verified backup: **41 checks, 0 failed** (every refusal above that applies at the CLI, plus: wrong
  database proven with the real production DB's fingerprint, batch 1 then batch 2 flow with B1-reader
  `MATCH`, replay refused, completed tenant re-run is a byte-identical no-op, CAS conflict stops and burns
  the grant, process killed before the first write and right after the commit both recover from database
  state, output/ledger/grants contain no secret).
* The complete B2 rehearsal re-run with the new executor: **38 checks, 0 failed** (no regression).
* CI: SQLite logic tests (every refusal code, partial-field grant, ledger lock/permissions, crash and burn
  semantics, secret-free output, no application import) and real MySQL 5.7 tests (live `@@server_uuid`
  fingerprint, grant for database A refused on database B, byte-exact CAS conflict, killed connection).

## 4. Runbook (for a future, separately authorized production phase)

Never run any step below without an explicit owner authorization for that phase.

1. **Pre-checks (read-only).** Backend SHA equals `main`, clean tree; service health; Keyring runtime
   status `CONFIGURED`; `verify` shows every non-empty field readable; payment links healthy (no pending
   WeChat callbacks); service `.env` has no `WXPAY_ENVELOPE_WRITE_ENABLED=true`.
2. **Fresh database backup** (`mysqldump --single-transaction`, root-only, outside the repo and web roots),
   then restore-verify it in an isolated MySQL as in B1/B2. Record its SHA-256.
3. **Keyring recovery.** Run the owner's recall check (`recall-check.ps1`); note the UTC time.
4. **Plan (read-only, on the server):**
   `python scripts/wxpay_secret_migrate.py --mode plan --target production --tenant-id <ID> --field wx_api_key_v3 --field wx_private_key`
   with `WXPAY_MIGRATION_DATABASE_URL` in the environment (never argv). Review the output; it contains no secret.
5. **Issue the grant (owner's machine, offline):** `python scripts/wxpay_migration_grant.py issue --plan-file ... --backup-path ... --backup-sha256 ... --recovery-attested-at ... --private-key ... --out grant.json`
   (passphrase prompt). Copy only `grant.json` to the server (root-only, mode 0600). TTL <= 30 minutes.
6. **Execute one tenant**, with the executor's own environment carrying `WXPAY_ENVELOPE_WRITE_ENABLED=true`
   (this process only; the service's flag stays off):
   `... --mode apply --apply --target production --tenant-id <ID> --grant-file grant.json`.
   Order: batch 1 = payments-**disabled** tenant; batch 2 = payments-**enabled** tenant, only after batch 1
   is verified and an authorized payment-compatibility check for that merchant is planned.
7. **After each tenant:** `--mode verify`; confirm exit 0, `fields_updated` as planned, `decrypt_match_count`
   equal, format counts as expected; confirm the service still serves (health, no new decrypt errors).
8. **Stop conditions:** any FAILED/REJECTED, any exit other than 0, any unexpected log line, any health
   regression. Do not continue to another tenant. A CAS conflict (exit 3) means a concurrent edit: the tenant
   is untouched; wait, re-plan, issue a new grant. A burned grant is never reused.
9. **No automatic rollback to plaintext.** Once any envelope exists, the pre-B1 code must never be restored
   (it would use the envelope string as the key). Recovery paths: keep the B1 reader; restore the Keyring from
   its sealed copy; or restore the pre-migration database backup.
10. **Audit record.** Keep: grant id (from the ledger), plan digest, backup SHA-256, executor output (hashed
    tenant ids, counts only), and the verify result. Never store plaintext, Keyring bytes or the authority
    private key in logs, tickets or Git.

Legacy plaintext compatibility (`WXPAY_LEGACY_PLAINTEXT_READ_ENABLED=false`) is a separate, later step, only
after `verify` shows zero plaintext fields and a fresh backup exists.
