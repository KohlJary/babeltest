/**
 * Payment services for mock testing.
 */

/**
 * Custom error for payment declined.
 */
export class PaymentDeclined extends Error {
  constructor(message = 'Payment declined') {
    super(message);
    this.name = 'PaymentDeclined';
  }
}

/**
 * External payment gateway (to be mocked in tests).
 */
export class PaymentGateway {
  /**
   * Charge a card. In real code, this calls an external API.
   */
  charge(amount, cardToken) {
    // This would normally call Stripe/etc
    throw new Error('Real PaymentGateway should be mocked in tests');
  }
}

/**
 * Order result.
 */
export class Order {
  constructor(id, status, total) {
    this.id = id;
    this.status = status;
    this.total = total;
  }
}

/**
 * Order processing service that depends on PaymentGateway.
 */
export class OrderService {
  constructor(paymentGateway = null) {
    this.paymentGateway = paymentGateway || new PaymentGateway();
    this._nextId = 1000;
  }

  /**
   * Place an order, charging the user's card.
   */
  placeOrder(userId, amount, cardToken) {
    try {
      // This calls the payment gateway (which we'll mock)
      this.paymentGateway.charge(amount, cardToken);

      const orderId = this._nextId++;

      return new Order(orderId, 'placed', amount);

    } catch (error) {
      if (error.name === 'PaymentDeclined' || error instanceof PaymentDeclined) {
        return new Order(0, 'declined', amount);
      }

      return new Order(0, 'error', amount);
    }
  }
}
