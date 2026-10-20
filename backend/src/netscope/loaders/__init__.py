"""Loaders: the only layer that turns file content into model objects.

A loader reads one input file, rejects anything it cannot trust with an
``InputError`` that names the file and the location, and hands back valid
arguments for the model layer. Nothing here knows about routing, analysis or
the API, and nothing above the loaders knows about file formats.

Per D15 the model keeps its own invariants, so a loader's job is to fail
before it reaches a constructor. A bad file is an ``InputError``; a
``ValueError`` escaping from ``models`` would mean the loader itself is wrong.
"""

from __future__ import annotations

from netscope.loaders.sndlib_xml import ParsedBackbone, ParsedLink, load_backbone

__all__ = ["ParsedBackbone", "ParsedLink", "load_backbone"]
