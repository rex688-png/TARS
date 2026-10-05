import json
import io
import os
import pytest
import queue
import time

import src.lib.StatusParser as status_parser_module
from src.lib.StatusParser import StatusParser, parse_odyssey_flags, parse_status_json

@pytest.fixture
def status_file_path(tmp_path):
    status_data = {
        "event": "Status",
        "timestamp": "2024-11-12T13:14:15Z",
        "Flags": 16777216,
        "GuiFocus": 0
    }
    file_path = tmp_path / "Status.json"
    with open(file_path, "w") as f:
        json.dump(status_data, f)
    return tmp_path

def test_statusparser_file_update(status_file_path):
    parser = StatusParser(str(status_file_path))
    time.sleep(0.1)  # Let the watch thread start
    
    # Update file with new status: not landed
    old_status = {
        "Flags": 16777218,
        "GuiFocus": 1
    }

    with open(os.path.join(status_file_path, "Status.json"), "w") as f:
        json.dump(old_status, f)

    # Wait for update
    status_event = parser.status_queue.get(timeout=1)
    assert status_event["event"] == "Status"
    assert status_event["flags"]["LandingGearDown"] == False

    # Update file with new status: landed
    new_status = {
        "Flags": 16777220,
        "GuiFocus": 1
    }

    with open(os.path.join(status_file_path, "Status.json"), "w") as f:
        json.dump(new_status, f)

    # Wait for update
    status_event = parser.status_queue.get(timeout=10)
    assert status_event["event"] == "Status"
    assert status_event["flags"]["LandingGearDown"] == True

    landinggear_event = parser.status_queue.get(timeout=10)
    assert landinggear_event["event"] == "LandingGearDown"


def test_parse_odyssey_flags_sco_and_sca():
    flags = parse_odyssey_flags(1048576 | 2097152)

    assert flags["ActiveSCO"] is True
    assert flags["ActiveSCA"] is True
    assert flags["FsdHyperdriveCharging"] is False


@pytest.mark.parametrize(
    ("old_flags2", "new_flags2", "expected_event"),
    [
        (0, 1048576, "SCOActivated"),
        (1048576, 0, "SCODeactivated"),
        (0, 2097152, "SCAActivated"),
        (2097152, 0, "SCADeactivated"),
    ],
)
def test_create_delta_events_for_sco_and_sca(old_flags2, new_flags2, expected_event):
    old_status = parse_status_json({"Flags": 16777216, "Flags2": old_flags2})
    new_status = parse_status_json({"Flags": 16777216, "Flags2": new_flags2})
    parser = StatusParser.__new__(StatusParser)

    assert parser._create_delta_events(old_status, new_status) == [{"event": expected_event}]


def _reader(file_path, monkeypatch):
    parser = StatusParser.__new__(StatusParser)
    parser.file_path = str(file_path)
    monkeypatch.setattr(status_parser_module, "sleep", lambda _: None)
    return parser


def test_status_read_valid_json(tmp_path, monkeypatch):
    status_file = tmp_path / "Status.json"
    status_file.write_text('{"Flags": 16777216}', encoding="utf-8")

    assert _reader(status_file, monkeypatch)._read_status_file() == {"Flags": 16777216}


@pytest.mark.parametrize("content", ["", '{"Flags":'])
def test_status_read_empty_or_malformed_returns_none(tmp_path, monkeypatch, content):
    status_file = tmp_path / "Status.json"
    status_file.write_text(content, encoding="utf-8")

    assert _reader(status_file, monkeypatch)._read_status_file() is None


def test_status_read_retries_malformed_then_accepts_valid(monkeypatch):
    documents = iter(['{"Flags":', '{"Flags": 16777216}'])
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: io.StringIO(next(documents)))
    parser = _reader("unused", monkeypatch)

    assert parser._read_status_file() == {"Flags": 16777216}


def test_repeated_malformed_status_does_not_raise(tmp_path, monkeypatch):
    status_file = tmp_path / "Status.json"
    status_file.write_text("not-json", encoding="utf-8")
    parser = _reader(status_file, monkeypatch)

    assert parser._read_status_file() is None
    assert parser._read_status_file() is None


def test_malformed_update_keeps_previous_valid_status(tmp_path, monkeypatch):
    status_file = tmp_path / "Status.json"
    status_file.write_text("", encoding="utf-8")
    parser = _reader(status_file, monkeypatch)
    previous = parse_status_json({"Flags": 16777216, "GuiFocus": 0})
    parser.current_status = previous
    parser.status_queue = queue.Queue()

    assert parser._process_status_update() is False
    assert parser.current_status is previous
    assert parser.status_queue.empty()
