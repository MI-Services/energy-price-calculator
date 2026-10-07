"""Root conftest for the HA harness tests.

pytest-homeassistant-custom-component registers ITSELF as a pytest plugin
via its package entry point (it shows up as the 'homeassistant' plugin), so
it must NOT be listed in pytest_plugins here: that double-registers the
module and raises
    ValueError: Plugin already registered under a different name
The fixtures (hass, aioclient_mock, freezer, MockConfigEntry,
enable_custom_integrations) are available without any conftest wiring.
"""
import os
import sys

import pytest

# Make the custom_components package importable regardless of invocation dir.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
