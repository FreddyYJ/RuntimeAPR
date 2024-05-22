my_int = 187254365


def f(n: int) -> int:
    global my_int
    my_int *= my_int
    if n % 2 == 0:
        raise ValueError
    return my_int


from runtimeapr.loop import except_handler

try:
    print(f(6))
except Exception as _e:
    except_handler(_e)