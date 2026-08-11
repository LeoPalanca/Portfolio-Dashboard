from __future__ import annotations

from pathlib import Path
import unittest

from src.portfolio_dashboard.domain import Trade
from src.portfolio_dashboard.ingest import BrokerAdapter, FunctionBrokerAdapter


class BrokerAdapterTest(unittest.TestCase):
    def test_function_adapter_implements_protocol_shape(self) -> None:
        export = Path("example.csv")
        parsed: list[Trade] = []
        adapter = FunctionBrokerAdapter(
            name="Example Broker",
            discover_export=lambda: export,
            parse_export=lambda path: parsed if path == export else self.fail("unexpected path"),
        )

        typed_adapter: BrokerAdapter = adapter
        self.assertEqual(typed_adapter.name, "Example Broker")
        self.assertEqual(typed_adapter.discover(), export)
        self.assertIs(typed_adapter.parse(export), parsed)


if __name__ == "__main__":
    unittest.main()
