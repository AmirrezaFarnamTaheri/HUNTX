from huntx.state.db import DBConnection


def test_connection_enables_sqlite_safety_pragmas(tmp_path):
    db = DBConnection(tmp_path / "state.db")

    with db.connect() as conn:
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert foreign_keys == 1
    assert busy_timeout == 30_000
