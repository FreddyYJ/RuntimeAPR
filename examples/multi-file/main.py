from oper import add, sub, mult, div

def main():
    a=10
    b=2
    print(f'a: {a}, b: {b}, result: {add(a,b)}')
    print(f'a: {a}, b: {b}, result: {sub(a,b)}')

    a=20
    b=0
    print(f'a: {a}, b: {b}, result: {mult(a,b)}')
    print(f'a: {a}, b: {b}, result: {div(a,b)}')

    a=10
    b=3
    print(f'a: {a}, b: {b}, result: {sub(a,b)}')
    print(f'a: {a}, b: {b}, result: {div(a,b)}')

main()