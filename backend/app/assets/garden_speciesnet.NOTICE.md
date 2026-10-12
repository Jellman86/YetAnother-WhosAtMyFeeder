# SpeciesNet attribution

SpeciesNet 4.0.3a and 4.0.3b are developed by Google and contributors.
Upstream: https://github.com/google/cameratrapai
Model releases: https://www.kaggle.com/models/google/speciesnet

The ordered outputs, taxonomy and country rules in
`garden_speciesnet_4.0.3.json.gz` come from the official model packages, taxonomy
release 20260609. The preparation code was checked against upstream commit
`20c5c33cfd23e5ae2ec93f2cc04177e7ef2050fc`.

The classifiers were converted to ONNX without changing their output order.
The compressed catalogue input omits the separate detector checksum; the
classifier outputs, taxonomy and geofence rules are preserved. Runtime canonical
bindings are resolved against the installation’s species catalogue, leaving
ambiguous identities unresolved. The application uses its own conservative review
policy rather than the complete upstream SpeciesNet ensemble.

Licence: Apache License 2.0, reproduced in `garden_speciesnet.LICENSE.txt`.
The uncompressed package SHA-256 and source citation are recorded in
`species_sources.json`. The model checksums are also bound inside the package.
No upstream example photographs or detector weights are redistributed here.
