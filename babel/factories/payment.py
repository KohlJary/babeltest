"""Factories for example.payment classes."""

from example.payment import OrderService, PaymentGateway


def order_service() -> OrderService:
    """Factory for OrderService with real PaymentGateway."""
    return OrderService(PaymentGateway())
