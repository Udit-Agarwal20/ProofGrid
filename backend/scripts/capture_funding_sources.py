"""Capture public announcements through the production robots/SSRF policy."""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.application.acquisition.http import SafeHttpAcquirer  # noqa: E402
from app.core.errors import ProofGridError  # noqa: E402

SOURCES = [
    ("sarvam-series-a.html", "https://www.sarvam.ai/blogs/announcing-series-a"),
    (
        "neysa-seed.html",
        "https://neysa.ai/press-release/neysa-raises-20-million-in-seed-funding-to-accelerate-generative-ai-adoption-for-enterprises/",
    ),
]


async def main() -> None:
    target = Path(__file__).resolve().parents[1] / "app" / "fixtures" / "captured_funding"
    client = SafeHttpAcquirer()
    manifest = []
    for filename, url in SOURCES:
        try:
            document = await client.fetch(url)
        except ProofGridError as exc:
            print(json.dumps({"source": url, "status": exc.code}))
            continue
        target.mkdir(parents=True, exist_ok=True)
        (target / filename).write_bytes(document.content.encode("utf-8"))
        data = document.model_dump(mode="json", exclude={"content"})
        data.update(file=filename, acquisition_method="FIXTURE")
        data["metadata"].update(
            first_party=True,
            synthetic=False,
            original_acquisition_method=document.acquisition_method,
            capture_sha256=hashlib.sha256(document.content.encode()).hexdigest(),
            fixture_label="Captured public historical company announcement; original dates retained",
        )
        manifest.append(data)
        print(
            json.dumps(
                {"source": url, "status": "CAPTURED", "bytes": len(document.content.encode())}
            )
        )
    if manifest:
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    else:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
