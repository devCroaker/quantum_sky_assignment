# Input data provenance

Two inputs. One is public research data, one is invented for this exercise. They are kept
apart deliberately, because only one of them can be cited.

## `nobel-eu.xml`, the backbone

Public research data from SNDlib, the Survivable Network Design Library.

- Source: <https://sndlib.put.poznan.pl/download/sndlib-networks-xml/nobel-eu.xml>
- Retrieved: 2026-10-20
- SHA-256: `0a169d757e38bc002554173b97c6cb5f0e89292fb1bdcb340cb5485f084be121`
- Contents: 28 European cities with geographical coordinates, 41 links, 378 traffic demands.

Committed verbatim, byte for byte as served. The file is not reformatted or trimmed, so the
checksum above can be verified against a fresh download.

The same data is also published in a native text format at
<https://sndlib.put.poznan.pl/download/sndlib-networks-native/nobel-eu.txt>. We parse the
XML, because it is unambiguous to parse and because its line numbers give us something
precise to name in a validation error.

### Citation

> S. Orlowski, M. Pióro, A. Tomaszewski, R. Wessäly. "SNDlib 1.0, Survivable Network Design
> Library." Networks, 55(3):276-286, 2010.

Library home page: <https://sndlib.put.poznan.pl>

### What we ignore

Each link in the file carries a list of `addModule` capacity and cost options. R3 says to
ignore them and give every backbone link a capacity of 550 units, so the loader does not
read them at all. The file also carries `demandRoutings` and admissible path data in some
SNDlib variants, which we likewise do not use, because R5 specifies the routing rule.

## `sites.csv`, the sites

**Invented for this exercise.** Not real network data, not public data, and not citable. It
is reproduced exactly as given in the assignment brief.

Nine rows add nine nodes: two data centers, six operations sites and one aggregation hub.
Each value in `attaches_to` creates one access link at the row's `access_capacity`. A value
is either a city id from the backbone file or another row's `site_id`, which is why
`OPS-EAST-1` can attach to `HUB-EAST`. Forward references between rows are therefore legal
and resolution happens after all rows are read.

- SHA-256: `f75a2d09eb7704ef1758d763c35f0721b4ab5b319cd9564d5956039ace856a5b`
- 9 rows, 14 attachment values, so 14 access links.

## Why the files are committed

The application makes no network calls at runtime. Fetching the topology on startup would
make the tool fail when a research server is down, make results irreproducible if the file
ever changes, and make the test suite depend on the internet. The checksums above are the
mechanism for confirming the committed copy matches upstream.
