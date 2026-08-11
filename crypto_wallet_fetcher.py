from __future__ import annotations

import argparse
import csv
import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt

from src.portfolio_dashboard.config import get_settings


PRIMARY_PORTFOLIO_ID = get_settings().primary_portfolio_id


APP_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = Path.home() / "Downloads"
CONFIG_CSV = APP_DIR / "data" / "crypto_wallets.csv"
POSITIONS_CSV = APP_DIR / "data" / "crypto_wallet_positions.csv"
TRANSACTIONS_CSV = APP_DIR / "data" / "crypto_wallet_transactions.csv"
CDP_HOST = "api.cdp.coinbase.com"
CDP_BASE_URL = f"https://{CDP_HOST}"
COINBASE_HOST = "api.coinbase.com"
TONAPI_BASE_URL = "https://tonapi.io"
COINBASE_RETAIL_API = "https://api.coinbase.com"
BSC_RPC_URL = "https://bsc-dataseed1.binance.org/"

POSITION_FIELDS = [
    "person",
    "broker",
    "wallet_label",
    "wallet_address",
    "chain",
    "network",
    "asset",
    "symbol",
    "quantity",
    "market_value_eur",
    "cost_basis_eur",
    "asset_class",
    "sector",
    "geo",
    "source",
    "fetched_at",
    "status",
    "message",
]
TRANSACTION_FIELDS = [
    "person",
    "wallet_label",
    "source",
    "account_id",
    "account_name",
    "asset",
    "transaction_id",
    "created_at",
    "type",
    "status",
    "quantity",
    "native_amount",
    "native_currency",
    "cost_basis_after_eur",
    "quantity_after",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_decimal(value: Any) -> Decimal:
    raw = clean(value)
    if not raw:
        return Decimal("0")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal("0")


def decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def latest_binance_history() -> Path | None:
    files = sorted(DOWNLOADS_DIR.glob("Binance-Transaction-History-*.csv"))
    return files[-1] if files else None


def binance_cost_basis(path: Path | None) -> dict[str, Decimal]:
    if not path or not path.exists():
        return {}
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows.append({key: clean(value) for key, value in row.items()})

    costs: dict[str, Decimal] = {}
    used_targets: set[int] = set()
    for index, row in enumerate(rows):
        if row.get("Operation") != "Binance Convert" or row.get("Coin") != "EUR":
            continue
        eur_spend = abs(parse_decimal(row.get("Change")))
        if eur_spend <= 0:
            continue
        target_index = None
        for candidate_index in (index - 1, index + 1, index - 2, index + 2):
            if candidate_index < 0 or candidate_index >= len(rows) or candidate_index in used_targets:
                continue
            candidate = rows[candidate_index]
            coin = clean(candidate.get("Coin")).upper()
            if candidate.get("Operation") == "Binance Convert" and coin and coin != "EUR" and parse_decimal(candidate.get("Change")) > 0:
                target_index = candidate_index
                break
        if target_index is None:
            continue
        used_targets.add(target_index)
        coin = clean(rows[target_index].get("Coin")).upper()
        costs[coin] = costs.get(coin, Decimal("0")) + eur_spend
    return costs


def read_config(path: Path = CONFIG_CSV) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            {key: clean(value) for key, value in row.items()}
            for row in csv.DictReader(handle)
            if clean(row.get("enabled", "1")) not in {"0", "false", "False", "no"}
        ]


