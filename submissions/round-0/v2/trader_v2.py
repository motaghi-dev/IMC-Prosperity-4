from datamodel import Order, OrderDepth, TradingState

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from datamodel import Order, OrderDepth

POSITION_LIMITS: Dict[str, int] = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

PriceLevel = Tuple[int, int]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def update_ema(previous: Optional[float], value: float, alpha: float) -> float:
    if previous is None:
        return value
    return alpha * value + (1.0 - alpha) * previous


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


def visible_book_imbalance(buys: List[PriceLevel], sells: List[PriceLevel], levels: int = 3) -> float:
    buy_qty = sum(quantity for _, quantity in buys[:levels])
    sell_qty = sum(quantity for _, quantity in sells[:levels])
    total = buy_qty + sell_qty
    if total == 0:
        return 0.0
    return (buy_qty - sell_qty) / total


def multi_level_microprice(buys: List[PriceLevel], sells: List[PriceLevel], levels: int = 3) -> Optional[float]:
    """
    Uses multiple levels and cross-weights each side by the opposite side's visible depth.
    This behaves like a generalized microprice and tends to shift toward the side under pressure.
    """
    bid_levels = buys[:levels]
    ask_levels = sells[:levels]

    if bid_levels and not ask_levels:
        return float(bid_levels[0][0])
    if ask_levels and not bid_levels:
        return float(ask_levels[0][0])
    if not bid_levels and not ask_levels:
        return None

    total_bid_qty = sum(quantity for _, quantity in bid_levels)
    total_ask_qty = sum(quantity for _, quantity in ask_levels)
    if total_bid_qty == 0 or total_ask_qty == 0:
        return mid_price(bid_levels, ask_levels)

    avg_bid = sum(price * quantity for price, quantity in bid_levels) / total_bid_qty
    avg_ask = sum(price * quantity for price, quantity in ask_levels) / total_ask_qty

    return (avg_ask * total_bid_qty + avg_bid * total_ask_qty) / (total_bid_qty + total_ask_qty)


def buy_capacity(position: int, position_limit: int) -> int:
    return max(0, position_limit - position)


def sell_capacity(position: int, position_limit: int) -> int:
    return max(0, position_limit + position)


def inventory_adjusted_sizes(position: int, position_limit: int, base_size: int) -> Tuple[int, int]:
    if position_limit <= 0:
        return base_size, base_size

    ratio = position / float(position_limit)
    bid_factor = clamp(1.0 - ratio, 0.25, 2.0)
    ask_factor = clamp(1.0 + ratio, 0.25, 2.0)

    bid_size = max(1, int(round(base_size * bid_factor)))
    ask_size = max(1, int(round(base_size * ask_factor)))
    return bid_size, ask_size


def append_order(orders: List[Order], symbol: str, price: int, quantity: int) -> None:
    if quantity == 0:
        return
    orders.append(Order(symbol, int(price), int(quantity)))


import math
from typing import Any, Dict, List, Optional, Tuple

from datamodel import Order, OrderDepth, TradingState



class BaseStrategy:
    def __init__(
        self,
        product: str,
        position_limit: int,
        quote_size: int,
        quote_edge: float,
        take_threshold: float,
        inventory_skew: float,
        max_take_size: int,
    ) -> None:
        self.product = product
        self.position_limit = position_limit
        self.quote_size = quote_size
        self.quote_edge = quote_edge
        self.take_threshold = take_threshold
        self.inventory_skew = inventory_skew
        self.max_take_size = max_take_size

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

    def post_process(
        self,
        fair_value: float,
        state: TradingState,
        symbol: str,
        product: str,
        order_depth: OrderDepth,
        position: int,
        memory: Dict[str, Any],
    ) -> None:
        return None

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

        best_bid_price = best_bid(buys)
        best_ask_price = best_ask(sells)
        current_mid = mid_price(buys, sells)

        orders: List[Order] = []

        remaining_buy = buy_capacity(position, self.position_limit)
        remaining_sell = sell_capacity(position, self.position_limit)
        net_filled = 0

        for ask_price, ask_quantity in sells:
            if remaining_buy <= 0:
                break
            if ask_price > fair_value - self.take_threshold:
                break
            quantity = min(ask_quantity, remaining_buy, self.max_take_size)
            append_order(orders, symbol, ask_price, quantity)
            remaining_buy -= quantity
            net_filled += quantity

        for bid_price, bid_quantity in buys:
            if remaining_sell <= 0:
                break
            if bid_price < fair_value + self.take_threshold:
                break
            quantity = min(bid_quantity, remaining_sell, self.max_take_size)
            append_order(orders, symbol, bid_price, -quantity)
            remaining_sell -= quantity
            net_filled -= quantity

        working_position = position + net_filled
        remaining_buy = buy_capacity(working_position, self.position_limit)
        remaining_sell = sell_capacity(working_position, self.position_limit)

        reservation_price = fair_value - self.inventory_skew * working_position
        desired_bid = int(math.floor(reservation_price - self.quote_edge))
        desired_ask = int(math.ceil(reservation_price + self.quote_edge))

        if best_ask_price is not None:
            desired_bid = min(desired_bid, best_ask_price - 1)
        if best_bid_price is not None:
            desired_ask = max(desired_ask, best_bid_price + 1)

        if desired_bid >= desired_ask:
            desired_bid = int(math.floor(fair_value)) - 1
            desired_ask = int(math.ceil(fair_value)) + 1
            if best_ask_price is not None:
                desired_bid = min(desired_bid, best_ask_price - 1)
            if best_bid_price is not None:
                desired_ask = max(desired_ask, best_bid_price + 1)

        passive_bid_size, passive_ask_size = inventory_adjusted_sizes(
            working_position,
            self.position_limit,
            self.quote_size,
        )

        if remaining_buy > 0:
            append_order(orders, symbol, desired_bid, min(passive_bid_size, remaining_buy))
        if remaining_sell > 0:
            append_order(orders, symbol, desired_ask, -min(passive_ask_size, remaining_sell))

        memory["last_fair"] = round(float(fair_value), 4)
        if current_mid is not None:
            memory["last_mid"] = round(float(current_mid), 4)
        if best_bid_price is not None:
            memory["last_best_bid"] = best_bid_price
        if best_ask_price is not None:
            memory["last_best_ask"] = best_ask_price

        self.post_process(fair_value, state, symbol, product, order_depth, position, memory)
        return orders, memory


