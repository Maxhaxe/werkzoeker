"""
Unit tests for all Telegram bot commands in bot_commands.py
"""

import pytest
import os
import json
from unittest.mock import AsyncMock
from pathlib import Path
from bot_commands import TelegramCommandHandler

@pytest.fixture
def temp_keywords(tmp_path):
    kw_file = tmp_path / "keywords.json"
    data = {
        "functiebenamingen": {"eplan engineer": 4},
        "vakkennis": {"hoogspanning": 3},
        "custom": {"scada": 3},
        "disabled": []
    }
    kw_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return kw_file

@pytest.fixture
def handler(temp_keywords):
    h = TelegramCommandHandler()
    h.keywords_file = temp_keywords
    h._send = AsyncMock()
    h._active_chat_id = "123456"
    return h

@pytest.mark.asyncio
async def test_cmd_start(handler):
    await handler._cmd_start("")
    assert handler._send.called
    sent_text = handler._send.call_args[0][0]
    assert "Welkom" in sent_text
    assert "123456" in handler.allowed_chat_ids

@pytest.mark.asyncio
async def test_cmd_help(handler):
    await handler._cmd_help("")
    assert handler._send.called
    assert "/status" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_groep(handler):
    await handler._cmd_groep("")
    assert handler._send.called
    assert "123456" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_status(handler):
    await handler._cmd_status("")
    assert handler._send.called
    assert "WerkZoeker Status" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_platformen(handler):
    await handler._cmd_platformen("")
    assert handler._send.called
    assert "Ondersteunde Databronnen" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_zoektermen(handler):
    await handler._cmd_zoektermen("")
    assert handler._send.called
    assert "Actieve Zoektermen" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_keywords(handler):
    await handler._cmd_keywords("")
    assert handler._send.called
    assert "Actieve trefwoorden" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_add_and_remove(handler):
    # Test add with colon
    await handler._cmd_add("plc:4")
    assert handler._send.called
    assert "plc" in handler._send.call_args[0][0]

    # Test add with space
    await handler._cmd_add("domotica 3")
    assert "domotica" in handler._send.call_args[0][0]

    # Test remove existing keyword from section
    await handler._cmd_remove("hoogspanning")
    assert "verwijderd" in handler._send.call_args[0][0]

    # Test remove non-existing
    await handler._cmd_remove("nietbestaandwoord")
    assert "niet gevonden" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_disable(handler):
    await handler._cmd_disable("eplan engineer")
    assert "uitgeschakeld" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_threshold(handler, monkeypatch):
    monkeypatch.setenv("SCORE_THRESHOLD", "6")
    await handler._cmd_threshold("8")
    assert os.getenv("SCORE_THRESHOLD") == "8"
    assert "8 punten" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_startfilter(handler, monkeypatch):
    monkeypatch.setenv("MAX_START_MONTHS_AHEAD", "6")
    await handler._cmd_startfilter("3")
    assert os.getenv("MAX_START_MONTHS_AHEAD") == "3"
    assert "3 maanden" in handler._send.call_args[0][0]

    await handler._cmd_startfilter("0")
    assert os.getenv("MAX_START_MONTHS_AHEAD") == ""
    assert "uitgeschakeld" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_dagoverzicht(handler):
    await handler._cmd_dagoverzicht("")
    assert handler._send.called

@pytest.mark.asyncio
async def test_handle_update_dispatch(handler):
    update = {
        "update_id": 999,
        "message": {
            "text": "/help",
            "chat": {"id": 123456, "type": "private"}
        }
    }
    await handler._handle_update(update)
    assert handler._send.called
    assert "/status" in handler._send.call_args[0][0]

@pytest.mark.asyncio
async def test_handle_update_unknown_command(handler):
    update = {
        "update_id": 1000,
        "message": {
            "text": "/foobar",
            "chat": {"id": 123456, "type": "private"}
        }
    }
    await handler._handle_update(update)
    assert handler._send.called
    assert "Onbekend commando" in handler._send.call_args[0][0]
