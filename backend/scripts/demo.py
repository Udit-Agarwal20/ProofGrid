"""Run the synthetic golden journey against a separately running API and worker."""

import argparse
import asyncio
import json
import os
from uuid import uuid4

import httpx

PROMPT = "Find Indian AI startups that raised more than $1M in the last 12 months. Include company, website, founders, headquarters, funding round, funding amount, investors, funding date, and original evidence."


async def main(base: str) -> None:
    token = os.getenv("API_AUTH_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=60) as client:

        async def post(path: str, body: dict[str, object] | None = None) -> dict[str, object]:
            response = await client.post(path, json=body)
            response.raise_for_status()
            return dict(response.json())

        compiled = await post(
            "/v1/requirements/compile", {"prompt": PROMPT, "reference_date": "2026-09-30T00:00:00Z"}
        )
        req = compiled["requirement_id"]
        await post(f"/v1/requirements/{req}/confirm", {"expected_version": 1})
        plan = await post(f"/v1/requirements/{req}/plan")
        assert isinstance(plan["data"], dict)
        run = await post(
            f"/v1/workflows/{plan['id']}/runs",
            {
                "workflow_version_id": plan["data"]["workflow_version_id"],
                "idempotency_key": str(uuid4()),
            },
        )
        print(json.dumps({"run_id": run["id"], "events": base + f"/v1/runs/{run['id']}/events"}))
        for _ in range(300):
            response = await client.get(f"/v1/runs/{run['id']}")
            response.raise_for_status()
            state = response.json()["data"]
            if state["status"] in {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
                print(json.dumps(state, indent=2))
                metrics = state["metrics"]
                if metrics.get("dataset_version_id"):
                    exported = await post(
                        "/v1/exports",
                        {"dataset_version_id": metrics["dataset_version_id"], "format": "csv"},
                    )
                    print(json.dumps(exported, indent=2))
                return
            await asyncio.sleep(1)
        raise SystemExit("Run has not finished; inspect its persisted status and worker.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    asyncio.run(main(parser.parse_args().base_url))
