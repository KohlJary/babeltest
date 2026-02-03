namespace example;

/// <summary>
/// Example math utilities - unified target: example.math
/// </summary>
public static class math
{
    public static int add(int a, int b) => a + b;

    public static int subtract(int a, int b) => a - b;

    public static double divide(double a, double b)
    {
        if (b == 0)
            throw new ArgumentException("divide by zero");
        return a / b;
    }

    public static bool is_even(int n) => n % 2 == 0;
}
