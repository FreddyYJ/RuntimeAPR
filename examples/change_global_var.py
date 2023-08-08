# from slipcover.jurigged.loop import except_handler

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
    return a,b

for _ in range(5):
    # try:
        inc(a)
    # except Exception as e:
    #     except_handler(e)