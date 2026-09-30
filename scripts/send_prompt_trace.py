from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def send_trace(label: str, correlation_id: str) -> None:
    load_dotenv(REPO_ROOT / ".env")
    os.environ["LANGFUSE_PROMPT_LABEL"] = label

    from langfuse import get_client

    langfuse_client = get_client()
    managed_prompt = langfuse_client.get_prompt(
        "day13-chat",
        label=label,
        type="text",
        cache_ttl_seconds=60,
        fetch_timeout_seconds=15,
        max_retries=2,
    )
    print(f"prompt_version={managed_prompt.version} prompt_labels={managed_prompt.labels}")

    # Import after setting the label so the request uses the selected prompt version.
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cp2.local") as client:
        response = await client.post(
            "/chat",
            headers={"x-request-id": correlation_id},
            json={
                "user_id": "student-cp2",
                "session_id": f"prompt-{label}-evidence",
                "feature": "qa",
                "message": "How should alerts be designed?",
            },
        )
        response.raise_for_status()
        payload = response.json()
        print(
            f"label={label} status={response.status_code} "
            f"correlation_id={payload['correlation_id']} tokens_in={payload['tokens_in']}"
        )

    langfuse_client.flush()
    print("langfuse_flush=done")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one trace for a Langfuse prompt label")
    parser.add_argument("label", choices=("baseline", "candidate", "production"))
    parser.add_argument("correlation_id", help="Correlation ID in req-<8-hex> format")
    args = parser.parse_args()
    asyncio.run(send_trace(args.label, args.correlation_id))


if __name__ == "__main__":
    main()
