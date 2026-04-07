from datamodel import Order, OrderDepth, TradingState

import json
import math
from typing import Any, Dict, List, Optional, Tuple

POSITION_LIMITS: Dict[str, int] = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

PriceLevel = Tuple[int, int]


def load_trader_state(trader_data: str) -> Dict[str, Any]:
    if not trader_data:
        return {"products": {}}

    try:
        data = json.loads(trader_data)
    except Exception:
        return {"products": {}}

    if not isinstance(data, dict):
        return {"products": {}}

    data.setdefault("products", {})
    return data


def dump_trader_state(state: Dict[str, Any]) -> str:
    return json.dumps(state, separators=(",", ":"), sort_keys=True)


def get_product_memory(state: Dict[str, Any], product: str) -> Dict[str, Any]:
    products = state.setdefault("products", {})
    memory = products.setdefault(product, {})
    if not isinstance(memory, dict):
        memory = {}
        products[product] = memory
    return memory


def normalize_book(order_depth: OrderDepth) -> Tuple[List[PriceLevel], List[PriceLevel]]:
    """
    Returns sorted price levels as:
    - buys: [(price, positive_quantity)] sorted descending by price
    - sells: [(price, positive_quantity)] sorted ascending by price
    """
    buys = sorted(
        [(int(price), int(quantity)) for price, quantity in order_depth.buy_orders.items() if int(quantity) > 0],
        key=lambda level: level[0],
        reverse=True,
    )
    sells = sorted(
        [(int(price), abs(int(quantity))) for price, quantity in order_depth.sell_orders.items() if int(quantity) != 0],
        key=lambda level: level[0],
    )
    return buys, sells


def best_bid(buys: List[PriceLevel]) -> Optional[int]:
    return buys[0][0] if buys else None


def best_ask(sells: List[PriceLevel]) -> Optional[int]:
    return sells[0][0] if sells else None


def mid_price(buys: List[PriceLevel], sells: List[PriceLevel]) -> Optional[float]:
    bid = best_bid(buys)
    ask = best_ask(sells)

    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    if bid is not None:
        return float(bid)
    if ask is not None:
        return float(ask)
    return None


def buy_capacity(position: int, position_limit: int) -> int:
    return max(0, position_limit - position)


def sell_capacity(position: int, position_limit: int) -> int:
    return max(0, position_limit + position)


def inventory_only_quote_sizes(position: int, position_limit: int) -> Tuple[int, int]:
    """
    No fixed quote-size knob.
    The buy size is the remaining room before hitting +limit.
    The sell size is the remaining room before hitting -limit.
    This is a pure inventory-based size skew.
    """
    return buy_capacity(position, position_limit), sell_capacity(position, position_limit)


def append_order(orders: List[Order], symbol: str, price: int, quantity: int) -> None:
    if quantity == 0:
        return
    orders.append(Order(symbol, int(price), int(quantity)))


