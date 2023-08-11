a=[0,0,0,0,0]
i=0

def inc(b):
    global a
    a[b]=b
    if a[2]!=2:
        print(f'a: {a}')
    else:
        raise ValueError

while i<5:
    inc(i)
    i+=1