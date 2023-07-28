"""
    This example shows unexpected behavior of pickle.

    Pickle cannot handle if different variables reference same object.

    IDs of member after 'Program running' is same and both of A.value is changed to 1.
    However, after 'Crash is fixed' IDs of member is different.
    Moreover, A.value of b2 is changed to 0 after 'Continue Program' but A.value of b1 is not changed.
"""
import gc
import pickle

class A:
    def __init__(self) -> None:
        self.value=0

class B:
    def __init__(self,a=None) -> None:
        self.a=a

def foo():
    a=A()
    b1=B(a)
    b2=B(a)
    print(f'ID: {id(b1)}, {id(b2)}')
    print(f'ID of member: {id(b1.a)}, {id(b2.a)}')
    print(f'Value of A.a: {b1.a.value}, {b2.a.value}\n')

    print('Program running')
    b2.a.value=1
    print(f'ID: {id(b1)}, {id(b2)}')
    print(f'ID of member: {id(b1.a)}, {id(b2.a)}')
    print(f'Value of A.a: {b1.a.value}, {b2.a.value}')

    # Assumes a crash is occured
    print('\nCrash occurs, save heap!')
    gc.collect()
    b1_pkl=pickle.dumps(b1)
    b2_pkl=pickle.dumps(b2)
    
    # Assumes a crash is fixed
    print('Crash is fixed, load heap!\n')
    b1=pickle.loads(b1_pkl)
    b2=pickle.loads(b2_pkl)
    print(f'ID: {id(b1)}, {id(b2)}')
    print(f'ID of member: {id(b1.a)}, {id(b2.a)}')
    print(f'Value of A.a: {b1.a.value}, {b2.a.value}\n')

    # Continue program
    print('Continue program\n')
    b2.a.value=0
    print(f'ID: {id(b1)}, {id(b2)}')
    print(f'ID of member: {id(b1.a)}, {id(b2.a)}')
    print(f'Value of A.a: {b1.a.value}, {b2.a.value}')

if __name__ == '__main__':
    foo()