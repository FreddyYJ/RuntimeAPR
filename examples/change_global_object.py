class Foo:
    def __init__(self,v:int) -> None:
        self.value=v
    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, Foo):
            return self.value==__value.value
        else:
            return False
    def __add__(self, __value: object) -> object:
        if isinstance(__value, Foo):
            return Foo(self.value+__value.value)
        else:
            return Foo(self.value+__value)
    def __str__(self) -> str:
        return str(self.value)
        
a=Foo(0)

def inc():
    # a+=1
    global a
    a=a+Foo(1)
    if a==Foo(3):
        raise ValueError
    else:
        print(f'a: {a}')

for _ in range(5):
    inc()
