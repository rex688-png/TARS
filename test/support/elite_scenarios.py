"""Reusable synthetic Elite scenarios read through the production journal parser."""

from pathlib import Path
from queue import Queue
import json

from src.lib.EDJournal import EDJournal
from src.lib.Event import GameEvent


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "elite"


def install_journal(directory: Path, scenario: str, name: str = "Journal.2026-01-01T120000.01.log") -> Path:
    """Install a scenario as the filename that Elite's journal reader expects."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / name
    destination.write_bytes((FIXTURES / f"{scenario}.jsonl").read_bytes())
    if scenario == "journey":
        (directory / "NavRoute.json").write_bytes((FIXTURES / "nav_route.json").read_bytes())
    return destination


def read_history(directory: Path) -> EDJournal:
    """Read actual EDJournal history without starting an unbounded watcher thread."""
    reader = EDJournal.__new__(EDJournal)
    reader.logs_path = str(directory)
    reader.events = Queue()
    reader.historic_events = []
    reader.load_history()
    return reader


def game_events(reader: EDJournal) -> list[GameEvent]:
    return [GameEvent(content=entry, historic=True) for entry in reader.historic_events]


def status_document(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
