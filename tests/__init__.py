"""Tests for the solcast_clearsky integration."""

from importlib import import_module
from importlib.util import find_spec
import sys

if find_spec("tests.common") is None:
    for _name in ("common", "typing", "ignore_uncaught_exceptions", "components.diagnostics", "components.recorder.common"):
        sys.modules[f"tests.{_name}"] = import_module(f"pytest_homeassistant.{_name}")
