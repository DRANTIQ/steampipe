#!/usr/bin/env python3
"""
Check that this environment can reach AWS (STS GetCallerIdentity).
Run inside the worker container to debug "StatusCode: 0, request send failed":
  docker compose run --rm worker python scripts/check_aws_connectivity.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    from src.config import get_settings
    s = get_settings()
    if not (s.AWS_ACCESS_KEY_ID and s.AWS_SECRET_ACCESS_KEY):
        print("No AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in env; set in .env")
        return 1
    try:
        import boto3
        kwargs = {
            "aws_access_key_id": s.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": s.AWS_SECRET_ACCESS_KEY,
            "region_name": s.S3_REGION,
        }
        if s.AWS_SESSION_TOKEN:
            kwargs["aws_session_token"] = s.AWS_SESSION_TOKEN
        sts = boto3.client("sts", **kwargs)
        identity = sts.get_caller_identity()
        print("OK: GetCallerIdentity", identity.get("Arn"))
        return 0
    except Exception as e:
        print("FAIL:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
