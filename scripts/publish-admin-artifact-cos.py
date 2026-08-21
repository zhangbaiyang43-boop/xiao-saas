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

COS_PREFIX = "deploy-artifacts/admin-h5"


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

    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
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
        with open(args.archive, "rb") as f:
            client.put_object(
                Bucket=bucket,
                Body=f.read(),
                Key=archive_key,
                ContentType="application/gzip",
                CacheControl="public,max-age=31536000,immutable",
            )
        with open(args.checksum, "rb") as f:
            client.put_object(
                Bucket=bucket,
                Body=f.read(),
                Key=checksum_key,
                ContentType="text/plain; charset=utf-8",
                CacheControl="public,max-age=31536000,immutable",
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
