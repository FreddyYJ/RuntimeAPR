"""
    Example to check symbolic execution. 

    expected output:
        In main: 0
        In foo: 1
        In main: 1
        In foo: 2
        In main: 2
        ...
        In foo: 5
        In main: 5

    acutal error:
        ValueError in line 24 from line 35 (when i == 3)
"""

my_global = 0

def foo(a):
    global my_global
    my_global += 1
    if my_global==4:
        print('my_global==4')
        if a==3:
            raise ValueError('A should not be a 3')
        elif a<3:
            print('a<3')
        elif a>3:
            print('a>3')
    else:
        print('my_global!=4')
        if a<=3:
            print('a<=3')
        elif a>3:
            print('a>3')

    print(f'In foo: {my_global}')

if __name__ == '__main__':
    for i in range(5):
        print(f'In main: {my_global}')
        foo(i)
    print(f'In main: {my_global}')