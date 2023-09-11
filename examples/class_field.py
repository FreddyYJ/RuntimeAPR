class A:
    def __init__(self) -> None:
        self.a=0

def inc(a):
    a.a+=1
    if a.a==3:
        raise ValueError
    else:
        print(f'a: {a.a}')

a=A()
for i in range(5):
    inc(a)