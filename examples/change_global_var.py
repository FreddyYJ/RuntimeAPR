a=0

def inc(b):
    global a
    a=a+1
    if a<3:
        print(f'a: {a}')
    else:
        raise ValueError

for _ in range(5):
    inc(a)
