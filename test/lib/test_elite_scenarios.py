"""Contract scenarios: saved history, live journal tail and state projections."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test" / "support"))
from elite_scenarios import game_events, install_journal, read_history, status_document


@pytest.mark.parametrize("scenario, expected", [
    ("journey", ["Commander", "LoadGame", "Docked", "Undocked", "SupercruiseEntry", "StartJump", "FSDJump", "FSSDiscoveryScan", "SAAScanComplete", "FSSBodySignals", "Touchdown", "LaunchSRV", "ScanOrganic", "NavRouteClear"]),
    ("last_known", ["Commander", "Location"]),
    ("new_session", ["Commander", "Location", "Loadout"]),
    ("no_route", ["Location", "NavRouteClear"]),
    ("malformed", ["Commander", "Location"]),
])
def test_synthetic_scenarios_use_production_journal_history(tmp_path, scenario, expected):
    install_journal(tmp_path, scenario)
    reader = read_history(tmp_path)
    names = [event.content["event"] for event in game_events(reader)]
    assert all(name in names for name in expected)
    assert all(event.historic for event in game_events(reader))
    assert reader.events.empty()  # saved history is not a live journal signal


def test_empty_or_missing_journal_is_not_live(tmp_path):
    reader = read_history(tmp_path / "missing")
    assert reader.historic_events == []
    assert reader.events.empty()


def test_newest_session_replaces_old_saved_history(tmp_path):
    old = install_journal(tmp_path, "last_known", "Journal.2025-01-01T000000.01.log")
    new = install_journal(tmp_path, "new_session", "Journal.2026-01-02T080000.01.log")
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))
    reader = read_history(tmp_path)
    assert {event["event"] for event in reader.historic_events} >= {"Location", "Loadout"}
    assert next(event for event in reader.historic_events if event["event"] == "Location")["StarSystem"] == "LHS 3447"
    assert all(new.name in event["id"] for event in reader.historic_events)


def test_appended_event_enters_real_live_queue_after_saved_history(tmp_path, monkeypatch):
    journal = install_journal(tmp_path, "last_known")
    reader = read_history(tmp_path)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": "2026-01-02T08:00:00Z", "event": "Undocked", "StationName": "Galileo"}) + "\n")

    import src.lib.EDJournal as journal_module
    class EndOfTail(Exception):
        pass
    def end_tail(_seconds):
        raise EndOfTail
    monkeypatch.setattr(journal_module, "sleep", end_tail)
    with pytest.raises(EndOfTail):
        reader._reading_loop()
    live = reader.events.get_nowait()
    assert live["event"] == "Undocked"
    assert live["id"].endswith(".000004")
    assert not any(event["event"] == "Undocked" for event in reader.historic_events)


def test_synthetic_status_fuel_passes_existing_status_parser():
    from src.lib.StatusParser import parse_status_json
    normal = parse_status_json(status_document("status_normal"))
    low = parse_status_json(status_document("status_low_fuel"))
    assert normal["Fuel"]["FuelMain"] == 24.7
    assert low["Fuel"]["FuelMain"] == 2.1
    assert normal["Destination"]["Name"] == "Alpha Centauri A 1"


def test_journey_projects_authoritative_ship_location_and_exobiology(tmp_path):
    from src.lib.projections.commander import Commander
    from src.lib.projections.exobiology_scan import ExobiologyScan
    from src.lib.projections.location import Location
    from src.lib.projections.ship_info import ShipInfo

    install_journal(tmp_path, "journey")
    events = game_events(read_history(tmp_path))
    commander, ship, location, biology = Commander(), ShipInfo(), Location(), ExobiologyScan()
    snapshots = {}
    discoveries = []
    for event in events:
        for projection in (commander, ship, location, biology):
            result = projection.process(event) or []
            discoveries.extend(item.content["event"] for item in result if item.content.get("event", "").startswith("ScanOrganic"))
        if event.content["event"] in {"Docked", "SupercruiseEntry", "FSDJump", "Touchdown"}:
            snapshots[event.content["event"]] = location.state.model_copy(deep=True)

    assert commander.state.Name == "Fixture Commander"
    assert (ship.state.Name, ship.state.Model) == ("eXPY", "Caspian Explorer")
    assert snapshots["Docked"].Station == "Galileo"
    assert snapshots["SupercruiseEntry"].StarSystem == "Sol"
    assert snapshots["FSDJump"].StarSystem == "Alpha Centauri"
    assert snapshots["Touchdown"].Landed is True
    assert "ScanOrganicFirst" in discoveries and "ScanOrganicSecond" in discoveries


def test_partial_valid_location_event_uses_projection_defaults(tmp_path):
    from src.lib.projections.location import Location

    install_journal(tmp_path, "malformed")
    location = Location()
    for event in game_events(read_history(tmp_path)):
        location.process(event)
    assert location.state.StarSystem == "Sol"
    assert location.state.Docked is True
    assert location.state.StarPos == [0.0, 0.0, 0.0]


def test_route_available_then_cleared_from_parsed_events(tmp_path):
    from src.lib.projections.nav_info import NavInfo

    class NoNetworkSystemDb:
        def fetch_multiple_systems_nonblocking(self, _names):
            pass
        def get_bodies(self, _name):
            return []

    install_journal(tmp_path, "journey")
    nav = NavInfo(NoNetworkSystemDb())
    had_route = False
    for event in game_events(read_history(tmp_path)):
        nav.process(event)
        had_route |= bool(nav.state.NavRoute)
    assert had_route
    assert nav.state.NavRoute == []  # no route is an ordinary state
