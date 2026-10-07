import asyncio
import os
import time
import uuid
from collections import Counter

import httpx
import pytest

from tests.test_stress.stats import write_stress_stats


BASE_URL = os.environ.get("PANGLOSS_TEST_BASE_URL", "http://127.0.0.1:8000")

COMPLEX_STRESS_CASES = [
    (20, 5),
    (50, 10),
    (100, 20),
    (200, 20),
    (500, 50),
    (1000, 50),
    (1000, 100),
    (2000, 100),
    (2000, 200),
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
        json={"type": "Person", "label": label},
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code != 200:
        raise httpx.HTTPStatusError(
            f"Unexpected status {response.status_code}: {response.text}",
            request=response.request,
            response=response,
        )
    return response.json()["id"]


def person_relation(person_id: str) -> dict:
    return {"type": "Person", "id": person_id}


async def create_subsubthing(
    client: httpx.AsyncClient,
    token: str,
    label: str,
    person_ids: list[str],
) -> str:
    response = await client.post(
        "/api/SubSubThing/new",
        json={
            "type": "SubSubThing",
            "label": label,
            "is_person_of_subsubthing": [
                person_relation(person_id) for person_id in person_ids
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code != 200:
        raise httpx.HTTPStatusError(
            f"Unexpected status {response.status_code}: {response.text}",
            request=response.request,
            response=response,
        )
    return response.json()["id"]


async def update_subsubthing(
    client: httpx.AsyncClient,
    token: str,
    thing_id: str,
    label: str,
    person_ids: list[str],
) -> None:
    response = await client.put(
        f"/api/SubSubThing/{thing_id}/edit",
        json={
            "id": thing_id,
            "type": "SubSubThing",
            "label": label,
            "is_person_of_subsubthing": [
                person_relation(person_id) for person_id in person_ids
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code != 200:
        raise httpx.HTTPStatusError(
            f"Unexpected status {response.status_code}: {response.text}",
            request=response.request,
            response=response,
        )


def summarize_results(results: list[dict]) -> tuple[list[dict], list[dict], list[float], Counter]:
    successful = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    latencies = [r["latency"] for r in successful]
    error_counts = Counter(r["error"] for r in failed)
    return successful, failed, latencies, error_counts


def print_summary(
    total_requests: int,
    concurrency: int,
    successful: list[dict],
    failed: list[dict],
    error_counts: Counter,
) -> None:
    print()
    print(f"total={total_requests}")
    print(f"concurrency={concurrency}")
    print(f"successful={len(successful)}")
    print(f"failed={len(failed)}")
    print(f"errors={dict(error_counts)}")


@pytest.mark.asyncio
@pytest.mark.stress
@pytest.mark.parametrize("total_requests,concurrency", COMPLEX_STRESS_CASES)
async def test_concurrent_complex_model_create_and_update(
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
        sem = asyncio.Semaphore(concurrency)

        async def create_and_update_one(i: int) -> dict:
            async with sem:
                started = time.perf_counter()

                try:
                    run_id = f"{total_requests}-{concurrency}-{i}-{uuid.uuid4()}"

                    initial_person_ids = [
                        await create_person(
                            client,
                            token,
                            f"Complex initial person {run_id}-{person_number}",
                        )
                        for person_number in range(3)
                    ]

                    updated_person_ids = [
                        await create_person(
                            client,
                            token,
                            f"Complex updated person {run_id}-{person_number}",
                        )
                        for person_number in range(2)
                    ]

                    thing_id = await create_subsubthing(
                        client,
                        token,
                        f"Complex SubSubThing {run_id}",
                        initial_person_ids,
                    )

                    await update_subsubthing(
                        client,
                        token,
                        thing_id,
                        f"Complex SubSubThing updated {run_id}",
                        [initial_person_ids[0], *updated_person_ids],
                    )

                    return {
                        "ok": True,
                        "latency": time.perf_counter() - started,
                        "error": None,
                    }

                except httpx.HTTPStatusError as e:
                    return {
                        "ok": False,
                        "latency": time.perf_counter() - started,
                        "error": (
                            f"HTTP {e.response.status_code}: "
                            f"{e.response.text[:500]}"
                        ),
                    }
                
                except (httpx.HTTPError, KeyError) as e:
                    return {
                        "ok": False,
                        "latency": time.perf_counter() - started,
                        "error": f"{type(e).__name__}: {e}",
                    }

        start = time.perf_counter()
        results = await asyncio.gather(
            *(create_and_update_one(i) for i in range(total_requests))
        )

    duration = time.perf_counter() - start
    successful, failed, latencies, error_counts = summarize_results(results)

    print_summary(total_requests, concurrency, successful, failed, error_counts)

    assert latencies, "No successful requests"

    write_stress_stats(
        "complex-create-update-stress",
        total=total_requests,
        concurrency=concurrency,
        duration=duration,
        latencies=latencies,
        extra={
            "error_counts": dict(error_counts),
            "person_nodes_per_request": 5,
            "subsubthing_nodes_per_request": 1,
            "create_edges_per_request": 3,
            "update_edges_per_request": 3,
        },
    )


@pytest.mark.asyncio
@pytest.mark.stress
@pytest.mark.parametrize("total_requests,concurrency", COMPLEX_STRESS_CASES)
async def test_concurrent_complex_model_repeated_updates(
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
        sem = asyncio.Semaphore(concurrency)

        async def repeatedly_update_one(i: int) -> dict:
            async with sem:
                started = time.perf_counter()

                try:
                    run_id = f"{total_requests}-{concurrency}-{i}-{uuid.uuid4()}"

                    person_ids = [
                        await create_person(
                            client,
                            token,
                            f"Repeated update person {run_id}-{person_number}",
                        )
                        for person_number in range(5)
                    ]

                    thing_id = await create_subsubthing(
                        client,
                        token,
                        f"Repeated update SubSubThing {run_id}",
                        person_ids[:3],
                    )

                    await update_subsubthing(
                        client,
                        token,
                        thing_id,
                        f"Repeated update SubSubThing first patch {run_id}",
                        [person_ids[1], person_ids[3], person_ids[4]],
                    )

                    await update_subsubthing(
                        client,
                        token,
                        thing_id,
                        f"Repeated update SubSubThing second patch {run_id}",
                        [person_ids[2], person_ids[4]],
                    )

                    return {
                        "ok": True,
                        "latency": time.perf_counter() - started,
                        "error": None,
                    }

                except httpx.HTTPStatusError as e:
                    return {
                        "ok": False,
                        "latency": time.perf_counter() - started,
                        "error": (
                            f"{e.request.method} {e.request.url.path} -> "
                            f"HTTP {e.response.status_code}: "
                            f"{e.response.text[:500]}"
                        ),
                    }
                except (httpx.HTTPError, KeyError) as e:
                    return {
                        "ok": False,
                        "latency": time.perf_counter() - started,
                        "error": f"{type(e).__name__}: {e}",
                    }

        start = time.perf_counter()
        results = await asyncio.gather(
            *(repeatedly_update_one(i) for i in range(total_requests))
        )

    duration = time.perf_counter() - start
    successful, failed, latencies, error_counts = summarize_results(results)

    print_summary(total_requests, concurrency, successful, failed, error_counts)

    assert latencies, f"No successful requests: {dict(error_counts)}"

    write_stress_stats(
        "complex-repeated-update-stress",
        total=total_requests,
        concurrency=concurrency,
        duration=duration,
        latencies=latencies,
        extra={
            "error_counts": dict(error_counts),
            "person_nodes_per_request": 5,
            "subsubthing_nodes_per_request": 1,
            "create_edges_per_request": 3,
            "first_update_edges_per_request": 3,
            "second_update_edges_per_request": 2,
        },
    )

    assert not failed, (
        f"{len(failed)} of {total_requests} workflows failed: "
        f"{dict(error_counts)}"
    )
