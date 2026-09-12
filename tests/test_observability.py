"""Authentication tests for the HW2 endpoint. Offline: no Langfuse, Docker, or model key."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from server import app as server_app


def test_create_session_rejects_role_mismatch(world: dict) -> None:
    server_app._SESSIONS.clear()
    with pytest.raises(HTTPException) as exc_info:
        server_app.create_session(server_app.SessionCreate(user_id=1, role="merchant"))
    assert exc_info.value.status_code == 403


def test_token_cannot_authorize_a_different_session(world: dict) -> None:
    server_app._SESSIONS.clear()
    session_a = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))
    session_b = server_app.create_session(server_app.SessionCreate(user_id=9001, role="merchant"))

    with pytest.raises(HTTPException) as exc_info:
        server_app._authorize(session_b["session_id"], f"Bearer {session_a['token']}")
    assert exc_info.value.status_code == 403
