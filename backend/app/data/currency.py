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


def format_price(amount: float, currency: str = "USD") -> str:
    """Format a price with currency symbol for display."""
    symbol = CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{symbol}{round(amount):,}"
