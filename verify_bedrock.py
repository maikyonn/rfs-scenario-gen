#!/usr/bin/env python3
"""Verify AWS Bedrock access to Claude Sonnet 4.6."""

import json
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

PROFILE = "Path-Emerging-Dev-147229569658"
REGION = "us-west-2"
MODEL_ID = "us.anthropic.claude-sonnet-4-6"


def verify_bedrock_access():
    print(f"Profile : {PROFILE}")
    print(f"Region  : {REGION}")
    print(f"Model   : {MODEL_ID}")
    print("-" * 50)

    # 1. Auth check
    try:
        session = boto3.Session(profile_name=PROFILE, region_name=REGION)
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        print(f"[OK] Authenticated as: {identity['Arn']}")
    except NoCredentialsError:
        print("[FAIL] No credentials found — run: aws sso login --profile <profile>")
        return
    except ClientError as e:
        print(f"[FAIL] Auth error: {e}")
        return

    # 2. Invoke model
    bedrock = session.client("bedrock-runtime")
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 64,
        "messages": [
            {"role": "user", "content": "Reply with exactly: 'Claude Sonnet 4.6 on Bedrock is working.'"}
        ],
    }

    try:
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(payload),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        reply = result["content"][0]["text"].strip()
        tokens_in = result["usage"]["input_tokens"]
        tokens_out = result["usage"]["output_tokens"]

        print(f"[OK] Model responded: \"{reply}\"")
        print(f"     Tokens — in: {tokens_in}, out: {tokens_out}")
        print("-" * 50)
        print("Bedrock access to Claude Sonnet 4.6 is verified.")

    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg = e.response["Error"]["Message"]
        print(f"[FAIL] {code}: {msg}")
        if code == "AccessDeniedException":
            print("       Request model access at: AWS Console → Bedrock → Model access")


if __name__ == "__main__":
    verify_bedrock_access()
