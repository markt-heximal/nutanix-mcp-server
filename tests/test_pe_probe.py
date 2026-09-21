"""Tests for the PE reachability probe behind /api/config.

The probe decides which clusters the UI is allowed to offer, so the cases that
matter are: a live Prism counts, a dead address or a non-Prism answer does not,
the configured order survives, results are cached, and — load-bearing — no
credential is ever sent, because failed logins lock Prism's admin account.
"""

import httpx

from nutanix_mcp.pe_probe import PROBE_PATH, PEHostProbe

FL = "10.0.1.243"
CA = "192.168.86.6"
DEAD = "10.0.1.249"
WEB = "10.0.1.10"  # answers HTTP, but is not Prism


class FakePrism:
    """A MockTransport handler standing in for the estate."""

    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.url.host
        if host == DEAD:
            raise httpx.ConnectError("unreachable", request=request)
        if host == WEB:
            return httpx.Response(404, text="not found")
        return httpx.Response(401, json={"message": "Authentication required"})

    def hits(self, host: str) -> int:
        return sum(1 for r in self.requests if r.url.host == host)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _probe(fake: FakePrism, clock: Clock | None = None) -> PEHostProbe:
    return PEHostProbe(
        port=9440,
        verify_ssl=False,
        ttl=30.0,
        clock=clock or Clock(),
        transport=httpx.MockTransport(fake),
    )


async def test_only_answering_prism_hosts_are_kept_in_order():
    fake = FakePrism()
    assert await _probe(fake).answering([CA, DEAD, WEB, FL]) == [CA, FL]


async def test_probe_targets_the_prism_v2_api_on_the_configured_port():
    fake = FakePrism()
    await _probe(fake).answering([FL])
    (req,) = fake.requests
    assert req.url.port == 9440
    assert req.url.path == PROBE_PATH


async def test_probe_never_sends_credentials():
    fake = FakePrism()
    await _probe(fake).answering([FL, CA])
    assert fake.requests
    for req in fake.requests:
        assert "authorization" not in {k.lower() for k in req.headers}


async def test_results_are_cached_within_ttl_and_refreshed_after():
    fake, clock = FakePrism(), Clock()
    probe = _probe(fake, clock)

    await probe.answering([FL, DEAD])
    clock.now += 29
    await probe.answering([FL, DEAD])
    assert fake.hits(FL) == 1 and fake.hits(DEAD) == 1

    clock.now += 2
    await probe.answering([FL, DEAD])
    assert fake.hits(FL) == 2 and fake.hits(DEAD) == 2


async def test_a_new_host_is_probed_without_reprobing_cached_ones():
    fake = FakePrism()
    probe = _probe(fake)
    await probe.answering([FL])
    assert await probe.answering([FL, CA]) == [FL, CA]
    assert fake.hits(FL) == 1 and fake.hits(CA) == 1


async def test_duplicate_hosts_are_probed_once():
    fake = FakePrism()
    assert await _probe(fake).answering([FL, FL]) == [FL, FL]
    assert fake.hits(FL) == 1


async def test_no_hosts_means_no_requests():
    fake = FakePrism()
    assert await _probe(fake).answering([]) == []
    assert fake.requests == []
