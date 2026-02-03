/**
 * Example services - unified target: example.services
 */

export class UserService {
  constructor() {
    this._users = [
      { id: 1, name: "Kohl", email: "kohl@example.com", active: true },
      { id: 2, name: "Alice", email: "alice@example.com", active: true },
    ];
  }

  get_by_id(userId) {
    return this._users.find((u) => u.id === userId) || null;
  }

  create(name, email) {
    const user = {
      id: this._users.length + 1,
      name,
      email,
      active: true,
    };
    this._users.push(user);
    return user;
  }

  deactivate(userId) {
    const user = this._users.find((u) => u.id === userId);
    if (!user) return false;
    user.active = false;
    return true;
  }

  // Aliases for camelCase compatibility
  getById(userId) {
    return this.get_by_id(userId);
  }
}

export class Calculator {
  add(a, b) {
    return a + b;
  }

  multiply(a, b) {
    return a * b;
  }
}