class BaseStrategy:
    def __init__(self, product: str, position_limit: int) -> None:
        self.product = product
        self.position_limit = position_limit

    def compute_fair_value(
        self,
        state: TradingState,
        symbol: str,
        product: str,
        order_depth: OrderDepth,
        position: int,
        memory: Dict[str, Any],
    ) -> Optional[float]:
        raise NotImplementedError

    def fair_buy_price(self, fair_value: float) -> int:
        return int(math.floor(fair_value))

    def fair_sell_price(self, fair_value: float) -> int:
        return int(math.ceil(fair_value))

    def choose_quote_prices(
        self,
        fair_value: float,
        buys: List[PriceLevel],
        sells: List[PriceLevel],
    ) -> Tuple[int, int]:
        """
        Quote one tick in front of the current best prices when possible,
        but do not cross to the wrong side of fair value.
        """
        fair_bid = self.fair_buy_price(fair_value)
        fair_ask = self.fair_sell_price(fair_value)

        bb = best_bid(buys)
        ba = best_ask(sells)

        if bb is not None and ba is not None:
            spread = ba - bb

            if spread >= 2:
                quote_bid = min(bb + 1, fair_bid)
                quote_ask = max(ba - 1, fair_ask)
            else:
                # No price strictly inside the spread; just join the current edge.
                quote_bid = min(bb, fair_bid)
                quote_ask = max(ba, fair_ask)
        elif bb is not None:
            quote_bid = min(bb + 1, fair_bid)
            quote_ask = max(bb + 2, fair_ask)
        elif ba is not None:
            quote_bid = min(ba - 2, fair_bid)
            quote_ask = max(ba - 1, fair_ask)
        else:
            quote_bid = fair_bid
            quote_ask = fair_ask if fair_ask > fair_bid else fair_bid + 1

        if quote_bid >= quote_ask:
            # Final safety fallback around fair value.
            quote_bid = fair_bid
            quote_ask = fair_ask if fair_ask > fair_bid else fair_bid + 1

        return quote_bid, quote_ask

    def generate_orders(
        self,
        state: TradingState,
        symbol: str,
        product: str,
        order_depth: OrderDepth,
        position: int,
        memory: Dict[str, Any],
    ) -> Tuple[List[Order], Dict[str, Any]]:
        buys, sells = normalize_book(order_depth)
        fair_value = self.compute_fair_value(state, symbol, product, order_depth, position, memory)
        if fair_value is None:
            return [], memory

        orders: List[Order] = []
        current_mid = mid_price(buys, sells)
        bb = best_bid(buys)
        ba = best_ask(sells)

        # Take only clear free value relative to fair.
        remaining_buy = buy_capacity(position, self.position_limit)
        remaining_sell = sell_capacity(position, self.position_limit)
        net_filled = 0

        fair_bid = self.fair_buy_price(fair_value)
        fair_ask = self.fair_sell_price(fair_value)

        for ask_price, ask_quantity in sells:
            if remaining_buy <= 0:
                break
            if ask_price >= fair_bid:
                break
            quantity = min(ask_quantity, remaining_buy)
            append_order(orders, symbol, ask_price, quantity)
            remaining_buy -= quantity
            net_filled += quantity

        for bid_price, bid_quantity in buys:
            if remaining_sell <= 0:
                break
            if bid_price <= fair_ask:
                break
            quantity = min(bid_quantity, remaining_sell)
            append_order(orders, symbol, bid_price, -quantity)
            remaining_sell -= quantity
            net_filled -= quantity

        working_position = position + net_filled
        remaining_buy = buy_capacity(working_position, self.position_limit)
        remaining_sell = sell_capacity(working_position, self.position_limit)

        # Hard unwind rule at the exact position limit.
        if working_position >= self.position_limit:
            append_order(orders, symbol, fair_ask, -working_position)
        elif working_position <= -self.position_limit:
            append_order(orders, symbol, fair_bid, -working_position)
        else:
            quote_bid, quote_ask = self.choose_quote_prices(fair_value, buys, sells)
            bid_size, ask_size = inventory_only_quote_sizes(working_position, self.position_limit)

            if remaining_buy > 0 and bid_size > 0:
                append_order(orders, symbol, quote_bid, min(bid_size, remaining_buy))
            if remaining_sell > 0 and ask_size > 0:
                append_order(orders, symbol, quote_ask, -min(ask_size, remaining_sell))

        memory["last_fair"] = round(float(fair_value), 4)
        if current_mid is not None:
            memory["last_mid"] = round(float(current_mid), 4)
        if bb is not None:
            memory["last_best_bid"] = bb
        if ba is not None:
            memory["last_best_ask"] = ba
        memory["last_position"] = int(position)

        return orders, memory


class EmeraldsStrategy(BaseStrategy):
    FAIR_VALUE = 10000.0

    def __init__(self) -> None:
        super().__init__(product="EMERALDS", position_limit=POSITION_LIMITS["EMERALDS"])

    def compute_fair_value(
        self,
        state: TradingState,
        symbol: str,
        product: str,
        order_depth: OrderDepth,
        position: int,
        memory: Dict[str, Any],
    ) -> Optional[float]:
        memory["anchor"] = self.FAIR_VALUE
        return self.FAIR_VALUE


class TomatoesStrategy(BaseStrategy):
    def __init__(self) -> None:
        super().__init__(product="TOMATOES", position_limit=POSITION_LIMITS["TOMATOES"])

    def compute_fair_value(
        self,
        state: TradingState,
        symbol: str,
        product: str,
        order_depth: OrderDepth,
        position: int,
        memory: Dict[str, Any],
    ) -> Optional[float]:
        buys, sells = normalize_book(order_depth)
        current_mid = mid_price(buys, sells)

        if current_mid is not None:
            memory["pricing_rule"] = "best_bid_ask_mid"
            return current_mid

        previous = memory.get("last_fair")
        return float(previous) if previous is not None else None


class Trader:
    def __init__(self) -> None:
        self.strategies = {
            "EMERALDS": EmeraldsStrategy(),
            "TOMATOES": TomatoesStrategy(),
        }

    def bid(self) -> int:
        return 0

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        result: Dict[str, List[Order]] = {}
        trader_state = load_trader_state(state.traderData)

        for symbol, order_depth in state.order_depths.items():
            listing = state.listings.get(symbol)
            product = listing.product if listing is not None else symbol

            strategy = self.strategies.get(product)
            if strategy is None:
                result[symbol] = []
                continue

            memory = get_product_memory(trader_state, product)
            position = state.position.get(product, 0)
            orders, updated_memory = strategy.generate_orders(
                state=state,
                symbol=symbol,
                product=product,
                order_depth=order_depth,
                position=position,
                memory=memory,
            )
            trader_state["products"][product] = updated_memory
            result[symbol] = orders

        if state.timestamp % 1000 == 0:
            snapshots = []
            for product, memory in trader_state.get("products", {}).items():
                fair_value = memory.get("last_fair")
                best_bid_price = memory.get("last_best_bid")
                best_ask_price = memory.get("last_best_ask")
                position = state.position.get(product, 0)
                snapshots.append(
                    f"{product}:pos={position},fair={fair_value},bid={best_bid_price},ask={best_ask_price}"
                )
            if snapshots:
                print(f"t={state.timestamp} | " + " | ".join(snapshots))

        conversions = 0
        return result, conversions, dump_trader_state(trader_state)
