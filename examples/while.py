a=0

def inc():
    # a+=1
    global a
    while a<=4:
        a=a+1
        if a==3:
            raise ValueError
        else:
            print(f'a: {a}')

inc()
