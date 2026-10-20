"""Guards the one structural promise the package makes about itself.

This file exists from the first commit so that the quality gates have
something real to run, and so that the layering rule in the package
docstring is enforced rather than merely documented.
"""

from __future__ import annotations

import netscope


def test_version_is_exposed() -> None:
    assert netscope.__version__ == "0.1.0"
