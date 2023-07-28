ITERATION=18000000000

from time import sleep,time
timer=0.

def inc(a):
    if a%(ITERATION/100)==0:
        # print(f'a: {a}')
        pass

for i in range(ITERATION):
    # t0=time()
    inc(i)
    # timer+=time()-t0

# print(f'timer: {timer}')