class EmeraldsStrategy(BaseStrategy):
    FAIR_VALUE = 10000.0

    def __init__(self) -> None:
        super().__init__(
            product="EMERALDS",
            position_limit=POSITION_LIMITS["EMERALDS"],
            quote_size=12,
            quote_edge=3.0,
            take_threshold=2.0,
            inventory_skew=0.10,
            max_take_size=20,
        )

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
        signal = 0.0
        if best_ask(sells) == 10000:
            signal += 1.0
        if best_bid(buys) == 10000:
            signal -= 1.0

        fair_value = self.FAIR_VALUE + signal
        memory["anchor"] = self.FAIR_VALUE
        memory["anchor_signal"] = signal
        return fair_value


class TomatoesStrategy(BaseStrategy):
    def __init__(self) -> None:
        super().__init__(
            product="TOMATOES",
            position_limit=POSITION_LIMITS["TOMATOES"],
            quote_size=10,
            quote_edge=3.0,
            take_threshold=2.0,
            inventory_skew=0.12,
            max_take_size=16,
        )
        self.fast_alpha = 0.28
        self.slow_alpha = 0.10

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
        book_price = multi_level_microprice(buys, sells, levels=3)

        if current_mid is None and book_price is None:
            previous = memory.get("last_fair")
            return float(previous) if previous is not None else None

        if current_mid is None:
            current_mid = book_price
        if book_price is None:
            book_price = current_mid

        previous_fast = memory.get("ema_fast")
        previous_slow = memory.get("ema_slow")
        ema_fast = update_ema(previous_fast, current_mid, self.fast_alpha)
        ema_slow = update_ema(previous_slow, current_mid, self.slow_alpha)

        book_signal = clamp(book_price - current_mid, -4.0, 4.0)
        mean_reversion_signal = clamp(ema_fast - current_mid, -3.0, 3.0)
        slow_anchor_signal = clamp(ema_slow - current_mid, -4.0, 4.0)
        imbalance_signal = 1.5 * visible_book_imbalance(buys, sells, levels=3)

        fair_value = current_mid
        fair_value += 0.90 * book_signal
        fair_value += 0.35 * mean_reversion_signal
        fair_value += 0.15 * slow_anchor_signal
        fair_value += imbalance_signal

        memory["ema_fast"] = round(float(ema_fast), 4)
        memory["ema_slow"] = round(float(ema_slow), 4)
        memory["book_fair"] = round(float(book_price), 4)
        memory["imbalance"] = round(float(imbalance_signal), 4)

        return fair_value


from typing import Dict, List, Tuple

from datamodel import Order, TradingState



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
                best_bid = memory.get("last_best_bid")
                best_ask = memory.get("last_best_ask")
                position = state.position.get(product, 0)
                snapshots.append(
                    f"{product}:pos={position},fair={fair_value},bid={best_bid},ask={best_ask}"
                )
            if snapshots:
                print(f"t={state.timestamp} | " + " | ".join(snapshots))

        conversions = 0
        return result, conversions, dump_trader_state(trader_state)
