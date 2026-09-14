from pathlib import Path

from tophost_api.client.state import SecureStateStore


def test_secure_state_store_roundtrip(tmp_path: Path):
    path = tmp_path / "state" / "auth.json"

    SecureStateStore.write(
        path,
        {
            "hello": "world",
        },
    )

    assert SecureStateStore.read(path) == {
        "hello": "world"
    }

    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_secure_state_delete(tmp_path: Path):
    path = tmp_path / "state.json"

    SecureStateStore.write(
        path,
        {"x": 1},
    )

    SecureStateStore.delete(path)

    assert not path.exists()
