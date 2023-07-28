class A:
    def __init__(self) -> None:
        self.a=0

    def inc(self):
        # a+=1
        self.a=self.a+1
        if self.a==3:
            raise ValueError
        else:
            print(f'a: {self.a}')

a=A()
for _ in range(5):
    a.inc()
