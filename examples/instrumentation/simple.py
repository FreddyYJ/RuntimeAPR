a =0

def foo(b):
    global a
    a+=1
    if a==5:
        raise Exception('a==5')
    print(a)
    return a,b

for i in range(10):
# try:
    foo(4)
# except Exception as e:
#     print(e)
