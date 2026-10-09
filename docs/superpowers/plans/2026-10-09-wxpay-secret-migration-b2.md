# WeChat Pay secret migration (B2): isolated-rehearsal executor and production plan

Status: **prototype for isolated rehearsal only.** Nothing in this document or in
`saas-base/scripts/wxpay_secret_migrate.py` is authorized to run against production.
Production state at the time of writing: backend on `995b425e`, no Keyring, envelope writes
off, 4 legacy-plaintext fields in 2 tenants, 0 envelopes.

## 1. What was built

`saas-base/scripts/wxpay_secret_migrate.py` moves legacy plaintext `tenant.wx_api_key_v3` /
`tenant.wx_private_key` values to the B1 envelope `enc:v1:<key-id>:<fernet-token>`.

| Mode | Writes | Notes |
|---|---|---|
| `inventory` | no | format counts only |
| `dry-run` (default) | no | plan per tenant; no Keyring needed |
| `verify` | no | every non-empty field must be readable by the B1 reader |
| `apply` | yes | guarded, see below |

### Safety properties (enforced in code, covered by tests)

* `apply` needs **all** of: `--apply`; `WXPAY_MIGRATION_ALLOW_ISOLATED_WRITE` = the exact
  acknowledgement string; a `b2_rehearsal_marker` table with exactly one
  `B2_ISOLATED_REHEARSAL` row in the target database (a production database has none);
  `WXPAY_MIGRATION_DATABASE_URL` different from the application's `DATABASE_URL`; the B1
  write flag on; a Keyring that loads under the B1 trust policy.
* Target URL comes from the environment, never argv.
* Field whitelist: the two secret columns only.
* Only valid `LEGACY_PLAINTEXT` is encrypted. Existing envelopes are never re-encrypted.
  Raw-Fernet / unknown / malformed values, **and envelopes the current Keyring cannot read**,
  reject the whole tenant (no change to that tenant, so a broken field is never masked).
* One transaction and one `UPDATE` per tenant. Compare-and-swap on both old values using a
  byte-exact comparison (`BINARY col <=> BINARY :old` on MySQL, because the columns are
  `utf8mb4_general_ci` and a plain `=` would treat `a` and `A` as equal). `rowcount != 1` is a
  conflict. `updated_at = updated_at` pins the audit timestamp against `ON UPDATE
  CURRENT_TIMESTAMP`. The row is read back inside the transaction and must decrypt, through the
  B1 reader, to the original secret before COMMIT.
* A tenant failure never affects another tenant. State is always re-read from the database, so a
  killed run is resumed by running again.
* Output is JSON lines with hashed tenant ids, format names and reason codes only. Exception
  text is never printed (driver errors can embed SQL parameters) and the engine hides parameters.
* Exit codes: 0 ok, 2 failed/rejected, 3 CAS conflict(s), 4 refused (guard).

### Tests

* `tests/test_wxpay_secret_migration_executor.py` (SQLite, runs in Gate A/B/Full): guards,
  dry-run, atomicity, resume after a simulated crash, idempotency, secret-free output,
  rotation, unreadable-envelope rejection.
* `tests/test_wxpay_secret_migration_schema_mysql.py` (real MySQL 5.7 job): byte-exact CAS
  against a case-insensitive collation, `updated_at` pinned, InnoDB rollback, killed connection,
  conflict retry, marker guard.
* `scripts/wxpay_b2_rehearsal_driver.py`: the server-side driver used for the isolated rehearsal
  (below). Synthetic Keyring only; prints PASS/FAIL, counts and MATCH/DIFF.

## 2. Isolated rehearsal (2026-10-09)

Environment: a throwaway `mysqld` 5.7.44 started with `--no-defaults --skip-networking`, its own
datadir and socket under `/var/lib/b2-rehearsal/`, restored from the SHA-256-verified
pre-deploy backup; a throwaway Keyring (`root:root` 0600 in a root-only directory, so the real B1
trust policy applied unchanged); a decoy application `DATABASE_URL`; no production credentials,
Redis, systemd unit or Keyring were used. The directory (including the restored copy and the test
Keyring) is deleted on exit; production git SHA, MySQL and service PIDs, health and Keyring files
were verified unchanged afterwards.

Result: **38 checks, 0 failed** (counts and MATCH/DIFF only; the log holds no secret material).

