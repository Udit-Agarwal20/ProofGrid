import pytest

from app.application.acquisition.safety import canonical_url
from app.core.errors import ProofGridError


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://169.254.169.254/latest",
        "http://[::1]",
        "http://[fd00::1]",
        "http://[fe80::1]",
        "http://[::ffff:127.0.0.1]",
        "http://2130706433",
        "http://0177.0.0.1",
        "http://0x7f000001",
        "http://127.1",
        "http://user:secret@example.com",
        "http://example.com:22",
        "http://metadata.google.internal",
        "http://example.com\\@localhost",
        "http://[ff02::1]",
        "http://0.0.0.0",
    ],
)
def test_blocks_unsafe_urls(url: str) -> None:
    with pytest.raises(ProofGridError):
        canonical_url(url)


def test_canonical_url_keeps_meaningful_query() -> None:
    assert (
        canonical_url("https://EXAMPLE.com/a?utm_source=x&b=2&a=1#foo")
        == "https://example.com/a?a=1&b=2"
    )


async def test_redirect_to_metadata_is_rejected_before_connecting() -> None:
    import httpx

    from app.application.acquisition.http import SafeHttpAcquirer

    calls = []

    async def resolver(url: str) -> tuple[str, list[str]]:
        return canonical_url(url), ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    client = SafeHttpAcquirer(resolver=resolver, transport=httpx.MockTransport(handler))
    with pytest.raises(ProofGridError, match="eligible"):
        await client.fetch("https://example.com/source")
    assert len(calls) == 2


async def test_dns_pinning_host_header_and_stream_size() -> None:
    import httpx

    from app.application.acquisition.http import SafeHttpAcquirer

    async def resolver(url: str) -> tuple[str, list[str]]:
        return canonical_url(url), ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="x" * 500, headers={"content-type": "text/html"})

    client = SafeHttpAcquirer(
        max_bytes=100, resolver=resolver, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProofGridError, match="size limit"):
        await client.fetch("https://example.com/source")


async def test_robots_disallow_is_terminal() -> None:
    import httpx

    from app.application.acquisition.http import SafeHttpAcquirer

    async def resolver(url: str) -> tuple[str, list[str]]:
        return canonical_url(url), ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(
            200, text="User-agent: *\nDisallow: /", headers={"content-type": "text/plain"}
        )

    client = SafeHttpAcquirer(resolver=resolver, transport=httpx.MockTransport(handler))
    with pytest.raises(ProofGridError, match="robots"):
        await client.fetch("https://example.com/source")


async def test_redirect_destination_gets_its_own_robots_check() -> None:
    import httpx

    from app.application.acquisition.http import SafeHttpAcquirer

    calls: list[tuple[str, str]] = []

    async def resolver(url: str) -> tuple[str, list[str]]:
        return canonical_url(url), ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        calls.append((host, request.url.path))
        if request.url.path == "/robots.txt":
            if host == "destination.example":
                return httpx.Response(
                    200, text="User-agent: *\nDisallow: /", headers={"content-type": "text/plain"}
                )
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "https://destination.example/page"})

    with pytest.raises(ProofGridError, match="robots"):
        await SafeHttpAcquirer(resolver=resolver, transport=httpx.MockTransport(handler)).fetch(
            "https://original.example/start"
        )
    assert ("destination.example", "/robots.txt") in calls
    assert ("destination.example", "/page") not in calls
