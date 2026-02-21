"""Airline alliance memberships and service tier classifications.

Static reference data used by the trade-off resolver for graduated
preference scoring. Extend these dicts as new airlines appear in
search results.
"""

# ---------- Alliance memberships ----------

AIRLINE_ALLIANCES: dict[str, str] = {
    # Star Alliance
    "AC": "star_alliance",  # Air Canada
    "UA": "star_alliance",  # United Airlines
    "LH": "star_alliance",  # Lufthansa
    "NH": "star_alliance",  # ANA
    "SQ": "star_alliance",  # Singapore Airlines
    "TK": "star_alliance",  # Turkish Airlines
    "SK": "star_alliance",  # SAS
    "OS": "star_alliance",  # Austrian
    "LO": "star_alliance",  # LOT Polish
    "TP": "star_alliance",  # TAP Air Portugal
    "ET": "star_alliance",  # Ethiopian Airlines
    "SA": "star_alliance",  # South African Airways
    "OZ": "star_alliance",  # Asiana Airlines
    "BR": "star_alliance",  # EVA Air
    "AI": "star_alliance",  # Air India
    "MS": "star_alliance",  # EgyptAir
    "A3": "star_alliance",  # Aegean Airlines
    "SN": "star_alliance",  # Brussels Airlines
    "OU": "star_alliance",  # Croatia Airlines
    # Oneworld
    "BA": "oneworld",  # British Airways
    "AA": "oneworld",  # American Airlines
    "QF": "oneworld",  # Qantas
    "CX": "oneworld",  # Cathay Pacific
    "JL": "oneworld",  # Japan Airlines
    "IB": "oneworld",  # Iberia
    "AY": "oneworld",  # Finnair
    "QR": "oneworld",  # Qatar Airways
    "MH": "oneworld",  # Malaysia Airlines
    "RJ": "oneworld",  # Royal Jordanian
    "S7": "oneworld",  # S7 Airlines
    "UL": "oneworld",  # SriLankan Airlines
    # SkyTeam
    "AF": "skyteam",  # Air France
    "KL": "skyteam",  # KLM
    "DL": "skyteam",  # Delta Air Lines
    "KE": "skyteam",  # Korean Air
    "AZ": "skyteam",  # ITA Airways (was Alitalia)
    "AM": "skyteam",  # Aeromexico
    "SU": "skyteam",  # Aeroflot
    "CI": "skyteam",  # China Airlines
    "MU": "skyteam",  # China Eastern
    "GA": "skyteam",  # Garuda Indonesia
    "VN": "skyteam",  # Vietnam Airlines
    "SV": "skyteam",  # Saudia
}


# ---------- Service tiers ----------

AIRLINE_TIERS: dict[str, str] = {
    # full_service: flag carriers, major alliance members, premium service
    "AC": "full_service",  # Air Canada
    "BA": "full_service",  # British Airways
    "UA": "full_service",  # United Airlines
    "AA": "full_service",  # American Airlines
    "DL": "full_service",  # Delta Air Lines
    "LH": "full_service",  # Lufthansa
    "AF": "full_service",  # Air France
    "KL": "full_service",  # KLM
    "NH": "full_service",  # ANA
    "SQ": "full_service",  # Singapore Airlines
    "TK": "full_service",  # Turkish Airlines
    "QF": "full_service",  # Qantas
    "CX": "full_service",  # Cathay Pacific
    "JL": "full_service",  # Japan Airlines
    "IB": "full_service",  # Iberia
    "QR": "full_service",  # Qatar Airways
    "EK": "full_service",  # Emirates (non-alliance)
    "KE": "full_service",  # Korean Air
    "AY": "full_service",  # Finnair
    "SK": "full_service",  # SAS
    "OS": "full_service",  # Austrian
    "ET": "full_service",  # Ethiopian Airlines
    "AI": "full_service",  # Air India
    # mid_tier: regional carriers, leisure carriers with reasonable service
    "WS": "mid_tier",   # WestJet
    "FI": "mid_tier",   # Icelandair
    "EI": "mid_tier",   # Aer Lingus
    "TP": "mid_tier",   # TAP Air Portugal
    "LO": "mid_tier",   # LOT Polish
    "A3": "mid_tier",   # Aegean Airlines
    "SN": "mid_tier",   # Brussels Airlines
    "DY": "mid_tier",   # Norwegian
    "AZ": "mid_tier",   # ITA Airways
    "OU": "mid_tier",   # Croatia Airlines
    "AT": "mid_tier",   # Royal Air Maroc
    "TS": "mid_tier",   # Air Transat
    # low_cost: ULCCs and budget carriers
    "WJ": "low_cost",   # Swoop
    "F8": "low_cost",   # Flair Airlines
    "NK": "low_cost",   # Spirit Airlines
    "G4": "low_cost",   # Allegiant Air
    "WO": "low_cost",   # Swoop (alt code)
    "FR": "low_cost",   # Ryanair
    "U2": "low_cost",   # easyJet
    "W6": "low_cost",   # Wizz Air
}

DEFAULT_TIER = "mid_tier"


# ---------- Lookup functions ----------


def get_alliance(airline_code: str) -> str | None:
    """Get the alliance name for an airline, or None if unaffiliated."""
    return AIRLINE_ALLIANCES.get(airline_code)


def get_tier(airline_code: str) -> str:
    """Get the service tier for an airline. Defaults to mid_tier if unknown."""
    return AIRLINE_TIERS.get(airline_code, DEFAULT_TIER)


def same_alliance(code_a: str, code_b: str) -> bool:
    """Check if two airlines belong to the same alliance."""
    a = get_alliance(code_a)
    b = get_alliance(code_b)
    return a is not None and a == b