| Area | Evidence |
|---|---|
| Restored copy | 6 tenants, 4 plaintext fields, 0 envelopes |
| Keyring (real B1 trust policy) | load OK; active key valid; decrypt-only key valid; unknown key id, corrupted token -> fail closed; mode 0644, wrong owner, symlink -> fail closed |
| Read-only modes | `inventory` and default `dry-run` change nothing (`fields_expected=4`) |
| Guards | missing `--apply`, missing acknowledgement, missing marker, target == application DB, write flag off -> all refused, database untouched |
| Migration | `fields_expected=4`, `fields_updated=4`, plaintext after 0, envelope after 4, tenant count unchanged, non-secret columns (incl. `updated_at`) unchanged, B1-reader `MATCH=4 DIFF=0` |
| Idempotency | second run `fields_updated=0`, secret columns byte-identical |
| Fault injection | encrypt failure on the first or second field -> that tenant unchanged, others migrated; connection killed mid-tenant -> rolled back, others migrated; concurrent (case-only) edit -> `cas_conflict_count=1`, exit 3, winner preserved, next run succeeds; Keyring missing / active key invalid -> refused with no writes; unknown key id and corrupted token -> flagged by `verify`, tenant rejected, nothing rewritten |
| Crash recovery | process killed (exit 137) right after the first tenant committed: one whole tenant migrated, one untouched; restart migrated only the remainder (`noop=1 migrated=1`), committed bytes identical |
| Key rotation | A-envelopes readable with B active + A decrypt-only; new writes use B; an in-process Keyring snapshot does not change until restart; removing A -> 4/4 fields fail closed; restoring A recovers |
| Rollback / recovery | restoring the pre-migration snapshot returns the exact pre-migration secret state; Keyring lost -> 4/4 fields fail closed, restored from the secure copy -> readable; **pre-B1 code returns the envelope string as the key (PRE_B1_CODE_ROLLBACK=FORBIDDEN)** |
| Isolation afterwards | rehearsal directory removed; production git SHA, mysqld and service PIDs, health and Keyring files unchanged |

## 3. Production migration plan (not authorized by this change)

Prerequisites, in order:

1. A fresh, restore-verified logical backup taken immediately before the window (same procedure
   as the pre-deploy backup). The backup contains merchant secrets: root-only, outside Git and web roots.
2. Keyring prepared (see below) and loaded once by a read-only check (`verify` on an empty or
   already-migrated set) before any write is enabled.
3. A reviewed, separately authorized change that deploys this executor and removes the rehearsal
   marker guard in favour of an explicit production authorization mechanism. The rehearsal marker
   exists so that this prototype can never write to production.

Keyring source and storage: a root-owned `0600` file in a root-owned directory (e.g.
`/etc/saas-base/wxpay-keyring.json`; `/run` is a tmpfs and would not survive a reboot), or a
systemd `LoadCredential` copy. The service currently runs as root, so the root-only source applies
directly. Keys are generated on the server (Fernet), never leave it, are never put in Git, chat or
tickets, and a sealed offline copy is kept by the owner: **losing the Keyring after envelopes exist
makes every migrated secret unrecoverable** (the rehearsal demonstrates the fail-closed behaviour).

Active / decrypt-only rules: exactly one `encrypt-decrypt` key; every key that ever encrypted a live
envelope stays as `decrypt-only` until no envelope carries its id (check with `verify` and an id
inventory). A Keyring change takes effect only after the service is restarted (the loaded snapshot
is immutable). Removing a key makes its envelopes fail closed; do not remove before re-encrypting.

Tenant order and execution: the one payment-enabled tenant is migrated last; run `dry-run`, then
`verify`, then `apply --tenant-id <id>` one tenant at a time, re-running `verify` after each. Stop
on the first FAILED/REJECTED (default). A CAS conflict means someone edited the tenant concurrently:
the tenant is untouched; wait, re-run `dry-run`, then retry that tenant once. Exit code 3 requires a
human decision before continuing.

Rollback: **once any envelope exists, the pre-B1 code must never be restored** (the rehearsal
shows the old reader returns the envelope string itself as the key). Recovery paths are: keep the
B1 reader; restore the Keyring file from its sealed copy; or restore the pre-migration database
snapshot. There is intentionally no envelope-to-plaintext automation.

Closing legacy plaintext compatibility (`WXPAY_LEGACY_PLAINTEXT_READ_ENABLED=false`) is a separate,
later step and only when: `verify` shows zero `LEGACY_PLAINTEXT` fields, every payment-enabled tenant
has been exercised by a real, separately authorized payment check, and a fresh backup exists.
