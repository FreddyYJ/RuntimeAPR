a=0

def temp(a):
    return a!=3

def inc(b):
    global a
    a=a+1
    if temp(a):
        print(f'a: {a}')
    else:
        raise ValueError

# import atheris

# print(bytes(a))
# atheris.instrument_func(inc)

for _ in range(5):
    # try:
        inc(a)
    # except Exception as e:
    #     from slipcover.loop import except_handler
    #     except_handler(e)

# def CustomMutator(data,max_size,seed):
#     print(f'Mutate: {data}')
#     print(f'max size: {max_size}')
#     print(f'seed: {seed}')
#     new_input=atheris.Mutate(data,max_size,seed)
#     print(f'Mutated input: {new_input}')
#     return new_input

# atheris.Setup([bytes(a)],inc,custom_mutator=CustomMutator)
# atheris.Fuzz()