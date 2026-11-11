"""One name per carrier (epic #2247). Each source writes the carrier of a leg in its own way ("DB Fernverkehr AG",
"Nightjet"). `carrier_names` gives the name of the table, so that the score and the filters can compare the carriers
of two sources. A name that is not in the table stays as it is."""

# One name per carrier -> the names that the sources write for it. The name itself is also a source name.
CARRIERS: dict[str, tuple[str, ...]] = {
    "Deutsche Bahn": ("DB Fernverkehr AG", "DB Regio AG NRW", "Deutsche Bahn", "DB"),
    "Flix": ("FlixBus B.V.", "FlixBus DACH GmbH", "FlixBus Polska sp. z.o.o.", "FlixTrain GmbH", "FlixBus",
             "FlixTrain"),
    "NS": ("Nederlandse Spoorwegen", "NS"),
    "SBB": ("Schweizerische Bundesbahnen", "SBB"),
    "ÖBB": ("Österreichische Bundesbahnen", "ÖBB", "Nightjet", "Railjet Xpress", "Railjet"),
    "SNCF": ("SNCF", "TGV INOUI", "OUIGO", "Train TER"),
    "LNER": ("London North Eastern Railway", "LNER"),
    "KLM": ("KL", "KLM"),
    "Air France": ("AF", "Air France"),
    "TAP Air Portugal": ("TP", "TAP Portugal", "TAP Air Portugal"),
    "Transavia": ("HV", "Transavia"),
    "SWISS": ("LX", "SWISS", "Swiss International Air Lines"),
    "Air Europa": ("UX", "Air Europa"),
    "Eurostar": ("Eurostar", "Thalys"),
}

SEPARATOR = ", "  # the bahn.de payload joins the carriers of a leg with it


def _by_source_name() -> dict[str, str]:
    """Each source name (and each name itself) without case -> its name of the table."""
    table: dict[str, str] = {}
    for name, source_names in CARRIERS.items():
        for source_name in (name, *source_names):
            table[source_name.casefold()] = name
    return table


_BY_SOURCE_NAME = _by_source_name()


def carrier_names(raw: str | None) -> tuple[str, ...]:
    """The names of the carriers of a raw carrier text: split at ", ", each part mapped through the table (without
    case; a part that is not in the table stays as it is). No duplicates, in order. None or a blank text gives ()."""
    if raw is None or not raw.strip():
        return ()
    names: list[str] = []
    for part in raw.split(SEPARATOR):
        part = part.strip()
        if not part:
            continue
        name = _BY_SOURCE_NAME.get(part.casefold(), part)
        if name not in names:
            names.append(name)
    return tuple(names)
