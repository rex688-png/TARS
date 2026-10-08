import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def test_lynx_highliner_has_medium_pad_size():
    ship_sizes = json.loads((ROOT / "src" / "assets" / "ship_sizes.json").read_text())

    assert ship_sizes["mediumtransport01"] == "M"


def test_lynx_highliner_is_known_ship_name():
    from lib.actions.data import known_ships

    assert "Lynx Highliner" in known_ships
    assert "Panther Clipper MkII" in known_ships
    assert "Python" in known_ships


def test_caspian_explorer_model_is_separate_from_commander_ship_name():
    from lib.Event import GameEvent
    from lib.projections.ship_info import ShipInfo, ShipInfoStateModel

    saved = ShipInfoStateModel.model_validate({"Name": "eXPY", "Type": "explorer_nx"})
    assert saved.Model == "Caspian Explorer"

    projection = ShipInfo()
    projection.process(GameEvent(historic=False, content={
        "event": "Loadout", "Ship": "explorer_nx", "ShipName": "eXPY",
        "ShipIdent": "EXP-01", "Modules": [], "timestamp": "2026-10-08T00:00:00Z",
    }))
    assert projection.state.Name == "eXPY"
    assert projection.state.Type == "explorer_nx"
    assert projection.state.Model == "Caspian Explorer"
