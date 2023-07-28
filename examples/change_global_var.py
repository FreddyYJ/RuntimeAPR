# from slipcover.jurigged.loop import Develoop
a=0

def inc():
    # a+=1
    global a
    a=a+1
    if a==3:
        raise ValueError
    else:
        print(f'a: {a}')

for _ in range(5):
    inc()
