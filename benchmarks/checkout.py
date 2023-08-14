import subprocess
import os

def checkout(subject:str,version:int):
    print(f'Checking out {subject}-{version}')
    if not os.path.exists(f'/root/project/RuntimeAPR/benchmarks/{subject}'):
        os.mkdir(f'/root/project/RuntimeAPR/benchmarks/{subject}')

    result=subprocess.run(['bugsinpy-checkout','-p',subject,'-i',str(version),'-v','0',
                           '-w',f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}'],
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    
    # Store the output in the checkout.log file
    with open(f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}/{subject}/checkout.log','w') as f:
        f.write(result.stdout.decode())

    if result.returncode!=0:
        print(f'{subject}-{version} checkout returns {result.returncode}')
    else:
        print(f'{subject}-{version} checkout success!')

import benchmark

for sub in benchmark.SUBJECTS:
    for i in range(1,benchmark.BUGS_NUMBER[sub]+1):
        checkout(sub,i)