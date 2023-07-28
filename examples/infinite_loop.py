from time import sleep

def foo(i):
    print(i)
    sleep(3)

i=0
while True:
    foo(i)
    i+=1