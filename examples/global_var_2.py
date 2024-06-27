my_int = 187254365


def f(n: int) -> int:
    global my_int
    my_int *= my_int
    if n % 2 == 0:
        raise ValueError
    return my_int

print(f(6))