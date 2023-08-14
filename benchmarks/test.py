import subprocess

def test(subject:str,version:str):
    print(f'Compiling {subject}-{version}')
    result=subprocess.run(['bugsinpy-compile'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          cwd=f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}/{subject}')
    
    # Store the output in the compile.log file
    with open(f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}/{subject}/compile.log','w') as f:
        f.write(result.stdout.decode())

    if result.returncode!=0:
        print(f'{subject}-{version} compile returns {result.returncode}')
    else:
        print(f'{subject}-{version} compile success, running tests')

    # Run tests
    result=subprocess.run(['bugsinpy-test'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          cwd=f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}/{subject}')
    
    # Store the output in the test.log file
    with open(f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}/{subject}/test.log','w') as f:
        f.write(result.stdout.decode())

    if result.returncode!=0:
        print(f'{subject}-{version} test returns {result.returncode}')
        return False
    else:
        print(f'{subject}-{version} test success!')
        return True
    
def test_fixed(subject:str,version:str):
    print(f'Compiling {subject}-{version}f')
    result=subprocess.run(['bugsinpy-compile'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          cwd=f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f/{subject}')
    
    # Store the output in the compile.log file
    with open(f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f/{subject}/compile.log','w') as f:
        f.write(result.stdout.decode())

    if result.returncode!=0:
        print(f'{subject}-{version}f compile returns {result.returncode}')
    else:
        print(f'{subject}-{version}f compile success, running tests')

    # Run tests
    result=subprocess.run(['bugsinpy-test'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          cwd=f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f/{subject}')
    
    # Store the output in the test.log file
    with open(f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f/{subject}/test.log','w') as f:
        f.write(result.stdout.decode())

    if result.returncode!=0:
        print(f'{subject}-{version}f test returns {result.returncode}')
        return False
    else:
        print(f'{subject}-{version}f test success!')
        return True


import benchmark

for sub in benchmark.SUBJECTS:
    for i in range(1,benchmark.BUGS_NUMBER[sub]+1):
        if (sub,i) not in benchmark.EXCEPT_BUGS:
            test_fixed(sub,i)