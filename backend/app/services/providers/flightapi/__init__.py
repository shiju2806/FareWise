"""FlightAPI.io provider package.

Composes:
    - client.FlightAPIClient        — httpx client for the FlightAPI HTTP surface
    - credit_gate.CreditBudgetGate  — per-company monthly credit ceiling
    - concurrency_gate.ConcurrencyGate — global 5-concurrent Lite plan limit
    - provider.FlightAPIProvider    — FlightDataProvider implementation

See provider.py for the pipeline layering (cache → coalesce → concurrency →
credit → client).
"""
