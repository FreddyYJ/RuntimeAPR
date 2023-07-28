def inc(a:int):
    # a+=1
    a=a+1
    if a==3:
        raise ValueError
    else:
        return a

a=0
for _ in range(5):
    a=inc(a)
