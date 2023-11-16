a=0

def temp(a):
    return a!=3

def inc(b):
    global a
    a=a+1
    if temp(a):
        print(f'a: {a}')
    else:
        raise ValueError

for _ in range(5):
    inc(a)
