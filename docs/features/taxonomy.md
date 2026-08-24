# Taxonomy & Naming

YA-WAMF uses a professional taxonomy engine to ensure every bird sighting is recorded with both its common and scientific identity.

## iNaturalist Integration
The system is connected to the [iNaturalist API](https://www.inaturalist.org/). Every time a new species is detected, YA-WAMF:
1. Performs a bidirectional lookup (Common ↔ Scientific).
2. Retrieves the standard Taxonomic ID.
3. Caches the result in a local SQLite table (`taxonomy_cache`) to avoid redundant API calls.

## Display Modes
You can customize how birds are named in the UI via **Settings > Detection**:

- **Standard:** Common name is primary, Scientific name is the subtitle.
- **Hobbyist:** Scientific name is primary, Common name is the subtitle.
- **Strictly Scientific:** Only the Scientific name is shown.

![Species List](../images/frontend_species.png)

## Taxonomy Repair
If your database has old detections with inconsistent naming, you can run the **Taxonomy Repair** tool in the settings. This tool will scan your entire history and normalize all labels against the iNaturalist database.


## Where names come from

Names are resolved in order, and the first source that answers wins:

1. **Your own name for a species**, if you have set one. Nothing overrides it.
2. **iNaturalist**, which also supplies the taxon id used for enrichment.
3. **The bundled species reference**, when the network cannot answer. It carries 11,276 species
   from the IOC World Bird List with names in every language this project presents, so an offline
   or air-gapped install still names birds, in your language, with no API key.
4. **eBird**, for species the bundled list does not carry, when you have configured a key.

The bundled reference is generated from the IOC World Bird List and redistributed under
[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/); see
`backend/app/assets/species_reference.NOTICE.md` for the attribution.

## The species catalogue

Newer installs also carry a **species catalogue** at `/data/species_catalog.db`: a versioned
database of species identities, the names each one has in every language this project presents,
recorded synonyms, and the exact meaning of every output a supported model can produce.

It exists because names are not identities. A taxon that is split, lumped, or renamed changes its
scientific name, so anything keying on the text quietly divides one bird into two. The catalogue
gives each species a stable identity that its names hang off, and detections record that identity
alongside the model artifact and output index that produced them.

### What diagnostics tell you

The **Naming Sources** card under Jobs → Diagnostics reports:

- **Catalogue species** — how many identities the active release holds.
- **Model output classes with no catalogue identity** — outputs that keep their original label text
  because no source could say what they are. These are counted rather than guessed at, and a
  detection from one of them is still recorded, just without a canonical identity.
- **Catalogue sources** — the pinned source of every piece of data in the active release, with its
  version, licence, and citation.

### Sources and attribution

The catalogue redistributes work from other projects, and the citations shown in diagnostics are
the attribution their licences require. At the time of writing the active release is built from the
[IOC World Bird List](https://www.worldbirdnames.org/) under
[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) and the
[Catalogue of Life](https://www.checklistbank.org/dataset/315777) under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Diagnostics show whatever the release
you are actually running was built from, which is the version that matters.

### Updates, rollback, and backups

A catalogue release is imported whole or not at all. An interrupted import leaves the previous
release active, and identities are never deleted by an update.

A release can name an output that an earlier one could not, because an output the catalogue could
not name carries no claim about what it is. A release that would *change* an identity already
recorded, rewrite a model's label, or withdraw an identity is refused outright: that is a
correction, and a correction needs a deliberate decision rather than arriving in an update.

**The catalogue is a separate file from your detection history.** Rolling a release back changes
names, never your recorded sightings. Both live under `/data`, so a backup of that directory covers
the catalogue, the detections database, and your configuration together.
