import subprocess
import os

def diff(subject:str,version:int):
    print(f'Diffing {subject}-{version}f')
    result=subprocess.run(["git","diff"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          cwd=f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f/{subject}')
    
    if result.returncode!=0:
        print(result.stdout.decode('utf-8'))
        print(f'Error in diffing {subject}-{version}f')
        exit(result.returncode)
    else:
        print(f'Diffed {subject}-{version}f!')
        if not os.path.exists(f'/root/project/RuntimeAPR/benchmarks/diffs/{subject}'):
            os.mkdir(f'/root/project/RuntimeAPR/benchmarks/diffs/{subject}')
        with open(f'/root/project/RuntimeAPR/benchmarks/diffs/{subject}/{subject}-{version}.diff','w') as f:
            f.write(result.stdout.decode('utf-8'))

import benchmark
import multiprocessing as mp

pool=mp.Pool(30)

for sub in benchmark.SUBJECTS:
    for i in range(1,benchmark.BUGS_NUMBER[sub]+1):
        if (sub,i) not in benchmark.EXCEPT_BUGS:
            pool.apply_async(diff,args=(sub,i))

pool.close()
pool.join()