def read_cdp_key(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    name = clean(payload.get("name"))
    private_key = clean(payload.get("privateKey"))
    if not name or not private_key:
        raise ValueError(f"{path} must contain name and privateKey fields.")
    return {"name": name, "private_key": private_key}


def coinbase_jwt(key: dict[str, str], host: str, method: str, path: str) -> str:
    now = int(time.time())
    uri = f"{method.upper()} {host}{path}"
    return jwt.encode(
        {
            "sub": key["name"],
            "iss": "cdp",
            "nbf": now,
            "exp": now + 120,
            "uri": uri,
        },
        key["private_key"],
        algorithm="ES256",
        headers={"kid": key["name"], "nonce": uuid.uuid4().hex},
    )


def cdp_jwt(key: dict[str, str], method: str, path: str) -> str:
    return coinbase_jwt(key, CDP_HOST, method, path)


def request_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = Request(url, headers=headers or {"User-Agent": "portfolio-dashboard/1.0"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "portfolio-dashboard/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def coinbase_spot_price_eur(asset: str) -> Decimal:
    payload = request_json(f"{COINBASE_RETAIL_API}/v2/prices/{asset.upper()}-EUR/spot")
    return parse_decimal(((payload.get("data") or {}).get("amount")))


def cdp_get(path: str, key: dict[str, str]) -> dict[str, Any]:
    token = cdp_jwt(key, "GET", path)
    return request_json(
        CDP_BASE_URL + path,
        {
            "Authorization": f"Bearer {token}",
            "User-Agent": "portfolio-dashboard/1.0",
        },
    )


def coinbase_get(path: str, key: dict[str, str]) -> dict[str, Any]:
    sign_path = path.split("?", 1)[0]
    token = coinbase_jwt(key, COINBASE_HOST, "GET", sign_path)
    return request_json(
        f"https://{COINBASE_HOST}{path}",
        {
            "Authorization": f"Bearer {token}",
            "User-Agent": "portfolio-dashboard/1.0",
        },
    )


def iter_coinbase_accounts(key: dict[str, str]) -> list[dict[str, Any]]:
    accounts: list[dict[str, Any]] = []
    path = "/v2/accounts"
    while path:
        payload = coinbase_get(path, key)
        accounts.extend(payload.get("data", []))
        pagination = payload.get("pagination") or {}
        next_uri = clean(pagination.get("next_uri"))
        path = next_uri if next_uri else ""
    return accounts


def iter_coinbase_transactions(account_id: str, key: dict[str, str]) -> list[dict[str, Any]]:
    transactions: list[dict[str, Any]] = []
    path = f"/v2/accounts/{account_id}/transactions"
    while path:
        payload = coinbase_get(path, key)
        transactions.extend(payload.get("data", []))
        pagination = payload.get("pagination") or {}
        next_uri = clean(pagination.get("next_uri"))
        path = next_uri if next_uri else ""
    return transactions


def transaction_audit_row(
    row: dict[str, str],
    account: dict[str, Any],
    transaction: dict[str, Any],
    cost_basis: Decimal,
    quantity: Decimal,
) -> dict[str, str]:
    return {
        "person": row.get("person") or PRIMARY_PORTFOLIO_ID,
        "wallet_label": row.get("wallet_label") or "Coinbase Account",
        "source": row.get("source") or "coinbase_account",
        "account_id": clean(account.get("id")),
        "account_name": clean(account.get("name")),
        "asset": row.get("asset") or "",
        "transaction_id": clean(transaction.get("id")),
        "created_at": clean(transaction.get("created_at")),
        "type": clean(transaction.get("type")),
        "status": clean(transaction.get("status")),
        "quantity": decimal_text(parse_decimal((transaction.get("amount") or {}).get("amount"))),
        "native_amount": decimal_text(parse_decimal((transaction.get("native_amount") or {}).get("amount"))),
        "native_currency": clean((transaction.get("native_amount") or {}).get("currency")),
        "cost_basis_after_eur": decimal_text(cost_basis),
        "quantity_after": decimal_text(quantity),
    }


def coinbase_account_cost_basis(
    row: dict[str, str],
    key: dict[str, str],
    accounts: list[dict[str, Any]],
) -> tuple[Decimal, list[dict[str, str]]]:
    wanted_asset = row["asset"].upper()
    events: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for account in accounts:
        balance = account.get("balance") or {}
        if clean(balance.get("currency")).upper() != wanted_asset:
            continue
        for transaction in iter_coinbase_transactions(clean(account.get("id")), key):
            amount = transaction.get("amount") or {}
            if clean(amount.get("currency")).upper() == wanted_asset:
                events.append((account, transaction))

    quantity = Decimal("0")
    cost_basis = Decimal("0")
    audit_rows: list[dict[str, str]] = []
    internal_types = {"staking_transfer", "retail_eth2_deprecation"}
    for account, transaction in sorted(events, key=lambda item: clean(item[1].get("created_at"))):
        status = clean(transaction.get("status"))
        if status and status != "completed":
            continue
        tx_type = clean(transaction.get("type"))
        tx_quantity = parse_decimal((transaction.get("amount") or {}).get("amount"))
        native = parse_decimal((transaction.get("native_amount") or {}).get("amount"))
        if tx_type in internal_types:
            audit_rows.append(transaction_audit_row(row, account, transaction, cost_basis, quantity))
            continue
        if tx_quantity > 0:
            quantity += tx_quantity
            if native > 0:
                cost_basis += native
        elif tx_quantity < 0:
            sell_quantity = abs(tx_quantity)
            if quantity > 0 and cost_basis > 0:
                cost_basis -= min(cost_basis, cost_basis * sell_quantity / quantity)
            quantity = max(Decimal("0"), quantity - sell_quantity)
        audit_rows.append(transaction_audit_row(row, account, transaction, cost_basis, quantity))
    return cost_basis, audit_rows


def fetch_coinbase_account(
    row: dict[str, str],
    key: dict[str, str],
    fetched_at: str,
    accounts: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    wanted_asset = row["asset"].upper()
    accounts = accounts if accounts is not None else iter_coinbase_accounts(key)
    total_quantity = Decimal("0")
    for account in accounts:
        balance = account.get("balance") or {}
        if clean(balance.get("currency")).upper() == wanted_asset:
            total_quantity += parse_decimal(balance.get("amount"))
    cost_basis, audit_rows = coinbase_account_cost_basis(row, key, accounts)
    price_eur = coinbase_spot_price_eur(wanted_asset) if total_quantity > 0 else Decimal("0")
    return [
        position_row(
            row,
            "coinbase",
            total_quantity,
            total_quantity * price_eur,
            cost_basis,
            fetched_at,
            "ok" if total_quantity > 0 else "empty",
            "Fetched from Coinbase account API and filtered to the configured asset only; P/L uses average-cost transaction history.",
        )
    ], audit_rows


def iter_cdp_balances(address: str, network: str, key: dict[str, str]) -> list[dict[str, Any]]:
    paths = [
        f"/platform/v2/evm/token-balances/{network}/{address}",
        f"/platform/v1/networks/{network}/addresses/{address}/balances",
    ]
    last_error = ""
    for path in paths:
        try:
            payload = cdp_get(path, key)
        except Exception as exc:
            last_error = str(exc)
            continue
        balances = payload.get("balances") or payload.get("data") or payload.get("token_balances") or []
        if isinstance(balances, list):
            return balances
    raise RuntimeError(last_error or f"Could not fetch Coinbase CDP balances for {network}.")


def cdp_balance_quantity(balance: dict[str, Any]) -> tuple[str, Decimal]:
    asset = clean(balance.get("symbol") or balance.get("asset") or balance.get("name"))
    amount = balance.get("amount") or balance.get("balance") or balance.get("quantity")
    if isinstance(amount, dict):
        raw = amount.get("amount") or amount.get("value") or amount.get("amount_decimal")
        decimals = amount.get("decimals")
    else:
        raw = amount
        decimals = balance.get("decimals")
    quantity = parse_decimal(raw)
    if decimals not in (None, "") and quantity == quantity.to_integral_value() and quantity > Decimal("100000"):
        quantity = quantity / (Decimal(10) ** int(decimals))
    return asset.upper(), quantity


def fetch_cdp_evm(row: dict[str, str], key: dict[str, str], fetched_at: str) -> list[dict[str, str]]:
    address = row["address"]
    wanted_asset = row["asset"].upper()
    networks = [item.strip() for item in row.get("networks", "").split(";") if item.strip()] or ["base", "ethereum"]
    output: list[dict[str, str]] = []
    for network in networks:
        try:
            balances = iter_cdp_balances(address, network, key)
        except Exception as exc:
            output.append(position_row(row, network, Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "error", str(exc)))
            continue
        matched = False
        for balance in balances:
            asset, quantity = cdp_balance_quantity(balance)
            if asset != wanted_asset or quantity <= 0:
                continue
            matched = True
            price_eur = coinbase_spot_price_eur(wanted_asset)
            output.append(position_row(row, network, quantity, quantity * price_eur, Decimal("0"), fetched_at, "ok", "Fetched from Coinbase CDP."))
        if not matched:
            output.append(position_row(row, network, Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "empty", "No matching token balance from Coinbase CDP."))
    return output


def evm_address_word(address: str) -> str:
    clean_address = address.lower().removeprefix("0x")
    if len(clean_address) != 40:
        raise ValueError(f"Unsupported EVM address: {address}")
    return clean_address.rjust(64, "0")


def evm_call(rpc_url: str, to_address: str, data: str) -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": to_address, "data": data}, "latest"],
    }
    response = post_json(rpc_url, payload)
    if response.get("error"):
        raise RuntimeError(str(response["error"]))
    return clean(response.get("result"))


def fetch_bsc_token(row: dict[str, str], fetched_at: str, cost_basis_by_asset: dict[str, Decimal] | None = None) -> list[dict[str, str]]:
    address = row["address"]
    contract = row.get("contract_address", "")
    if not contract:
        return [position_row(row, "bnb-smart-chain", Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "error", "Missing contract_address.")]
    raw_balance = evm_call(BSC_RPC_URL, contract, "0x70a08231" + evm_address_word(address))
    quantity = Decimal(int(raw_balance or "0x0", 16)) / (Decimal(10) ** int(row.get("decimals") or "18"))
    price_eur = coinbase_spot_price_eur(row.get("asset") or "USDC")
    cost_basis = (cost_basis_by_asset or {}).get(clean(row.get("asset")).upper(), Decimal("0"))
    return [
        position_row(
            row,
            "bnb-smart-chain",
            quantity,
            quantity * price_eur,
            cost_basis,
            fetched_at,
            "ok" if quantity > 0 else "empty",
            "Fetched exact BNB Smart Chain token contract balance.",
        )
    ]


def fetch_ton(row: dict[str, str], fetched_at: str, cost_basis_by_asset: dict[str, Decimal] | None = None) -> list[dict[str, str]]:
    address = row["address"]
    payload = request_json(f"{TONAPI_BASE_URL}/v2/accounts/{address}")
    quantity = parse_decimal(payload.get("balance")) / Decimal("1000000000")
    price_eur = coinbase_spot_price_eur("TON")
    cost_basis = (cost_basis_by_asset or {}).get("TON", Decimal("0"))
    return [
        position_row(
            row,
            "ton",
            quantity,
            quantity * price_eur,
            cost_basis,
            fetched_at,
            "ok",
            "Balance fetched from TonAPI because Coinbase CDP has no TON balance endpoint; price fetched from Coinbase.",
        )
    ]


def position_row(
    row: dict[str, str],
    network: str,
    quantity: Decimal,
    market_value_eur: Decimal,
    cost_basis_eur: Decimal,
    fetched_at: str,
    status: str,
    message: str,
) -> dict[str, str]:
    return {
        "person": row.get("person") or PRIMARY_PORTFOLIO_ID,
        "broker": "Crypto Wallet",
        "wallet_label": row.get("wallet_label") or "Wallet",
        "wallet_address": row.get("address") or "",
        "chain": row.get("chain") or network,
        "network": network,
        "asset": row.get("asset") or "",
        "symbol": row.get("symbol") or "",
        "quantity": decimal_text(quantity),
        "market_value_eur": decimal_text(market_value_eur) if market_value_eur > 0 else "",
        "cost_basis_eur": decimal_text(cost_basis_eur) if cost_basis_eur > 0 else "",
        "asset_class": "Crypto",
        "sector": "Crypto",
        "geo": "Global",
        "source": row.get("source") or "",
        "fetched_at": fetched_at,
        "status": status,
        "message": message,
    }


def write_positions(rows: list[dict[str, str]], path: Path = POSITIONS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    live_rows = [row for row in rows if parse_decimal(row.get("quantity")) > 0]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=POSITION_FIELDS)
        writer.writeheader()
        writer.writerows(live_rows)


def write_transactions(rows: list[dict[str, str]], path: Path = TRANSACTIONS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRANSACTION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def update(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    key = read_cdp_key(Path(args.cdp_key)) if args.cdp_key else None
    rows: list[dict[str, str]] = []
    transaction_rows: list[dict[str, str]] = []
    coinbase_accounts = iter_coinbase_accounts(key) if key else []
    binance_history = Path(args.binance_history) if args.binance_history else latest_binance_history()
    binance_costs = binance_cost_basis(binance_history)
    for item in config:
        source = item.get("source", "")
        if source == "coinbase_cdp":
            if key is None:
                rows.append(position_row(item, "", Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "error", "Missing --cdp-key."))
            else:
                rows.extend(fetch_cdp_evm(item, key, fetched_at))
        elif source == "coinbase_account":
            if key is None:
                rows.append(position_row(item, "coinbase", Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "error", "Missing --cdp-key."))
            else:
                try:
                    position_rows, audit_rows = fetch_coinbase_account(item, key, fetched_at, coinbase_accounts)
                    rows.extend(position_rows)
                    transaction_rows.extend(audit_rows)
                except Exception as exc:
                    rows.append(position_row(item, "coinbase", Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "error", str(exc)))
        elif source == "bsc_rpc":
            try:
                rows.extend(fetch_bsc_token(item, fetched_at, binance_costs))
            except Exception as exc:
                rows.append(position_row(item, "bnb-smart-chain", Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "error", str(exc)))
        elif source == "tonapi":
            try:
                rows.extend(fetch_ton(item, fetched_at, binance_costs))
            except Exception as exc:
                rows.append(position_row(item, "ton", Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "error", str(exc)))
        else:
            rows.append(position_row(item, "", Decimal("0"), Decimal("0"), Decimal("0"), fetched_at, "error", f"Unsupported source: {source}"))

    if args.dry_run:
        print(json.dumps({"positions": rows, "transactions": transaction_rows}, indent=2))
    else:
        write_positions(rows, Path(args.output))
        write_transactions(transaction_rows, Path(args.transactions_output))
    print(f"Wallet config rows: {len(config)}")
    print(f"Live position rows: {sum(1 for row in rows if parse_decimal(row.get('quantity')) > 0)}")
    print(f"Coinbase transaction audit rows: {len(transaction_rows)}")
    if binance_history:
        print(f"Binance history cost source: {binance_history}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch configured public crypto wallet balances for the dashboard.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("--config", default=str(CONFIG_CSV))
    update_parser.add_argument("--output", default=str(POSITIONS_CSV))
    update_parser.add_argument("--transactions-output", default=str(TRANSACTIONS_CSV))
    update_parser.add_argument("--binance-history", default="")
    update_parser.add_argument("--cdp-key", default="")
    update_parser.add_argument("--dry-run", action="store_true")
    update_parser.set_defaults(func=update)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
