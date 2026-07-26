"""
One-off helper: retries an OCI Resource Manager stack's Apply job until it
succeeds, since Oracle's free-tier Ampere A1 capacity is frequently
unavailable ("Out of host capacity") and clears unpredictably. Not part of
the app itself -- a deployment-provisioning tool, safe to delete once the
VM exists.

Usage:
    .oci-cli-venv/Scripts/python.exe scripts/oci_retry_apply.py <stack_ocid> [--interval 180] [--max-attempts 500]
"""

import argparse
import json
import subprocess
import sys
import time

OCI_BIN = str((__import__("pathlib").Path(__file__).parent.parent / ".oci-cli-venv" / "Scripts" / "oci"))


def try_apply(stack_id: str, max_wait_seconds: int) -> dict:
    result = subprocess.run(
        [
            OCI_BIN, "resource-manager", "job", "create-apply-job",
            "--stack-id", stack_id,
            "--execution-plan-strategy", "AUTO_APPROVED",
            "--wait-for-state", "SUCCEEDED",
            "--wait-for-state", "FAILED",
            "--max-wait-seconds", str(max_wait_seconds),
            "--wait-interval-seconds", "15",
        ],
        capture_output=True, text=True, shell=True,
    )
    stdout = result.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {}
    return {
        "returncode": result.returncode,
        "stderr": result.stderr.strip(),
        "data": payload.get("data", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stack_id")
    parser.add_argument("--interval", type=int, default=180, help="Seconds to wait between retry attempts")
    parser.add_argument("--max-attempts", type=int, default=500)
    parser.add_argument("--max-wait-seconds", type=int, default=300, help="How long each single apply attempt waits for a terminal state")
    args = parser.parse_args()

    for attempt in range(1, args.max_attempts + 1):
        print(f"[attempt {attempt}] creating apply job...", flush=True)
        outcome = try_apply(args.stack_id, args.max_wait_seconds)
        state = outcome["data"].get("lifecycle-state")

        if state == "SUCCEEDED":
            print(f"[attempt {attempt}] SUCCEEDED. Job id: {outcome['data'].get('id')}")
            print(json.dumps(outcome["data"], indent=2))
            sys.exit(0)

        reason = outcome["stderr"] or state or "unknown"
        print(f"[attempt {attempt}] failed/timed out (state={state}). {reason[:300]}", flush=True)
        print(f"[attempt {attempt}] sleeping {args.interval}s before retrying...", flush=True)
        time.sleep(args.interval)

    print("Exhausted max attempts without success.")
    sys.exit(1)


if __name__ == "__main__":
    main()
