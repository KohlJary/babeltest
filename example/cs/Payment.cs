namespace example.payment;

/// <summary>
/// Payment services for mock testing.
/// Uses interfaces to enable mocking via dependency injection.
/// </summary>

public class PaymentDeclined : Exception
{
    public PaymentDeclined(string message = "Payment declined") : base(message) { }
}

public interface IPaymentGateway
{
    Dictionary<string, object> Charge(double amount, string cardToken);
}

public class PaymentGateway : IPaymentGateway
{
    public Dictionary<string, object> Charge(double amount, string cardToken)
    {
        // This would normally call Stripe/etc
        throw new NotImplementedException("Real PaymentGateway should be mocked in tests");
    }
}

public class Order
{
    public int id { get; set; }
    public string status { get; set; } = "";
    public double total { get; set; }
}

public class OrderService
{
    private readonly IPaymentGateway _paymentGateway;
    private int _nextId = 1000;

    public OrderService() : this(new PaymentGateway()) { }

    public OrderService(IPaymentGateway paymentGateway)
    {
        _paymentGateway = paymentGateway;
    }

    public Order place_order(int user_id, double amount, string card_token)
    {
        try
        {
            _paymentGateway.Charge(amount, card_token);
            return new Order { id = _nextId++, status = "placed", total = amount };
        }
        catch (PaymentDeclined)
        {
            return new Order { id = 0, status = "declined", total = amount };
        }
        catch (Exception)
        {
            return new Order { id = 0, status = "error", total = amount };
        }
    }
}
