import asyncio
import os
import time
import uuid
from collections import Counter

import httpx
import pytest

from tests.test_stress.stats import write_stress_stats


BASE_URL = os.environ.get("PANGLOSS_TEST_BASE_URL", "http://127.0.0.1:8000")

READ_STRESS_CASES = [
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
    (10000, 200),
    (10000, 500),
]


async def get_token(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/users/token",
        json={"username": "testuser", "password": "testpassword"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def create_person(client: httpx.AsyncClient, token: str, label: str) -> str:
    response = await client.post(
        "/api/Person/new",
        json={
            "type": "Person",
            "label": label,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def create_subthing_for_person(
    client: httpx.AsyncClient,
    token: str,
    label: str,
    person_id: str,
) -> str:
    response = await client.post(
        "/api/SubThing/new",
        json={
            "type": "SubThing",
            "label": label,
            "is_person_of_subthing": [
                {
                    "type": "Person",
                    "id": person_id,
                }
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def read_person(
    client: httpx.AsyncClient,
    person_id: str,
) -> dict:
    response = await client.get(f"/api/Person/{person_id}")
    assert response.status_code == 200, response.text
    return response.json()


def assert_basic_person_response(data: dict) -> None:
    assert data["type"] == "Person", data
    assert data["id"], data


def find_connected_subthings(data: dict) -> list[dict]:
    value = data.get("is_subthing_of_person")

    if not value:
        return []

    if not isinstance(value, list):
        return []

    return [
        item
        for item in value
        if isinstance(item, dict) and item.get("type") == "SubThing"
    ]


async def seed_people_with_subthings(
    client: httpx.AsyncClient,
    token: str,
    count: int,
) -> list[str]:
    run_id = str(uuid.uuid4())
    person_ids = []

    for i in range(count):
        person_id = await create_person(
            client,
            token,
            f"Read stress person {run_id}-{i}",
        )

        await create_subthing_for_person(
            client,
            token,
            f"Read stress SubThing {run_id}-{i}",
            person_id,
        )

        person_ids.append(person_id)

    return person_ids


@pytest.mark.asyncio
@pytest.mark.stress
@pytest.mark.parametrize("total_requests,concurrency", READ_STRESS_CASES)
async def test_concurrent_person_reads(
    total_requests: int,
    concurrency: int,
):
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=120,
        limits=limits,
    ) as client:
        token = await get_token(client)

        seeded_person_ids = await seed_people_with_subthings(
            client,
            token,
            count=max(concurrency, 25),
        )

        # Validate one seeded entity before timing starts.
        # This confirms that GET /api/Person/{id} itself works.
        sample_data = await read_person(client, seeded_person_ids[0])
        assert_basic_person_response(sample_data)

        sample_connected_subthings = find_connected_subthings(sample_data)
        includes_connected_subthing = bool(sample_connected_subthings)

        if not includes_connected_subthing:
            print()
            print("WARNING: GET /api/Person/{id} does not include is_subthing_of_person.")
            print("The stress test will measure basic Person read performance only.")
            print(f"Sample response keys: {list(sample_data.keys())}")

        sem = asyncio.Semaphore(concurrency)

        async def read_one(i: int) -> dict:
            person_id = seeded_person_ids[i % len(seeded_person_ids)]

            async with sem:
                started = time.perf_counter()

                try:
                    response = await client.get(f"/api/Person/{person_id}")
                    elapsed = time.perf_counter() - started

                    if response.status_code != 200:
                        return {
                            "ok": False,
                            "latency": elapsed,
                            "error": f"status_{response.status_code}",
                        }

                    data = response.json()
                    assert_basic_person_response(data)

                    if includes_connected_subthing:
                        connected_subthings = find_connected_subthings(data)

                        if not connected_subthings:
                            return {
                                "ok": False,
                                "latency": elapsed,
                                "error": "missing_connected_subthing",
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

                except (AssertionError, KeyError) as e:
                    elapsed = time.perf_counter() - started

                    return {
                        "ok": False,
                        "latency": elapsed,
                        "error": type(e).__name__,
                    }

        start = time.perf_counter()

        results = await asyncio.gather(
            *(read_one(i) for i in range(total_requests))
        )

    duration = time.perf_counter() - start

    successful = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    latencies = [r["latency"] for r in successful]
    error_counts = Counter(r["error"] for r in failed)

    print()
    print(f"total={total_requests}")
    print(f"concurrency={concurrency}")
    print(f"seeded_persons={len(seeded_person_ids)}")
    print(f"successful={len(successful)}")
    print(f"failed={len(failed)}")
    print(f"errors={dict(error_counts)}")
    print(f"includes_connected_subthing={includes_connected_subthing}")

    assert latencies, "No successful read requests"

    write_stress_stats(
        "person-read-stress",
        total=total_requests,
        concurrency=concurrency,
        duration=duration,
        latencies=latencies,
        extra={
            "error_counts": dict(error_counts),
            "seeded_persons": len(seeded_person_ids),
            "reads_only_timed": True,
            "includes_connected_subthing": includes_connected_subthing,
        },
    )