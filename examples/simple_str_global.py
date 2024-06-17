my_str = "a string "


def f(n: int) -> str:
    global my_str
    my_str = my_str + my_str
    if n % 2 == 0:
        raise ValueError
    return my_str

print(f(6))
