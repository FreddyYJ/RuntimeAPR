import subprocess
import os
import benchmark

from copy import copy

def checkout(subject:str,version:int):
    print(f'Checking out {subject}-{version}')
    if not os.path.exists(f'/root/project/RuntimeAPR/benchmarks/{subject}'):
        os.mkdir(f'/root/project/RuntimeAPR/benchmarks/{subject}')

    if os.path.exists(f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}'):
        subprocess.run(['rm','-rf',f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}'])
    if os.path.exists(f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f'):
        subprocess.run(['rm','-rf',f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f'])
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

def checkout_fixed(subject:str,version:int):
    print(f'Checking out {subject}-{version}f')
    if not os.path.exists(f'/root/project/RuntimeAPR/benchmarks/{subject}'):
        os.mkdir(f'/root/project/RuntimeAPR/benchmarks/{subject}')

    result=subprocess.run(['bugsinpy-checkout','-p',subject,'-i',str(version),'-v','1',
                           '-w',f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f'],
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    
    # Store the output in the checkout.log file
    with open(f'/root/project/RuntimeAPR/benchmarks/{subject}/{subject}-{version}f/{subject}/checkout.log','w') as f:
        f.write(result.stdout.decode())

    if result.returncode!=0:
        print(f'{subject}-{version}f checkout returns {result.returncode}')
    else:
        print(f'{subject}-{version}f checkout success!')

def run(subject:str,id:int,info):
    if len(info)==0: return
    print(f'Running {subject}-{id}')
    # subprocess.run(['rm','-rf',f'{subject}/{subject}-{id}'])
    # subprocess.run(['rm','-rf',f'{subject}/{subject}-{id}f'])
    # checkout(subject,id)
    # checkout_fixed(subject,id)

    orig_dir=os.getcwd()
    os.chdir(f'{subject}/{subject}-{id}/{subject}')

    if benchmark.TEST_TOOLS[subject]=='pytest':
        test_file=info[1].split('::')[0]
    else:
        test_file='/'.join(info[1].split('.')[:-2])+'.py'

    if os.path.exists(f'{info[0]}.orig'):
        r=subprocess.run(['mv',f'{info[0]}.orig',info[0]])
    if os.path.exists(f'{test_file}.orig'):
        r=subprocess.run(['mv',f'{test_file}.orig',test_file])

    build_env=copy(os.environ)
    build_env['OUTPUT_LOG']='dynapyt-build.log'
    # r=subprocess.run(['bugsinpy-compile'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    # if r.returncode!=0:
    #     print(f'Fail to compile {subject}-{id}')

    r=subprocess.run(f'bash -c "source env/bin/activate && python -m pip install -r ../../../../../DynaPyt/requirements.txt && deactivate"',
                    shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=build_env)
    r=subprocess.run(f'bash -c "source env/bin/activate && python -m pip install ../../../../../DynaPyt && deactivate"',
                    shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=build_env)
    with open('dynapyt_build_output.log','w') as f:
        f.write(f'bash -c "source env/bin/activate && python -m dynapyt.instrument.instrument '
                            f'--file {info[0]} {test_file} --analysis dynapyt.analyses.FunctionStates.FunctionStates"\n')
        f.flush()
        result=subprocess.run(f'bash -c "source env/bin/activate && python -m dynapyt.instrument.instrument '
                            f'--file {info[0]} {test_file} --analysis dynapyt.analyses.FunctionStates.FunctionStates"',
                            stdout=f,stderr=f,shell=True,env=build_env)
        if result.returncode!=0:
            print(f'Failed to instrument {subject}-{id}')

    env=copy(os.environ)
    env['OUTPUT_LOG']='dynapyt.log'
    env['OUTPUT_JSON']='dynapyt.json'
    # with open('fail_test.log','w') as f:
    with open('dynapyt-test.log','w') as f:
        if benchmark.TEST_TOOLS[subject]=='pytest':
            # result=subprocess.run(f'bash -c "source env/bin/activate && python -m pytest {info[1]} -s && deactivate"',
            #                       stdout=f,stderr=f,shell=True)
            f.write(f'bash -c "source env/bin/activate && python -m dynapyt.run_analysis '
                                    f'--entry \'pytest {info[1]} -s\' '
                                    f'--analysis dynapyt.analyses.FunctionStates.FunctionStates && deactivate"\n')
            f.flush()
            result=subprocess.run(f'bash -c "source env/bin/activate && python -m dynapyt.run_analysis '
                                    f'--entry \'pytest {info[1]} -s\' '+
                                    f'--analysis dynapyt.analyses.FunctionStates.FunctionStates && deactivate"',
                                    stdout=f,stderr=f,shell=True,env=env)
        else:
            # result=subprocess.run(f'bash -c "source env/bin/activate && python -m unittest {info[1]} -q && deactivate"',
            #                       stdout=f,stderr=f,shell=True)
            f.write(f'bash -c "source env/bin/activate && python -m dynapyt.run_analysis '
                                    f'--entry \'python -m unittest {info[1]} -q\' '
                                    f'--analysis dynapyt.analyses.FunctionStates.FunctionStates && deactivate\n')
            f.flush()
            result=subprocess.run(f'bash -c "source env/bin/activate && python -m dynapyt.run_analysis '
                                    f'--entry \'python -m unittest {info[1]} -q\' '
                                    f'--analysis dynapyt.analyses.FunctionStates.FunctionStates && deactivate"',
                                    stdout=f,stderr=f,shell=True,env=env)
    r=subprocess.run(['mv',f'{info[0]}.orig',info[0]])
    r=subprocess.run(['mv',f'{test_file}.orig',test_file])
    
    # if benchmark.TEST_TOOLS[subject]=='pytest':
    #     result=subprocess.run(f'bash -c "source env/bin/activate && python -m slipcover --source {info[0]} -m pytest {info[1]} -s && deactivate"',
    #                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=True)
    # else:
    #     result=subprocess.run(f'bash -c "source env/bin/activate && python -m slipcover --source {info[0]} -m unittest {info[1]} -q && deactivate"',
    #                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=True)

    os.chdir(orig_dir)
    
    print(f'Finished {subject}-{id} with {result.returncode}')    

import multiprocessing as mp

pool=mp.Pool(20)

for id,info in benchmark.ANSIBLE_LIST.items():
    pool.apply_async(run,('ansible',id,info,))
for id,info in benchmark.BLACK_LIST.items():
    pool.apply_async(run,('black',id,info,))
for id,info in benchmark.FASTAPI_LIST.items():
    pool.apply_async(run,('fastapi',id,info,))
for id,info in benchmark.LUIGI_LIST.items():
    pool.apply_async(run,('luigi',id,info,))
for id,info in benchmark.PANDAS_LIST.items():
    pool.apply_async(run,('pandas',id,info,))
for id,info in benchmark.SCRAPY_LIST.items():
    pool.apply_async(run,('scrapy',id,info,))
for id,info in benchmark.SPACY_LIST.items():
    pool.apply_async(run,('spacy',id,info,))
for id,info in benchmark.THEFUCK_LIST.items():
    pool.apply_async(run,('thefuck',id,info,))
for id,info in benchmark.TORNADO_LIST.items():
    pool.apply_async(run,('tornado',id,info,))
for id,info in benchmark.TQDM_LIST.items():
    pool.apply_async(run,('tqdm',id,info,))
for id,info in benchmark.YOUTUBE_DL_LIST.items():
    pool.apply_async(run,('youtube-dl',id,info,))

pool.close()
pool.join()