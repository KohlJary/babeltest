/**
 * Factories for example/js/payment.mjs classes.
 */

import { OrderService, PaymentGateway } from '../../example/js/payment.mjs';

/**
 * Factory for OrderService with real PaymentGateway.
 */
export function orderService() {
  return new OrderService(new PaymentGateway());
}
