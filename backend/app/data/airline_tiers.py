"""Static airline tier and alliance classification.

Used for:
- 'same_tier' alternative suggestions (selection analysis)
- Alliance preference boost (search scoring)
"""

# Tiers: "legacy" (full-service), "low_cost", "ultra_low_cost"
AIRLINE_TIERS: dict[str, str] = {
    # North America — Legacy / Full-Service
    "AC": "legacy",   # Air Canada
    "AA": "legacy",   # American Airlines
    "UA": "legacy",   # United Airlines
    "DL": "legacy",   # Delta Air Lines
    "AS": "legacy",   # Alaska Airlines
    "HA": "legacy",   # Hawaiian Airlines
    # North America — Low Cost
    "WS": "low_cost",  # WestJet
    "B6": "low_cost",  # JetBlue
    "WN": "low_cost",  # Southwest
    "PD": "low_cost",  # Porter Airlines
    "TS": "low_cost",  # Air Transat
    # North America — Ultra Low Cost
    "NK": "ultra_low_cost",  # Spirit
    "F8": "ultra_low_cost",  # Flair Airlines
    "9M": "ultra_low_cost",  # Central Mountain Air (Canada regional ULCC)
    "G4": "ultra_low_cost",  # Allegiant Air
    "XP": "ultra_low_cost",  # Lynx Air (if active)
    # Europe — Legacy
    "BA": "legacy",   # British Airways
    "LH": "legacy",   # Lufthansa
    "AF": "legacy",   # Air France
    "KL": "legacy",   # KLM
    "IB": "legacy",   # Iberia
    "AZ": "legacy",   # ITA Airways
    "SK": "legacy",   # SAS
    "AY": "legacy",   # Finnair
    "LX": "legacy",   # Swiss
    "OS": "legacy",   # Austrian Airlines
    "LO": "legacy",   # LOT Polish
    "TP": "legacy",   # TAP Air Portugal
    # Europe — Low Cost
    "U2": "low_cost",  # easyJet
    "DY": "low_cost",  # Norwegian
    # Europe — Ultra Low Cost
    "FR": "ultra_low_cost",  # Ryanair
    "W6": "ultra_low_cost",  # Wizz Air
    # Middle East / Gulf — Legacy (premium)
    "EK": "legacy",   # Emirates
    "QR": "legacy",   # Qatar Airways
    "EY": "legacy",   # Etihad
    "TK": "legacy",   # Turkish Airlines
    # Asia-Pacific — Legacy
    "SQ": "legacy",   # Singapore Airlines
    "CX": "legacy",   # Cathay Pacific
    "NH": "legacy",   # ANA
    "JL": "legacy",   # Japan Airlines
    "QF": "legacy",   # Qantas
    "AI": "legacy",   # Air India
    "CI": "legacy",   # China Airlines
    "BR": "legacy",   # EVA Air
    "OZ": "legacy",   # Asiana Airlines
    "KE": "legacy",   # Korean Air
    # Asia — Low Cost
    "AK": "low_cost",  # AirAsia
    "3K": "low_cost",  # Jetstar Asia
    "FD": "low_cost",  # Thai AirAsia
}

AIRLINE_ALLIANCES: dict[str, str] = {
    # Star Alliance
    "AC": "star_alliance",
    "UA": "star_alliance",
    "LH": "star_alliance",
    "NH": "star_alliance",
    "SQ": "star_alliance",
    "TK": "star_alliance",
    "AS": "star_alliance",
    "SK": "star_alliance",
    "AY": "star_alliance",
    "LX": "star_alliance",
    "OS": "star_alliance",
    "LO": "star_alliance",
    "TP": "star_alliance",
    "OZ": "star_alliance",
    "AI": "star_alliance",
    "BR": "star_alliance",
    "CI": "star_alliance",
    # oneworld
    "AA": "oneworld",
    "BA": "oneworld",
    "QF": "oneworld",
    "CX": "oneworld",
    "JL": "oneworld",
    "QR": "oneworld",
    "IB": "oneworld",
    "AY": "oneworld",
    "AS": "oneworld",
    # SkyTeam
    "DL": "skyteam",
    "AF": "skyteam",
    "KL": "skyteam",
    "KE": "skyteam",
    "AZ": "skyteam",
}


def get_tier(airline_code: str) -> str:
    """Get airline tier by IATA code. Returns 'unknown' for unmapped airlines."""
    return AIRLINE_TIERS.get(airline_code, "unknown")


def get_alliance(airline_code: str) -> str | None:
    """Get airline alliance by IATA code. Returns None for non-alliance airlines."""
    return AIRLINE_ALLIANCES.get(airline_code)


TIER_LABELS: dict[str, str] = {
    "legacy": "Full-Service",
    "low_cost": "Low Cost",
    "ultra_low_cost": "Ultra Low Cost",
    "unknown": "Other",
}


def get_tier_label(airline_code: str) -> str:
    """Get human-readable tier label for an airline."""
    return TIER_LABELS.get(get_tier(airline_code), "Other")
