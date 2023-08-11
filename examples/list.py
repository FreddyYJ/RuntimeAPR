a=[0,0,0,0,0]
i=-1

def inc():
    global a,i
    i+=1
    a[i]=i
    if a[2]!=2:
        print(f'a: {a}')
    else:
        raise ValueError

while i<4:
    inc()