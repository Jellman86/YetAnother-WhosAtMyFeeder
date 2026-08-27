# Species reference attribution

`species_reference.db` is generated from the **IOC World Bird List** multilingual file.

> IOC World Bird List, Frank Gill, David Donsker & Pamela Rasmussen (Eds).
> <https://www.worldbirdnames.org/>

Licensed under a [Creative Commons Attribution 3.0 Unported Licence](https://creativecommons.org/licenses/by/3.0/).

The database holds the scientific name, the English name, and the name in each language this
project presents, for every species in that list. No other content is redistributed, and the file
is generated rather than edited by hand.

Regenerate with:

```bash
python backend/scripts/build_species_reference.py --ioc /path/to/Multiling_IOC_<version>.xlsx
```

The build is reproducible: the same source produces a byte-identical file, and the digest recorded
in `species_reference.db.sha256` is checked at runtime.
