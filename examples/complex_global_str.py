my_str = "a string"


def f(n: int) -> str:
    global my_str
    for m in range(min(n, len(my_str))):
        my_str = my_str.replace(my_str[m], my_str[-m])
    my_str += chr(n + 97)
    print(my_str.count(max(my_str)), len(my_str) / 2)
    n += 1
    if max([my_str.count(i) for i in my_str]) > len(my_str) / 2:
        raise ValueError
    return my_str


from runtimeapr.loop import except_handler

for _n in range(10):
    try:
        print(f(_n))
    except Exception as _e:
        except_handler(_e)
