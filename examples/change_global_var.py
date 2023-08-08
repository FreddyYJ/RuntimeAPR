# from slipcover.jurigged.loop import Develoop
a=0

def temp(a):
    return a!=3

def inc(b):
    # a+=1
    global a
    a=a+1
    if temp(a):
        print(f'a: {a}')
    else:
        raise ValueError
    return a,b

for _ in range(5):
    try:
        inc(a)
    except Exception as e:
        import inspect
        info:inspect.FrameInfo=inspect.getinnerframes(e.__traceback__)[1]
        f=info.frame