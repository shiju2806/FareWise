"""Currency utilities — airport-based currency resolution and conversion."""

# Major airports → currency mapping
AIRPORT_CURRENCIES: dict[str, str] = {
    # Canada
    "YYZ": "CAD", "YVR": "CAD", "YUL": "CAD", "YOW": "CAD", "YHZ": "CAD",
    "YYC": "CAD", "YEG": "CAD", "YWG": "CAD", "YHM": "CAD", "YKF": "CAD",
    # United States
    "JFK": "USD", "LAX": "USD", "ORD": "USD", "ATL": "USD", "DFW": "USD",
    "SFO": "USD", "SEA": "USD", "MIA": "USD", "BOS": "USD", "DEN": "USD",
    "IAH": "USD", "EWR": "USD", "LGA": "USD", "MCO": "USD", "PHL": "USD",
    "IAD": "USD", "DCA": "USD", "CLT": "USD", "MSP": "USD", "DTW": "USD",
    "BWI": "USD", "SAN": "USD", "TPA": "USD", "PDX": "USD", "SLC": "USD",
    "BNA": "USD", "AUS": "USD", "RDU": "USD", "SMF": "USD", "HNL": "USD",
    # United Kingdom
    "LHR": "GBP", "LGW": "GBP", "STN": "GBP", "MAN": "GBP", "EDI": "GBP",
    "BHX": "GBP", "GLA": "GBP", "LTN": "GBP", "BFS": "GBP",
    # Eurozone
    "CDG": "EUR", "ORY": "EUR", "FRA": "EUR", "MUC": "EUR", "AMS": "EUR",
    "MAD": "EUR", "BCN": "EUR", "FCO": "EUR", "MXP": "EUR", "DUB": "EUR",
    "LIS": "EUR", "VIE": "EUR", "BRU": "EUR", "HEL": "EUR", "CPH": "EUR",
    "OSL": "EUR", "ARN": "EUR", "ZRH": "EUR",
    # Asia-Pacific
    "NRT": "JPY", "HND": "JPY", "KIX": "JPY",
    "SIN": "SGD",
    "HKG": "HKD",
    "SYD": "AUD", "MEL": "AUD",
    "DEL": "INR", "BOM": "INR",
    "ICN": "KRW",
    "TPE": "TWD",
    # Middle East
    "DXB": "AED", "AUH": "AED",
    "DOH": "QAR",
    "IST": "TRY",
}

# Static exchange rates to USD (can be updated periodically)
EXCHANGE_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "CAD": 0.74,
    "GBP": 1.27,
    "EUR": 1.08,
    "JPY": 0.0067,
    "AUD": 0.65,
    "SGD": 0.75,
    "HKD": 0.13,
    "INR": 0.012,
    "AED": 0.27,
    "QAR": 0.27,
    "TRY": 0.031,
    "KRW": 0.00074,
    "TWD": 0.031,
}

# Airport → country code (ISO 3166-1 alpha-2)
AIRPORT_COUNTRIES: dict[str, str] = {
    # Canada
    "YYZ": "CA", "YVR": "CA", "YUL": "CA", "YOW": "CA", "YHZ": "CA",
    "YYC": "CA", "YEG": "CA", "YWG": "CA", "YHM": "CA", "YKF": "CA",
    # United States
    "JFK": "US", "LAX": "US", "ORD": "US", "ATL": "US", "DFW": "US",
    "SFO": "US", "SEA": "US", "MIA": "US", "BOS": "US", "DEN": "US",
    "IAH": "US", "EWR": "US", "LGA": "US", "MCO": "US", "PHL": "US",
    "IAD": "US", "DCA": "US", "CLT": "US", "MSP": "US", "DTW": "US",
    "BWI": "US", "SAN": "US", "TPA": "US", "PDX": "US", "SLC": "US",
    "BNA": "US", "AUS": "US", "RDU": "US", "SMF": "US", "HNL": "US",
    # United Kingdom
    "LHR": "GB", "LGW": "GB", "STN": "GB", "MAN": "GB", "EDI": "GB",
    "BHX": "GB", "GLA": "GB", "LTN": "GB", "BFS": "GB",
    # France
    "CDG": "FR", "ORY": "FR",
    # Germany
    "FRA": "DE", "MUC": "DE",
    # Netherlands
    "AMS": "NL",
    # Spain
    "MAD": "ES", "BCN": "ES",
    # Italy
    "FCO": "IT", "MXP": "IT",
    # Ireland
    "DUB": "IE",
    # Portugal
    "LIS": "PT",
    # Austria
    "VIE": "AT",
    # Belgium
    "BRU": "BE",
    # Finland
    "HEL": "FI",
    # Denmark
    "CPH": "DK",
    # Norway
    "OSL": "NO",
    # Sweden
    "ARN": "SE",
    # Switzerland
    "ZRH": "CH",
    # Japan
    "NRT": "JP", "HND": "JP", "KIX": "JP",
    # Singapore
    "SIN": "SG",
    # Hong Kong
    "HKG": "HK",
    # Australia
    "SYD": "AU", "MEL": "AU",
    # India
    "DEL": "IN", "BOM": "IN",
    # South Korea
    "ICN": "KR",
    # Taiwan
    "TPE": "TW",
    # UAE
    "DXB": "AE", "AUH": "AE",
    # Qatar
    "DOH": "QA",
    # Turkey
    "IST": "TR",
    # Iceland
    "KEF": "IS",
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$", "CAD": "CA$", "GBP": "\u00a3", "EUR": "\u20ac",
    "JPY": "\u00a5", "AUD": "A$", "SGD": "S$", "HKD": "HK$",
    "INR": "\u20b9", "AED": "AED", "QAR": "QAR", "TRY": "TRY",
    "KRW": "\u20a9", "TWD": "NT$",
}


def get_currency_for_airport(iata_code: str) -> str:
    """Get local currency for an airport. Defaults to USD for unknown airports."""
    return AIRPORT_CURRENCIES.get(iata_code, "USD")


def convert_to_usd(amount: float, from_currency: str) -> float:
    """Convert an amount to USD using static exchange rates."""
    rate = EXCHANGE_RATES_TO_USD.get(from_currency, 1.0)
    return round(amount * rate, 2)


def convert_from_usd(amount: float, to_currency: str) -> float:
    """Convert a USD amount to another currency using static exchange rates."""
    rate = EXCHANGE_RATES_TO_USD.get(to_currency, 1.0)
    if rate == 0:
        return amount
    return round(amount / rate, 2)


def is_domestic_route(origin_iata: str, dest_iata: str) -> bool:
    """Check if a route is domestic (same country). Unknown airports are treated as international."""
    origin_country = AIRPORT_COUNTRIES.get(origin_iata)
    dest_country = AIRPORT_COUNTRIES.get(dest_iata)
    if not origin_country or not dest_country:
        return False
    return origin_country == dest_country


def format_price(amount: float, currency: str = "USD") -> str:
    """Format a price with currency symbol for display."""
    symbol = CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{symbol}{round(amount):,}"
