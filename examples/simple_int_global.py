my_int = 2


class Tmp:
    def __init__(self, n):
        self.n = n


def f(n: Tmp) -> int:
    global my_int
    my_int *= my_int
    n.n += 1
    if n.n % 2 == 0:
        raise ValueError
    return my_int


from runtimeapr.loop import except_handler

try:
    print(f(Tmp(5)))
except Exception as _e:
    except_handler(_e)
