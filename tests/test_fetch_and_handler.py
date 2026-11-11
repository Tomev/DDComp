"""Tests for fetching from D&D Beyond (mocked transport) and the bot command."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock

import httpx
import pytest
import tableplop

import ddcomp


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def client_returning(status: int, body: Any = None, error: Exception = None):
    requested: List[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if error is not None:
            raise error
        if isinstance(body, (dict, list)):
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=body or "")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), requested


# ---- fetch_character -----------------------------------------------------------------


def test_fetch_success_uses_v5_and_returns_data() -> None:
    client, requested = client_returning(200, {"success": True, "data": {"name": "X"}})
    assert run(tableplop.fetch_character(123, client)) == {"name": "X"}
    assert requested == [
        "https://character-service.dndbeyond.com/character/v5/character/123"
    ]


@pytest.mark.parametrize(
    "status,body,error_type",
    [
        (403, {"success": False}, tableplop.CharacterPrivateError),
        (404, {"success": False}, tableplop.CharacterNotFoundError),
        (500, "oops", tableplop.DDBUnavailableError),
        (200, "not json", tableplop.DDBUnavailableError),
        (200, {"success": False, "data": None}, tableplop.DDBUnavailableError),
        (200, {"success": True, "data": None}, tableplop.DDBUnavailableError),
    ],
)
def test_fetch_error_statuses(status, body, error_type) -> None:
    client, _ = client_returning(status, body)
    with pytest.raises(error_type):
        run(tableplop.fetch_character(1, client))


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")]
)
def test_fetch_network_errors(error) -> None:
    client, _ = client_returning(200, error=error)
    with pytest.raises(tableplop.DDBUnavailableError):
        run(tableplop.fetch_character(1, client))


def test_error_types_share_a_base() -> None:
    for error_type in (
        tableplop.CharacterPrivateError,
        tableplop.CharacterNotFoundError,
        tableplop.DDBUnavailableError,
    ):
        assert issubclass(error_type, tableplop.DDBError)


# ---- /to_tableplop handler -----------------------------------------------------------


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock(), reply_document=AsyncMock())
    return SimpleNamespace(message=message)


def call(args, monkeypatch, fetch) -> SimpleNamespace:
    monkeypatch.setattr(ddcomp.tableplop, "fetch_character", fetch)
    update = make_update()
    run(ddcomp.to_tableplop(update, SimpleNamespace(args=args)))
    return update.message


def test_handler_is_registered_with_docstring() -> None:
    assert ddcomp.commands["to_tableplop"] is ddcomp.to_tableplop
    assert "Tableplop" in ddcomp.to_tableplop.__doc__


@pytest.mark.parametrize("args", [[], ["https://example.com/characters/1"], ["hello"]])
def test_handler_usage(args, monkeypatch) -> None:
    fetch = AsyncMock()
    message = call(args, monkeypatch, fetch)
    fetch.assert_not_called()
    text = message.reply_text.call_args.args[0]
    assert text.startswith("Usage: /to_tableplop")


@pytest.mark.parametrize(
    "error,expected",
    [
        (tableplop.CharacterPrivateError(1), "Public"),
        (tableplop.CharacterNotFoundError(1), "no character"),
        (tableplop.DDBUnavailableError("x"), "Could not reach"),
    ],
)
def test_handler_fetch_errors(error, expected, monkeypatch) -> None:
    message = call(
        ["https://www.dndbeyond.com/characters/1"],
        monkeypatch,
        AsyncMock(side_effect=error),
    )
    message.reply_document.assert_not_called()
    assert expected in message.reply_text.call_args.args[0]


def test_handler_conversion_failure(monkeypatch) -> None:
    message = call(
        ["https://www.dndbeyond.com/characters/1"],
        monkeypatch,
        AsyncMock(return_value={"classes": "broken"}),
    )
    message.reply_document.assert_not_called()
    assert "could not be converted" in message.reply_text.call_args.args[0]


def test_handler_sends_document(character, monkeypatch) -> None:
    fetch = AsyncMock(return_value=character)
    message = call(
        ["https://www.dndbeyond.com/characters/4242/mira"], monkeypatch, fetch
    )
    fetch.assert_awaited_once_with(4242)
    kwargs = message.reply_document.call_args.kwargs
    assert kwargs["filename"] == "mira_quickfoot_co_tableplop.json"
    sheet = json.loads(kwargs["document"].decode("utf-8"))
    assert sheet["type"] == "tableplop-character-v2"
    assert "Import" in kwargs["caption"] and "D&D Beyond" in kwargs["caption"]
    assert len(kwargs["caption"].splitlines()) in (2, 3)
