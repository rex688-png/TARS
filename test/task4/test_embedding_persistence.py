from pathlib import Path
import sys
import threading

import pysqlite3 as sqlite3
import sqlite_vec


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lib import Database as database_module
from lib.Database import VectorStore, set_connection_for_testing
from lib.Models import EmbeddingModel


class FixtureEmbeddingModel(EmbeddingModel):
    def __init__(self):
        super().__init__("fixture-embedding")

    def create_embedding(self, input_text: str) -> tuple[str, list[float]]:
        return self.model_name, [float(len(input_text)), 1.0, 0.5]


def _connection(path: Path):
    connection = sqlite3.connect(str(path))
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    return connection


def test_embedding_generation_persists_and_reloads_after_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(database_module, "_thread_local", threading.local())
    database = tmp_path / "tars.db"
    model = FixtureEmbeddingModel()
    first_connection = _connection(database)
    set_connection_for_testing(first_connection)
    first_store = VectorStore("alpha_memory")
    model_name, vector = model.create_embedding("Sol")
    first_store.store(model_name, "Commander visited Sol", vector, {"system": "Sol"})
    first_connection.close()

    second_connection = _connection(database)
    set_connection_for_testing(second_connection)
    second_store = VectorStore("alpha_memory")
    second_store.initialize(model_name, len(vector))
    results = second_store.search("Sol", model_name, vector, n=1)

    assert results[0]["content"] == "Commander visited Sol"
    assert results[0]["metadata"] == {"system": "Sol"}
    second_connection.close()
