"""Scan Git candidate files for configured secret values without printing those values."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import SecretStr  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    settings = get_settings()
    secrets = {
        name: value.get_secret_value().encode()
        for name, value in settings.__dict__.items()
        if isinstance(value, SecretStr) and len(value.get_secret_value()) >= 12
    }
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    )
    findings = []
    scanned = 0
    for name in set(paths):
        path = root / name
        if not name or not path.is_file():
            continue
        data = path.read_bytes()
        scanned += 1
        for key, value in secrets.items():
            if value in data:
                findings.append((name, key))
    for name, key in findings:
        print(f"Configured secret detected: {name} ({key}; value suppressed)")
    print(f"Scanned {scanned} Git candidate files; configured-secret matches: {len(findings)}")
    raise SystemExit(bool(findings))


if __name__ == "__main__":
    main()
