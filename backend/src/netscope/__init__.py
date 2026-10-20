"""Resilience analysis for a European backbone network.

The package is layered so that each requirement has one obvious home:

``models``    the domain types. Undirected links and demands, node kinds.
``errors``    input errors that name the file and the row or line.
``loaders``   parsing file A and file B, and merging them into one network.
``routing``   equal-split minimum-hop routing with the transit restriction.
``analysis``  baseline utilization, single-failure impact, criticality.
``api``       the HTTP surface the front end consumes.

Nothing below ``api`` imports from ``api``, and nothing in ``loaders`` imports
from ``routing`` or ``analysis``.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
