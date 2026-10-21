"""Runtime configuration, read from the environment (P13).

Names and defaults mirror the repository root's ``.env.example`` exactly,
which is the committed template CLAUDE.md names as the one place
configuration may come from. This module adds no variable beyond that file:
anything not listed there has no business being read from the environment
here.

``NETSCOPE_BACKBONE_CAPACITY`` is read here and passed through to
``loaders.merge.build_network`` by ``api.state.build_state``, which is the
only place the merged ``Network`` is built for the running application. R3
fixes every backbone link at 550 units, which is this setting's default and
its value whenever the variable is unset, so the requirement is satisfied
out of the box. The override exists on top of that default as a deliberate
extension: it is the one lever a follow-up capacity-planning session needs,
and removing it would mean reintroducing a documented setting that silently
does nothing, which is worse than not having it (see D27 in
``docs/DECISIONS.md`` for the full reasoning, including what still needs
saying out loud if this setting is ever used to demonstrate a change live).
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
