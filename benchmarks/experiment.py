import subprocess
import os
import benchmark

def run(subject:str):
    for id,info in benchmark.__dict__[subject.upper().replace('-','_')+'_LIST'].items():
        if len(info)==0: continue
        print(f'Running {subject}-{id}')
        orig_dir=os.getcwd()
        os.chdir(f'{subject}/{subject}-{id}/{subject}')

        r=subprocess.run(f'bash -c "source env/bin/activate && python -m pip install ../../../.. && deactivate"',
                        shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        
        if benchmark.TEST_TOOLS[subject]=='pytest':
            result=subprocess.run(f'bash -c "source env/bin/activate && python -m slipcover --source {info[0]} -m pytest {info[1]} -s && deactivate"',
                                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=True)
        else:
            result=subprocess.run(f'bash -c "source env/bin/activate && python -m slipcover --source {info[0]} -m unittest {info[1]} -q && deactivate"',
                                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=True)

        os.chdir(orig_dir)
        with open(f'log/{subject}-{id}.log','w') as f:
            f.write(result.stdout.decode('utf-8'))
        
        print(f'Finished {subject}-{id} with {result.returncode}')

run('ansible')
run('black')
run('fastapi')
run('luigi')
run('pandas')
run('scrapy')
run('spacy')
run('thefuck')
run('tornado')
run('tqdm')
run('youtube-dl')