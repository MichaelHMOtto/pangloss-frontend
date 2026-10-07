# tests/test_stress/test_create_stress.py

import asyncio
import os
import time
import uuid
from collections import Counter

import httpx
import pytest

from tests.test_stress.stats import write_stress_stats


BASE_URL = os.environ.get("PANGLOSS_TEST_BASE_URL", "http://127.0.0.1:8000")

STRESS_CASES = [
    (20, 5),
    (50, 10),
    (100, 20),
    (200, 20),
    (500, 50),
    (1000, 50),
    (1000, 100),
    (2000, 100),
    (2000, 200),
    (5000, 100),
    (5000, 200),
]


@pytest.mark.asyncio
@pytest.mark.stress
@pytest.mark.parametrize("total_requests,concurrency", STRESS_CASES)
async def test_concurrent_creates(total_requests: int, concurrency: int):
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=120,
        limits=limits,
    ) as client:
        token_response = await client.post(
            "/api/users/token",
            json={"username": "testuser", "password": "testpassword"},
        )
        assert token_response.status_code == 200, token_response.text

        token = token_response.json()["access_token"]
        sem = asyncio.Semaphore(concurrency)

        async def create_one(i: int) -> dict:
            async with sem:
                started = time.perf_counter()

                try:
                    response = await client.post(
                        "/api/MyModel/new",
                        json={
                            "label": f"Stress {total_requests}-{concurrency}-{i} {uuid.uuid4()}",
                            "name": f"Stress {i}",
                            "type": "MyModel",
                        },
                        headers={"Authorization": f"Bearer {token}"},
                    )

                    elapsed = time.perf_counter() - started

                    if response.status_code != 200:
                        return {
                            "ok": False,
                            "latency": elapsed,
                            "error": f"status_{response.status_code}",
                        }

                    return {
                        "ok": True,
                        "latency": elapsed,
                        "error": None,
                    }

                except httpx.HTTPError as e:
                    elapsed = time.perf_counter() - started

                    return {
                        "ok": False,
                        "latency": elapsed,
                        "error": type(e).__name__,
                    }

        start = time.perf_counter()

        results = await asyncio.gather(
            *(create_one(i) for i in range(total_requests))
        )

    duration = time.perf_counter() - start

    successful = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    latencies = [r["latency"] for r in successful]
    error_counts = Counter(r["error"] for r in failed)

    print()
    print(f"total={total_requests}")
    print(f"concurrency={concurrency}")
    print(f"successful={len(successful)}")
    print(f"failed={len(failed)}")
    print(f"errors={dict(error_counts)}")

    assert latencies, "No successful requests"

    write_stress_stats(
        "create-stress",
        total=total_requests,
        concurrency=concurrency,
        duration=duration,
        latencies=latencies,
        extra={
            "error_counts": dict(error_counts),
        },
    )