/**
 * Example math utilities - unified target: example.math
 */

export function add(a, b) {
  return a + b;
}

export function subtract(a, b) {
  return a - b;
}

export function divide(a, b) {
  if (b === 0) {
    throw new Error("divide by zero");
  }
  return a / b;
}

export function isEven(n) {
  return n % 2 === 0;
}

// Aliases for snake_case compatibility
export const is_even = isEven;
