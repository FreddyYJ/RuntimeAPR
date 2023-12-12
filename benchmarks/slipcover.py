import subprocess
import os
import benchmark

from copy import copy

def run(subject:str,id:int,info):
    if len(info)==0: return
    print(f'Running {subject}-{id}')

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

    env=copy(os.environ)
    env['FUNC_NAME']=info[2].split('.')[-1]
    with open('runtime-apr.log','w') as f:
        # result=subprocess.run(f'bash -c "source env/bin/activate && python -m pip install ../../../.. && deactivate"',
        #             shell=True,stdout=f,stderr=f)
        # if result.returncode!=0:
        #     print(f'Failed to install runtimeapr for {subject}-{id}')
        #     return
        
        if benchmark.TEST_TOOLS[subject]=='pytest':
            result=subprocess.run(f'bash -c "source env/bin/activate && python -m slipcover --source {info[0]} -m pytest {info[1]} -s && deactivate"',
                                stdout=f,stderr=f,shell=True,env=env)
        else:
            result=subprocess.run(f'bash -c "source env/bin/activate && python -m slipcover --source {info[0]} -m unittest {info[1]} -q && deactivate"',
                                stdout=f,stderr=f,shell=True,env=env)

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