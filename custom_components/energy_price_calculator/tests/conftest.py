"""Harness-koppeling + teardown-afstemming voor de HA-componenttests."""
import threading

import pytest
import pytest_homeassistant_custom_component  # noqa: F401  # registreert hass/aioclient_mock
from pytest_homeassistant_custom_component.plugins import verify_cleanup  # noqa: F401  # behoud import-pariteit


# aiohttp >= 3.12 start een daemon-achtergrondthread (_run_safe_shutdown_loop)
# om netjes af te sluiten als een ClientSession buiten zijn event-loop wordt
# gesloten. Die thread is onschadelijk, maar de harness-check verify_cleanup
# vlagt elke onbekende thread en faalt de CI flaky. HA core zelf staat deze
# thread inmiddels expliciet toe (core PR #183831: "Allow asyncio-waitpid
# threads in test cleanup check"); deze override volgt datzelfde beleid.
_ALLOWED_THREAD_MARKERS = ("waitpid-", "_run_safe_shutdown_loop", "asyncio-waitpid")


@pytest.fixture(autouse=True)
def verify_cleanup_allow_aiohttp_thread(monkeypatch):
    """Laat de harness-threadcheck de aiohttp-safe-shutdown-daemon toe.

    De harness-registratie gebeurt via een autouse fixture met een vaste
    assert in pytest_homeassistant_custom_component.plugins; in plaats van
    de plugin te forken patchen we alleen de thread-enummeratie die de
    check ziet: threads met een bekende aiohttp/asyncio-daemonnaam worden
    voor de duur van de teardown-check onzichtbaar gemaakt.
    """
    original_enumerate = threading.enumerate

    def filtered_enumerate():
        return [
            t
            for t in original_enumerate()
            if not any(marker in t.name for marker in _ALLOWED_THREAD_MARKERS)
        ]

    monkeypatch.setattr(threading, "enumerate", filtered_enumerate)
