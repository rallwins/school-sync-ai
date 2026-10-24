"""FastAPI runs sync endpoints on a thread pool, so one Store (one SQLite connection) is hit by
several threads at once. A shared sqlite3 connection raised 'bad parameter or other API misuse'
under that load; all Store access must be serialised."""

import threading
from datetime import UTC, datetime

from app.imports.store import ManifestRecord, Store


def test_store_survives_concurrent_use_from_many_threads(tmp_path):
    store = Store(tmp_path / "t.sqlite3")  # file-backed, like the real server
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(15):
                store.audit("t", f"{n}-{i}")
                store.upsert_mapping(
                    ManifestRecord(f"s{n}-{i}", "mock", "c", f"e{i}", "fp", f"b{n}")
                )
                store.manifest("mock", "c")
                store.create_oauth_state(f"st{n}-{i}", "v", now=datetime.now(UTC))
                store.consume_oauth_state(f"st{n}-{i}")
                store.list_imports()
        except BaseException as e:  # noqa: BLE001 - collect anything a thread raises
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [], f"{len(errors)} thread(s) failed, first: {errors[0]!r}"
    assert len(store.manifest("mock", "c")) == 12 * 15
