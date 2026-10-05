"""Signed HTTP delivery with DNS validation immediately before a pinned connection."""

import hashlib
import hmac
import ipaddress
import json
import re
import socket
import time
from collections.abc import Callable
from ipaddress import IPv4Address, IPv6Address
from urllib.parse import urlsplit

import httpx

from eventflow.config import get_settings
from eventflow.delivery import ClaimedDelivery

Address = IPv4Address | IPv6Address
Resolver = Callable[[str], list[Address]]


class UnsafeDestination(Exception):
    pass


def resolve_public(host: str) -> list[Address]:
    addresses = {
        ipaddress.ip_address(item[4][0])
        for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    }
    if not addresses or any(not public_address(address) for address in addresses):
        raise UnsafeDestination("DNS returned a non-public address")
    return sorted(addresses, key=str)


def public_address(address: Address) -> bool:
    return address.is_global and not (
        isinstance(address, IPv6Address)
        and (address.ipv4_mapped or address.sixtofour or address.teredo)
    )


def validated_destination(
    raw_url: str, resolver: Resolver = resolve_public
) -> tuple[httpx.URL, str]:
    settings = get_settings()
    if settings.local_test_receiver_url and raw_url == settings.local_test_receiver_url:
        if settings.environment == "production":
            raise UnsafeDestination("Local receiver is forbidden in production")
        url = httpx.URL(raw_url)
        if url.scheme != "http" or url.host not in ("127.0.0.1", "localhost"):
            raise UnsafeDestination("Test receiver must use loopback HTTP")
        return url, url.host
    try:
        url = httpx.URL(raw_url)
    except httpx.InvalidURL as exc:
        raise UnsafeDestination("Invalid URL") from exc
    host = url.host
    authority = urlsplit(raw_url).netloc
    if (
        url.scheme != "https"
        or url.port not in (None, 443)
        or host is None
        or url.username
        or url.password
        or url.fragment
        or "%" in authority
        or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host)
        or any(label.startswith("-") or label.endswith("-") for label in host.split("."))
    ):
        raise UnsafeDestination("URL violates the HTTPS destination policy")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeDestination("IP literal destinations are forbidden")
    addresses = resolver(host)
    if not addresses or any(not public_address(address) for address in addresses):
        raise UnsafeDestination("DNS returned a non-public address")
    return url.copy_with(host=str(addresses[0])), host


def signed_request(claim: ClaimedDelivery) -> tuple[bytes, dict[str, str]]:
    timestamp = str(int(time.time()))
    body = json.dumps(
        {
            "event_id": str(claim.event_id),
            "delivery_id": str(claim.delivery_id),
            "generation": claim.generation,
            "type": claim.event_type,
            "version": 1,
            "payload": claim.payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(
        claim.secret, timestamp.encode("ascii") + b"." + body, hashlib.sha256
    ).hexdigest()
    return body, {
        "Host": "",  # Replaced after URL validation.
        "Content-Type": "application/json",
        "User-Agent": "EventFlow/0.1",
        "X-EventFlow-Event-Id": str(claim.event_id),
        "X-EventFlow-Delivery-Id": str(claim.delivery_id),
        "X-EventFlow-Generation": str(claim.generation),
        "X-EventFlow-Timestamp": timestamp,
        "X-EventFlow-Signature": f"v1={signature}",
    }


def send_webhook(claim: ClaimedDelivery, resolver: Resolver = resolve_public) -> int:
    url, host = validated_destination(claim.url, resolver)
    body, headers = signed_request(claim)
    headers["Host"] = host if url.port in (None, 80, 443) else f"{host}:{url.port}"
    with httpx.Client(
        trust_env=False,
        follow_redirects=False,
        http2=False,
        timeout=httpx.Timeout(connect=5, read=10, write=5, pool=2),
    ) as client:
        request = client.build_request("POST", url, headers=headers, content=body)
        if url.scheme == "https":
            request.extensions["sni_hostname"] = host
        response = client.send(request, stream=True)
        try:
            return response.status_code
        finally:
            response.close()
