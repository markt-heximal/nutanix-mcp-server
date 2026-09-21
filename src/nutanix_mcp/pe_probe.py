"""Reachability probe for Prism Element hosts.

Used to keep the UI from advertising a cluster that is configured but not
answering. The probe is deliberately UNAUTHENTICATED: Prism locks `admin` for
about fifteen minutes after a few failed logins, so a health check that sends
credentials on every page load could turn one wrong password into a lockout.
An unauthenticated GET against the v2 API still proves Prism is there — it
answers 401 with a JSON body (verified against AOS 6.8.1) — while a dead or
wrong address fails to connect or times out.

What this does NOT prove is that the configured credential works; a host that
answers can still reject the password at call time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

# Statuses that mean "Prism Element answered". 401/403 are the normal
# unauthenticated replies; 200 covers a gateway that does not require auth.
PRISM_ANSWER_STATUSES = frozenset({200, 401, 403})

PROBE_PATH = "/api/nutanix/v2.0/cluster"


async def probe_pe_host(
    client: httpx.AsyncClient, pe_host: str, port: int
) -> bool:
    """True if Prism Element answers at pe_host:port."""
    try:
        response = await client.get(f"https://{pe_host}:{port}{PROBE_PATH}")
    except httpx.HTTPError as e:
        logger.warning("PE host %s did not answer: %s", pe_host, type(e).__name__)
        return False
    if response.status_code not in PRISM_ANSWER_STATUSES:
        logger.warning("PE host %s answered HTTP %s, not Prism", pe_host, response.status_code)
        return False
    return True


class PEHostProbe:
    """Probes PE hosts in parallel and caches the result for `ttl` seconds.

    The cache keeps /api/config fast and stops every page load from fanning
    out to every cluster. Each host is cached separately, so a changed host
    list only probes the hosts it has not seen recently.
    """

    def __init__(
        self,
        port: int,
        verify_ssl: bool,
        timeout: float = 3.0,
        ttl: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.port = port
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.ttl = ttl
        self._clock = clock
        self._transport = transport
        self._cache: dict[str, tuple[float, bool]] = {}
        self._lock = asyncio.Lock()

    async def answering(self, hosts: list[str]) -> list[str]:
        """The subset of `hosts` that answer, in their original order."""
        async with self._lock:
            now = self._clock()
            stale = [
                h for h in dict.fromkeys(hosts)
                if h not in self._cache or now - self._cache[h][0] >= self.ttl
            ]
            if stale:
                async with httpx.AsyncClient(
                    verify=self.verify_ssl,
                    timeout=httpx.Timeout(self.timeout),
                    transport=self._transport,
                ) as client:
                    results = await asyncio.gather(
                        *(probe_pe_host(client, h, self.port) for h in stale)
                    )
                for h, ok in zip(stale, results):
                    self._cache[h] = (now, ok)
            return [h for h in hosts if self._cache[h][1]]
