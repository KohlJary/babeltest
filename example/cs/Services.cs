namespace example.services;

/// <summary>
/// Example services - unified target: example.services
/// </summary>

public class User
{
    public int id { get; set; }
    public string name { get; set; } = "";
    public string email { get; set; } = "";
    public bool active { get; set; } = true;
}

public class UserService
{
    private readonly List<User> _users = new()
    {
        new User { id = 1, name = "Kohl", email = "kohl@example.com", active = true },
        new User { id = 2, name = "Alice", email = "alice@example.com", active = true },
    };

    public User? get_by_id(int user_id)
    {
        return _users.FirstOrDefault(u => u.id == user_id);
    }

    public User create(string name, string email)
    {
        var user = new User
        {
            id = _users.Count + 1,
            name = name,
            email = email,
            active = true
        };
        _users.Add(user);
        return user;
    }

    public bool deactivate(int user_id)
    {
        var user = _users.FirstOrDefault(u => u.id == user_id);
        if (user == null) return false;
        user.active = false;
        return true;
    }
}

public class Calculator
{
    public int add(int a, int b) => a + b;
    public int multiply(int a, int b) => a * b;
}
