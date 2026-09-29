from __future__ import annotations

import pytest


def _item_paths(item_id: int | str) -> list[tuple[str, str, dict[str, object] | None]]:
    return [
        ("PATCH", f"/api/notes/{item_id}", {"text": "x"}),
        ("DELETE", f"/api/notes/{item_id}", None),
        ("DELETE", f"/api/reminders/{item_id}", None),
        ("DELETE", f"/api/habits/{item_id}", None),
        ("PUT", f"/api/habits/{item_id}/marks/2026-09-28", {"done": True}),
    ]


@pytest.mark.parametrize("item_id", [2**63, 10**30, 0, -1])
async def test_ids_out_of_range_are_422(client, auth, item_id) -> None:
    for method, path, body in _item_paths(item_id):
        response = await client.request(method, path, json=body, headers=auth())
        assert response.status_code == 422, (method, path)
        assert response.json()["code"] == "validation_error"


async def test_largest_id_is_merely_not_found(client, auth) -> None:
    for method, path, body in _item_paths(2**63 - 1):
        response = await client.request(method, path, json=body, headers=auth())
        assert response.status_code == 404, (method, path)
