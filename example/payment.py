"""Payment services for mock testing."""

from dataclasses import dataclass


class PaymentDeclined(Exception):
    """Payment was declined."""
    pass


class PaymentGateway:
    """External payment gateway (to be mocked in tests)."""

    def charge(self, amount: float, card_token: str) -> dict:
        """Charge a card. In real code, this calls an external API."""
        # This would normally call Stripe/etc
        raise NotImplementedError("Real PaymentGateway should be mocked in tests")


@dataclass
class Order:
    """Order result."""
    id: int
    status: str
    total: float


class OrderService:
    """Order processing service that depends on PaymentGateway."""

    def __init__(self, payment_gateway: PaymentGateway | None = None):
        self.payment_gateway = payment_gateway or PaymentGateway()
        self._next_id = 1000

    def place_order(self, user_id: int, amount: float, card_token: str) -> Order:
        """Place an order, charging the user's card.

        Args:
            user_id: The user placing the order
            amount: Order total
            card_token: Payment card token

        Returns:
            Order with status

        Raises:
            PaymentDeclined: If payment fails
        """
        try:
            # This calls the payment gateway (which we'll mock)
            self.payment_gateway.charge(amount, card_token)

            order_id = self._next_id
            self._next_id += 1

            return Order(id=order_id, status="placed", total=amount)

        except PaymentDeclined:
            return Order(id=0, status="declined", total=amount)

        except Exception as e:
            return Order(id=0, status="error", total=amount)
