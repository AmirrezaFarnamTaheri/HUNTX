from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from huntx.connectors.telegram.connector import TelegramConnector


def _response(payload: dict[str, object]) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps(payload).encode("utf-8")
    return response


@patch("urllib.request.urlopen")
def test_request_timeout_is_clamped_to_remaining_deadline(mock_urlopen: MagicMock) -> None:
    connector = TelegramConnector("123:token", "1")
    connector.deadline = time.time() + 0.5
    mock_urlopen.return_value = _response({"ok": True})

    assert connector._make_request("getMe")["ok"] is True
    assert mock_urlopen.call_args.kwargs["timeout"] < 1


def test_request_refuses_work_after_deadline() -> None:
    connector = TelegramConnector("123:token", "1")
    connector.deadline = time.time() - 0.01

    with pytest.raises(TimeoutError, match="deadline exceeded"):
        connector._make_request("getMe")
