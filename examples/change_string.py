a=''

def inc():
    # a+=1
    global a
    a=a+'a'
    if a=='aaa':
        raise ValueError
    else:
        print(f'str: {a}')

for _ in range(5):
    inc()
