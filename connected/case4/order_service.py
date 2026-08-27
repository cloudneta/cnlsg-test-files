"""
Order Service

Internal order processing service.
Handles order creation, inventory validation, pricing,
discount calculation, shipment preparation, and reporting.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order_service")


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


@dataclass
class Product:
    product_id: int
    name: str
    price: int
    stock: int
    category: str


@dataclass
class OrderItem:
    product_id: int
    quantity: int
    unit_price: int


@dataclass
class Order:
    order_id: int
    customer_id: int
    items: List[OrderItem]
    status: OrderStatus
    total_price: int
    created_at: datetime


# --------------------------------------------------------------------------
# In-memory repositories
# --------------------------------------------------------------------------

PRODUCTS: Dict[int, Product] = {
    1: Product(1, "Laptop", 1500000, 20, "electronics"),
    2: Product(2, "Monitor", 450000, 35, "electronics"),
    3: Product(3, "Keyboard", 120000, 50, "accessories"),
    4: Product(4, "Mouse", 70000, 80, "accessories"),
    5: Product(5, "USB Hub", 50000, 100, "accessories"),
}

ORDERS: Dict[int, Order] = {}

_next_order_id = 1000


# --------------------------------------------------------------------------
# Product operations
# --------------------------------------------------------------------------

def get_product(product_id: int) -> Optional[Product]:
    return PRODUCTS.get(product_id)


def list_products() -> List[Product]:
    return list(PRODUCTS.values())


def get_products_by_category(category: str) -> List[Product]:
    result = []

    for product in PRODUCTS.values():
        if product.category == category:
            result.append(product)

    return result


def check_stock(product_id: int, quantity: int) -> bool:
    product = get_product(product_id)

    if product is None:
        return False

    return product.stock >= quantity


def decrease_stock(product_id: int, quantity: int) -> None:
    product = get_product(product_id)

    if product is None:
        raise ValueError("Product not found")

    if product.stock < quantity:
        raise ValueError("Insufficient stock")

    product.stock -= quantity


def increase_stock(product_id: int, quantity: int) -> None:
    product = get_product(product_id)

    if product is None:
        raise ValueError("Product not found")

    product.stock += quantity


# --------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------

def calculate_item_price(product: Product, quantity: int) -> int:
    return product.price * quantity


def calculate_discount(customer_id: int, subtotal: int) -> int:
    if subtotal >= 3000000:
        return int(subtotal * 0.10)

    if subtotal >= 1000000:
        return int(subtotal * 0.05)

    if customer_id % 10 == 0:
        return int(subtotal * 0.03)

    return 0


def calculate_shipping_fee(subtotal: int) -> int:
    if subtotal >= 100000:
        return 0

    return 3000


def calculate_order_total(
    customer_id: int,
    items: List[OrderItem],
) -> int:

    subtotal = 0

    for item in items:
        subtotal += item.unit_price * item.quantity

    discount = calculate_discount(customer_id, subtotal)
    shipping_fee = calculate_shipping_fee(subtotal)

    return subtotal - discount + shipping_fee


# --------------------------------------------------------------------------
# Order validation
# --------------------------------------------------------------------------

def validate_order_items(items: List[Dict]) -> List[str]:
    errors = []

    if not items:
        errors.append("Order must contain at least one item")
        return errors

    for item in items:
        product_id = item.get("product_id")
        quantity = item.get("quantity", 0)

        product = get_product(product_id)

        if product is None:
            errors.append(
                f"Product {product_id} does not exist"
            )
            continue

        if quantity <= 0:
            errors.append(
                f"Invalid quantity for product {product_id}"
            )
            continue

        if not check_stock(product_id, quantity):
            errors.append(
                f"Insufficient stock for product {product_id}"
            )

    return errors


# --------------------------------------------------------------------------
# Order creation
# --------------------------------------------------------------------------

def create_order(
    customer_id: int,
    raw_items: List[Dict],
) -> Order:

    global _next_order_id

    errors = validate_order_items(raw_items)

    if errors:
        raise ValueError(", ".join(errors))

    order_items = []

    for raw_item in raw_items:
        product = get_product(raw_item["product_id"])
        quantity = raw_item["quantity"]

        order_items.append(
            OrderItem(
                product_id=product.product_id,
                quantity=quantity,
                unit_price=product.price,
            )
        )

    total_price = calculate_order_total(
        customer_id,
        order_items,
    )

    order = Order(
        order_id=_next_order_id,
        customer_id=customer_id,
        items=order_items,
        status=OrderStatus.PENDING,
        total_price=total_price,
        created_at=datetime.utcnow(),
    )

    ORDERS[_next_order_id] = order
    _next_order_id += 1

    logger.info(
        "Created order %s for customer %s",
        order.order_id,
        customer_id,
    )

    return order


# --------------------------------------------------------------------------
# Order processing
# --------------------------------------------------------------------------

def confirm_order(order_id: int) -> Order:
    order = ORDERS.get(order_id)

    if order is None:
        raise ValueError("Order not found")

    if order.status != OrderStatus.PENDING:
        raise ValueError("Order cannot be confirmed")

    for item in order.items:
        if not check_stock(item.product_id, item.quantity):
            raise ValueError(
                f"Insufficient stock for product {item.product_id}"
            )

    for item in order.items:
        decrease_stock(
            item.product_id,
            item.quantity,
        )

    order.status = OrderStatus.CONFIRMED

    logger.info(
        "Confirmed order %s",
        order.order_id,
    )

    return order


def process_order(order_id: int) -> Order:
    order = ORDERS.get(order_id)

    if order is None:
        raise ValueError("Order not found")

    if order.status != OrderStatus.CONFIRMED:
        raise ValueError(
            "Only confirmed orders can be processed"
        )

    order.status = OrderStatus.PROCESSING

    logger.info(
        "Processing order %s",
        order.order_id,
    )

    return order


def ship_order(order_id: int) -> Order:
    order = ORDERS.get(order_id)

    if order is None:
        raise ValueError("Order not found")

    if order.status != OrderStatus.PROCESSING:
        raise ValueError(
            "Only processing orders can be shipped"
        )

    order.status = OrderStatus.SHIPPED

    logger.info(
        "Shipped order %s",
        order.order_id,
    )

    return order


# --------------------------------------------------------------------------
# Cancellation
# --------------------------------------------------------------------------

def cancel_order(order_id: int) -> Order:
    order = ORDERS.get(order_id)

    if order is None:
        raise ValueError("Order not found")

    if order.status == OrderStatus.SHIPPED:
        raise ValueError(
            "Shipped order cannot be cancelled"
        )

    if order.status in (
        OrderStatus.CONFIRMED,
        OrderStatus.PROCESSING,
    ):
        for item in order.items:
            increase_stock(
                item.product_id,
                item.quantity,
            )

    order.status = OrderStatus.CANCELLED

    logger.warning(
        "Cancelled order %s",
        order.order_id,
    )

    return order


# --------------------------------------------------------------------------
# Query operations
# --------------------------------------------------------------------------

def get_order(order_id: int) -> Optional[Order]:
    return ORDERS.get(order_id)


def get_customer_orders(customer_id: int) -> List[Order]:
    result = []

    for order in ORDERS.values():
        if order.customer_id == customer_id:
            result.append(order)

    return result


def get_orders_by_status(
    status: OrderStatus,
) -> List[Order]:

    result = []

    for order in ORDERS.values():
        if order.status == status:
            result.append(order)

    return result


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def calculate_total_sales() -> int:
    total = 0

    for order in ORDERS.values():
        if order.status != OrderStatus.CANCELLED:
            total += order.total_price

    return total


def generate_sales_report() -> Dict:
    report = {
        "total_orders": len(ORDERS),
        "total_sales": calculate_total_sales(),
        "pending": 0,
        "confirmed": 0,
        "processing": 0,
        "shipped": 0,
        "cancelled": 0,
    }

    for order in ORDERS.values():
        report[order.status.value] += 1

    return report


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------

def health_check() -> Dict:
    return {
        "status": "healthy",
        "products": len(PRODUCTS),
        "orders": len(ORDERS),
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    print(health_check())
