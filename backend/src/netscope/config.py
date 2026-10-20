"""Runtime configuration, read from the environment (P13).

Names and defaults mirror the repository root's ``.env.example`` exactly,
which is the committed template CLAUDE.md names as the one place
configuration may come from. This module adds no variable beyond that file:
anything not listed there has no business being read from the environment
here.

``NETSCOPE_BACKBONE_CAPACITY`` is read and kept on ``Settings`` for
completeness with ``.env.example``, but nothing in this task wires it
anywhere. ``loaders/merge.py`` hardcodes ``BACKBONE_CAPACITY = 550.0`` as a
module constant with no parameter to override it, and P13's brief does not
permit editing that file. See the P13 report for this gap: today the
variable can only ever agree with the hardcoded default, since there is
nowhere for a different value to take effect, which is worth flagging rather
than silently accepting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Mirrors .env.example. Paths are relative to the repository root, the way
#: the committed template documents them.
DEFAULT_SNDLIB_PATH = "data/nobel-eu.xml"
DEFAULT_SITES_PATH = "data/sites.csv"
DEFAULT_BACKBONE_CAPACITY = 550.0
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

__all__ = ["Settings"]


@dataclass(frozen=True, slots=True)
class Settings:
    """The five variables ``.env.example`` documents, with its defaults.

    Construct with :meth:`from_env` in application code. The plain
    constructor is what a test uses to point at a fixture file instead of an
    environment variable, which is the reason this is a dataclass and not a
    pydantic settings model: a test should not need to mutate ``os.environ``
    just to exercise a different input path.
    """

    sndlib_path: str = DEFAULT_SNDLIB_PATH
    sites_path: str = DEFAULT_SITES_PATH
    backbone_capacity: float = DEFAULT_BACKBONE_CAPACITY
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    @classmethod
    def from_env(cls) -> Settings:
        """Read the environment, falling back to the documented defaults."""
        return cls(
            sndlib_path=os.environ.get("NETSCOPE_SNDLIB_PATH", DEFAULT_SNDLIB_PATH),
            sites_path=os.environ.get("NETSCOPE_SITES_PATH", DEFAULT_SITES_PATH),
            backbone_capacity=float(
                os.environ.get("NETSCOPE_BACKBONE_CAPACITY", DEFAULT_BACKBONE_CAPACITY)
            ),
            host=os.environ.get("NETSCOPE_HOST", DEFAULT_HOST),
            port=int(os.environ.get("NETSCOPE_PORT", DEFAULT_PORT)),
        )
