"""Bounded public GETs with DNS pinning; no proxy, cookies or credential forwarding."""

import http.client
import ipaddress
import queue
import socket
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 5 * 1024 * 1024
_DNS_SLOTS = threading.BoundedSemaphore(8)


def public_url(value: str) -> str:
    if len(value) > 1000 or any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("Unsafe public URL")
    p = urlsplit(value)
    if (
        p.scheme not in {"http", "https"}
        or not p.hostname
        or p.username is not None
        or p.password is not None
    ):
        raise ValueError("Unsafe public URL")
    host = p.hostname.lower().rstrip(".")
    if p.port not in {None, 80 if p.scheme == "http" else 443}:
        raise ValueError("Nonstandard port")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(
        (".localhost", ".local", ".internal")
    ):
        raise ValueError("Private host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Private address")
    return value


def public_addresses(host: str, port: int, timeout: float = 10) -> list[str]:
    # A stuck OS resolver cannot consume unbounded worker time or thread count.
    if not _DNS_SLOTS.acquire(blocking=False):
        raise httpx.ConnectTimeout("DNS capacity exhausted")
    result = queue.Queue(maxsize=1)

    def resolve():
        try:
            result.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except Exception as exc:
            result.put(exc)
        finally:
            _DNS_SLOTS.release()

    threading.Thread(target=resolve, daemon=True).start()
    try:
        answers = result.get(timeout=min(timeout, 10))
    except queue.Empty as exc:
        raise httpx.ConnectTimeout("DNS deadline exceeded") from exc
    if isinstance(answers, Exception):
        raise httpx.ConnectError("Public DNS resolution failed") from answers
    addresses = sorted({item[4][0] for item in answers})
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("DNS resolved to a nonpublic address")
    return addresses


def public_get(
    url: str, *, timeout: float = 10, headers: dict | None = None, redirects: int = 3
) -> httpx.Response:
    """Resolve each hop once, pin its IP, and retain the hostname for TLS verification."""
    for hop in range(redirects + 1):
        public_url(url)
        p = urlsplit(url)
        port = p.port or (443 if p.scheme == "https" else 80)
        addresses = public_addresses(p.hostname, port, timeout)
        connection = http.client.HTTPConnection(p.hostname, port, timeout=min(timeout, 10))
        try:
            sock = socket.create_connection((addresses[0], port), timeout=min(timeout, 10))
            if p.scheme == "https":
                try:
                    sock = ssl.create_default_context().wrap_socket(
                        sock, server_hostname=p.hostname
                    )
                except Exception:
                    sock.close()
                    raise
            sock.settimeout(min(timeout, 30))
            connection.sock = sock
            request_headers = {
                "Accept": (headers or {}).get("Accept", "*/*"),
                "Accept-Encoding": "identity",
                "User-Agent": "StudentSuccessful/2 public-job-collector",
            }
            if hop == 0:
                request_headers.update(
                    {
                        k: v
                        for k, v in (headers or {}).items()
                        if k in {"If-None-Match", "If-Modified-Since"}
                    }
                )
            connection.request(
                "GET", p.path + ("?" + p.query if p.query else "") or "/", headers=request_headers
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location or hop == redirects:
                    raise ValueError("Redirect limit or missing destination")
                destination = urljoin(url, location)
                if p.scheme == "https" and urlsplit(destination).scheme != "https":
                    raise ValueError("HTTPS downgrade")
                url = public_url(destination)
                continue
            if response.getheader("Content-Encoding", "identity").lower() not in {"identity", ""}:
                raise ValueError("Compressed responses are not accepted")
            length = response.getheader("Content-Length")
            if length and int(length) > MAX_BYTES:
                raise ValueError("Response too large")
            deadline = time.monotonic() + min(timeout, 30)
            chunks = []
            size = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise httpx.ReadTimeout("Public response deadline exceeded")
                sock.settimeout(remaining)
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Response too large")
            content = b"".join(chunks)
            return httpx.Response(
                response.status,
                headers=dict(response.getheaders()),
                content=content,
                request=httpx.Request("GET", url),
            )
        except TimeoutError as exc:
            raise httpx.ReadTimeout("Public fetch timed out") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise httpx.RequestError("Public fetch failed") from exc
        finally:
            connection.close()
    raise ValueError("Redirect limit")
