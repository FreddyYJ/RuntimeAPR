a=0.5
from slipcover.concolic import ConcolicTracer,get_zvalue
def inc():
    global a
    a=a+1.
    if a!=3.5:
        print(f'a: {a}')
    else:
        raise ValueError

for _ in range(5):
    inc()