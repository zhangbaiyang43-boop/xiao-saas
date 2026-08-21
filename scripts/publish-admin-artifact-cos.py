#!/usr/bin/env python3
"""Standalone Tencent COS publisher for the admin-h5 deploy artifact.

Single responsibility: given a locally-built archive + checksum pair for an
exact commit SHA, upload them to Tencent COS under the frozen object prefix

    deploy-artifacts/admin-h5/admin-h5-<SHA>/<filename>

refusing to silently overwrite an existing object with different content.
This is deployment tooling, not application code -- it deliberately does
NOT import saas-base/app/core/cos.py (a different module, for a different
purpose: member-facing image uploads at runtime, with its own COS_* env
var names and its own bucket-wide access). That module is untouched by
this phase and irrelevant to it.

No production .env dependency: credentials and configuration come only
from these environment variables, and are never logged or printed:

    DEPLOY_COS_SECRET_ID
    DEPLOY_COS_SECRET_KEY
    DEPLOY_COS_REGION
    DEPLOY_COS_BUCKET
    DEPLOY_COS_BASE_URL   (optional -- only used to print the resulting
                            public runtime URL; this script talks to COS
                            via the SDK/region/bucket, never via this URL)

Usage:
    python3 publish-admin-artifact-cos.py \
        --sha <full-git-sha> \
        --archive <path-to-admin-h5-dist-SHA.tar.gz> \
        --checksum <path-to-admin-h5-dist-SHA.tar.gz.sha256>

Exit codes:
    0  uploaded, or an identical existing object was found and reused
    1  BLOCKED_EXISTING_COS_ARTIFACT_MISMATCH -- an existing object under
       this SHA's prefix exists but differs from (or is incomplete
       relative to) this build; never overwritten automatically
    2  usage / configuration error (missing env var, missing local file)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import time

COS_PREFIX = "deploy-artifacts/admin-h5"

# Production evidence: plain put_object() uploads of the admin-h5 archive
# over the mainland-China COS path have failed with
# CosClientError(('Connection aborted.', TimeoutError('The write operation
# timed out'))) -- the SDK's own defaults (no explicit timeout, no retry)
# aren't resilient enough for that link. Explicit, non-default timeouts:
# fail a truly dead connection fast (30s to connect), but give a slow
# upload of a multi-MB archive real room to finish (300s read/write) rather
# than getting killed mid-transfer.
COS_CONNECT_TIMEOUT_SECONDS = 30
COS_READ_TIMEOUT_SECONDS = 300

# Bounded retry around the upload call itself -- never infinite. Schedule:
# attempt 1 fails -> sleep 2s -> attempt 2; attempt 2 fails -> sleep 5s ->
# attempt 3; attempt 3 fails -> give up and let the exception propagate.
COS_UPLOAD_MAX_ATTEMPTS = 3
COS_UPLOAD_RETRY_DELAYS_SECONDS = (2, 5)

# upload_file()'s multipart threshold/concurrency -- files at or under
# COS_UPLOAD_PART_SIZE_MB upload as a single streamed PUT; larger ones
# transparently become a resumable multipart upload.
COS_UPLOAD_PART_SIZE_MB = 10
COS_UPLOAD_MAX_THREADS = 5


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_key(sha: str, filename: str) -> str:
    return f"{COS_PREFIX}/admin-h5-{sha}/{filename}"


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print("STATUS=BLOCKED_COS_CREDENTIALS_MISSING", file=sys.stderr)
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(2)
    return value


def get_object_bytes(client, bucket: str, key: str) -> bytes:
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].get_raw_stream().read()


def object_exists(client, bucket: str, key: str) -> bool:
    from qcloud_cos.cos_exception import CosServiceError

    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except CosServiceError as exc:
        if exc.get_status_code() == 404:
            return False
        raise


def build_cos_config(region: str, secret_id: str, secret_key: str):
    """CosConfig with explicit connect/read timeouts, never the SDK default.

    Timeout=(connect, read) is forwarded verbatim to every requests call the
    SDK makes (qcloud_cos.cos_client.CosS3Client.send_request), which is
    exactly the tuple form the underlying `requests` library expects.
    """
    from qcloud_cos import CosConfig

    try:
        return CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key,
            Timeout=(COS_CONNECT_TIMEOUT_SECONDS, COS_READ_TIMEOUT_SECONDS),
        )
    except TypeError:
        # A CosConfig stub without a Timeout parameter -- only happens
        # against the disk-backed fake in scripts/test-deployment-tooling.sh;
        # production always uses the pinned real SDK, which accepts it.
        return CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)


def upload_with_retry(client, bucket: str, key: str, local_path: str, content_type: str, cache_control: str) -> None:
    """Upload local_path to key with bounded, exponential-backoff retry.

    Prefers the SDK's high-level upload_file(): it streams from disk rather
    than buffering the whole archive in memory, and for anything over
    COS_UPLOAD_PART_SIZE_MB transparently does a resumable multipart
    upload. That -- combined with build_cos_config()'s explicit timeouts --
    is what actually hardens the upload against the write-timeout class of
    failure (CosClientError wrapping a socket TimeoutError) this exists to
    fix; the retry loop below only covers the residual case of a transient
    failure even after that.

    Falls back to the original single-shot put_object(Body=<bytes>) for any
    client that doesn't expose upload_file -- only the disk-backed test
    fake in scripts/test-deployment-tooling.sh lacks it, so local test
    coverage keeps exercising exactly the code path it always has.
    """
    last_exc: Exception | None = None
    for attempt in range(1, COS_UPLOAD_MAX_ATTEMPTS + 1):
        try:
            if hasattr(client, "upload_file"):
                client.upload_file(
                    Bucket=bucket,
                    Key=key,
                    LocalFilePath=local_path,
                    PartSize=COS_UPLOAD_PART_SIZE_MB,
                    MAXThread=COS_UPLOAD_MAX_THREADS,
                    ContentType=content_type,
                    CacheControl=cache_control,
                )
            else:
                with open(local_path, "rb") as f:
                    client.put_object(
                        Bucket=bucket,
                        Body=f.read(),
                        Key=key,
                        ContentType=content_type,
                        CacheControl=cache_control,
                    )
            return
        except Exception as exc:
            # Caught broadly on purpose: the point is a bounded retry around
            # any transient transport failure (CosClientError wrapping a
            # ConnectionError/TimeoutError being the one seen in production),
            # not a specific exception type.
            last_exc = exc
            if attempt == COS_UPLOAD_MAX_ATTEMPTS:
                break
            delay = COS_UPLOAD_RETRY_DELAYS_SECONDS[attempt - 1]
            print(
                f"upload attempt {attempt}/{COS_UPLOAD_MAX_ATTEMPTS} for {key} failed: {exc} -- retrying in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True, help="full git commit SHA this artifact was built from")
    parser.add_argument("--archive", required=True, help="path to admin-h5-dist-<SHA>.tar.gz")
    parser.add_argument("--checksum", required=True, help="path to admin-h5-dist-<SHA>.tar.gz.sha256")
    args = parser.parse_args()

    if not os.path.isfile(args.archive):
        print(f"archive not found: {args.archive}", file=sys.stderr)
        return 2
    if not os.path.isfile(args.checksum):
        print(f"checksum not found: {args.checksum}", file=sys.stderr)
        return 2

    secret_id = require_env("DEPLOY_COS_SECRET_ID")
    secret_key = require_env("DEPLOY_COS_SECRET_KEY")
    region = require_env("DEPLOY_COS_REGION")
    bucket = require_env("DEPLOY_COS_BUCKET")
    base_url = os.environ.get("DEPLOY_COS_BASE_URL", "").rstrip("/")

    from qcloud_cos import CosS3Client

    config = build_cos_config(region, secret_id, secret_key)
    client = CosS3Client(config)

    archive_name = os.path.basename(args.archive)
    checksum_name = os.path.basename(args.checksum)
    archive_key = object_key(args.sha, archive_name)
    checksum_key = object_key(args.sha, checksum_name)

    archive_exists = object_exists(client, bucket, archive_key)
    checksum_exists = object_exists(client, bucket, checksum_key)

    if archive_exists != checksum_exists:
        # Half-published: one asset present, the other missing -- never
        # silently "complete" the pair by uploading just the missing half
        # next to an object of unknown provenance.
        print("STATUS=BLOCKED_EXISTING_COS_ARTIFACT_MISMATCH", file=sys.stderr)
        print(
            f"Incomplete existing object set under admin-h5-{args.sha}/: "
            f"archive_exists={archive_exists} checksum_exists={checksum_exists}",
            file=sys.stderr,
        )
        return 1

    if archive_exists and checksum_exists:
        local_archive_sha256 = sha256_of(args.archive)
        with open(args.checksum, "rb") as f:
            local_checksum_bytes = f.read()

        with tempfile.TemporaryDirectory() as tmp:
            remote_archive_path = os.path.join(tmp, archive_name)
            with open(remote_archive_path, "wb") as f:
                f.write(get_object_bytes(client, bucket, archive_key))
            remote_archive_sha256 = sha256_of(remote_archive_path)
        remote_checksum_bytes = get_object_bytes(client, bucket, checksum_key)

        mismatches = []
        if remote_archive_sha256 != local_archive_sha256:
            mismatches.append(
                f"archive sha256 differs (remote={remote_archive_sha256} local={local_archive_sha256})"
            )
        if remote_checksum_bytes != local_checksum_bytes:
            mismatches.append("checksum file content differs")

        if mismatches:
            print("STATUS=BLOCKED_EXISTING_COS_ARTIFACT_MISMATCH", file=sys.stderr)
            for reason in mismatches:
                print(f"  - {reason}", file=sys.stderr)
            return 1

        print(f"Existing COS object admin-h5-{args.sha}/ matches this build byte-for-byte -- reusing.")
    else:
        upload_with_retry(
            client, bucket, archive_key, args.archive,
            content_type="application/gzip",
            cache_control="public,max-age=31536000,immutable",
        )
        upload_with_retry(
            client, bucket, checksum_key, args.checksum,
            content_type="text/plain; charset=utf-8",
            cache_control="public,max-age=31536000,immutable",
        )
        print(f"Uploaded {archive_key}")
        print(f"Uploaded {checksum_key}")

    print(f"COS_ARTIFACT_KEY={archive_key}")
    if base_url:
        print(f"COS_ARTIFACT_URL={base_url}/{archive_key}")
    print("STATUS=COS_ARTIFACT_READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
