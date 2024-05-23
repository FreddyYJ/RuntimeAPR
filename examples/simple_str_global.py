my_str = "a string "


def f(n: int) -> str:
    global my_str
    my_str = my_str + my_str
    if n % 2 == 0:
        raise ValueError
    return my_str


from runtimeapr.loop import except_handler

try:
    print(f(6))
except Exception as _e:
    except_handler(_e)
