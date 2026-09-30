"""Canonical URL and DNS policy. Every redirect is checked and connection IPs are pinned."""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tldextract

from app.core.errors import ProofGridError

_extract = tldextract.TLDExtract(
    suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True
)


def registrable_domain(host: str) -> str:
    parsed = _extract(host)
    return parsed.top_domain_under_public_suffix or host.lower()


def canonical_url(value: str) -> str:
    try:
        if re.search(r"[\x00-\x20\\]", value):
            raise ValueError
        p = urlsplit(value)
        if p.scheme.lower() not in {"http", "https"} or not p.hostname:
            raise ValueError
        if p.username is not None or p.password is not None or p.port not in (None, 80, 443):
            raise ValueError
        host = p.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if (
            "%" in host
            or host in {"localhost", "metadata.google.internal"}
            or host.endswith((".localhost", ".local", ".internal"))
        ):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Reject inet_aton variants (integer, short, octal and hexadecimal IPs).
            if re.fullmatch(r"[0-9.]+", host) or re.fullmatch(
                r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", host
            ):
                raise ValueError from None
        else:
            if (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or getattr(address, "ipv4_mapped", None)
            ):
                raise ValueError
        netloc = f"[{host}]" if ":" in host else host
        if p.port:
            netloc += f":{p.port}"
        query = urlencode(
            sorted(
                (k, v)
                for k, v in parse_qsl(p.query, keep_blank_values=True)
                if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
            )
        )
        return urlunsplit((p.scheme.lower(), netloc, p.path or "/", query, ""))
    except (ValueError, UnicodeError):
        raise ProofGridError(
            "UNSAFE_URL", "URL is not an eligible public HTTP destination."
        ) from None


async def resolve_public(url: str) -> tuple[str, list[str]]:
    normalized = canonical_url(url)
    p = urlsplit(normalized)
    try:
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(
                p.hostname, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM
            ),
            timeout=5,
        )
    except (OSError, TimeoutError):
        raise ProofGridError(
            "SOURCE_DNS_FAILURE", "Source hostname could not be resolved.", retryable=True
        ) from None
    ips = sorted({str(row[4][0]) for row in addresses})
    if not ips:
        raise ProofGridError("UNSAFE_URL", "Source did not resolve to a public address.")
    for value in ips:
        address = ipaddress.ip_address(value)
        if (
            not address.is_global
            or address.is_multicast
            or address.is_reserved
            or getattr(address, "ipv4_mapped", None)
        ):
            raise ProofGridError("UNSAFE_URL", "Source resolved to a prohibited address.")
    return normalized, ips
