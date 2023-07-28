def inc(b):
    for i in range(b):
        if i==3:
            raise ValueError
        else:
            print(f'b: {b}')

inc(5)
