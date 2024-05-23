a = 0


def inc():
    # a+=1
    global a
    a = a + 1
    res = a / 0 if a == 3 else a
    print(f'a: {a}')


for _ in range(5):
    inc()
