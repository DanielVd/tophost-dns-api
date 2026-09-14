from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from tophost_api.errors import UpstreamProtocolError


class SecureStateStore:
    """Small atomic JSON state store for authentication material."""

    @staticmethod
    def read(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise UpstreamProtocolError(
                f"Unable to read authentication state: {path.name}"
            ) from exc

        if not isinstance(data, dict):
            raise UpstreamProtocolError(
                f"Invalid authentication state: {path.name}"
            )

        return data

    @staticmethod
    def write(
        path: Path,
        data: dict[str, Any],
    ) -> None:
        path.parent.mkdir(
            mode=0o700,
            parents=True,
            exist_ok=True,
        )
        path.parent.chmod(0o700)

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=path.parent,
            text=True,
        )

        temporary = Path(temporary_name)

        try:
            os.fchmod(fd, 0o600)

            with os.fdopen(fd, "w") as handle:
                json.dump(
                    data,
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                temporary,
                path,
            )
            path.chmod(0o600)

        except Exception:
            temporary.unlink(
                missing_ok=True
            )
            raise

    @staticmethod
    def delete(path: Path) -> None:
        path.unlink(
            missing_ok=True
        )
