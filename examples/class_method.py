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
    
    def __str__(self) -> str:
        return f'{self.a}'

from slipcover.jurigged.loop import except_handler

a=A()
for _ in range(5):
    try:
        a.inc()
    except Exception as e:
        except_handler(e)