import json
import os
import sys
from typing import Dict

def generate(node:dict,objects:dict,tried_ids:set=set()):
    if isinstance(node['value'],list):
        result=[]
        for elm in node['value']:
            if str(elm) in objects:
                if elm in tried_ids:
                    # result.append({
                    #     'type':objects[str(elm)]['type'],
                    #     'value':elm,
                    #     'cached':True
                    # })
                    pass
                else:
                    tried_ids.add(elm)
                    result.append(generate(objects[str(elm)],objects,tried_ids))
        return {
            'type':node['type'],
            'value':result
        }
    elif isinstance(node['value'],dict):
        result=dict()
        for key,value in node['value'].items():
            if str(value) in objects:
                if value in tried_ids:
                    v={
                        'type':objects[str(value)]['type'],
                        'value':0,
                        'cached':True
                    }
                else:
                    tried_ids.add(value)
                    v=generate(objects[str(value)],objects,tried_ids)
                result[key]=v
        return {
            'type':node['type'],
            'value':result
        }
    else:
        return {
            'type':node['type'],
            'value':node['value']
        }
    
def parse(buggy_file,fixed_file,target_func):
    print(f'Trying {buggy_file}')
    if not os.path.exists(buggy_file):
        print(f'{buggy_file} not found')
        return None,None,None,None,None,None
    with open(buggy_file,'r') as f:
        buggy:Dict[str,list] = json.load(f)
    with open(fixed_file,'r') as f:
        fixed = json.load(f)

    buggy_states=buggy['states']    
    fixed_states=fixed['states']

    buggy_pos_args=dict()
    for i,arg in enumerate(buggy_states['pos_args']):
        buggy_pos_args[i]=generate(buggy['objects'][str(arg)],buggy['objects'],set())
    fixed_pos_args=dict()
    for i,arg in enumerate(fixed_states['pos_args']):
        fixed_pos_args[i]=generate(fixed['objects'][str(arg)],fixed['objects'],set())

    buggy_kw_args=dict()
    for k,v in buggy_states['kw_args'].items():
        buggy_kw_args[k]=generate(buggy['objects'][str(v)],buggy['objects'],set())
    fixed_kw_args=dict()
    for k,v in fixed_states['kw_args'].items():
        fixed_kw_args[k]=generate(fixed['objects'][str(v)],fixed['objects'],set())
    
    buggy_global=dict()
    for k,v in buggy_states['globals'].items():
        buggy_global[k]=generate(buggy['objects'][str(v)],buggy['objects'],set())
    
    fixed_global=dict()
    for k,v in fixed_states['globals'].items():
        fixed_global[k]=generate(fixed['objects'][str(v)],fixed['objects'],set())
    
    return buggy_pos_args, buggy_kw_args, buggy_global, fixed_pos_args, fixed_kw_args, fixed_global
    
def compare(buggy_state,fixed_state,name:str,different:dict):
    if buggy_state['type']!=fixed_state['type']:
        if isinstance(buggy_state['value'],list):
            buggy_res={}
            for i in range(len(buggy_state['value'])):
                buggy_res[i]=buggy_state['value'][i]
        else:
            buggy_res=buggy_state['value']
        if isinstance(fixed_state['value'],list):
            fixed_res={}
            for i in range(len(fixed_state['value'])):
                fixed_res[i]=fixed_state['value'][i]
        else:
            fixed_res=fixed_state['value']
        different[name]=[buggy_res,fixed_res]
        return buggy_res,fixed_res
    elif isinstance(buggy_state['value'],list):
        buggy_res={}
        fixed_res={}
        index=0
        for buggy,fixed in zip(buggy_state['value'],fixed_state['value']):
            b,f=compare(buggy,fixed,f'{name}[{index}]',different)
            if b!={}:
                buggy_res[index]=b
            if f!={}:
                fixed_res[index]=f
            index+=1
        
        if len(buggy_state['value'])>len(fixed_state['value']):
            for i in range(len(fixed_state['value']),len(buggy_state['value'])):
                buggy_res[i]=buggy_state['value'][i]
                different[f'{name}.[{i}]']=[buggy_state['value'][i],{}]
        elif len(buggy_state['value'])<len(fixed_state['value']):
            for i in range(len(buggy_state['value']),len(fixed_state['value'])):
                fixed_res[i]=fixed_state['value'][i]
                different[f'{name}.[{i}]']=[{},fixed_state['value'][i]]
        return buggy_res,fixed_res
    elif isinstance(buggy_state['value'],dict) and isinstance(fixed_state['value'],dict):
        buggy_res={}
        fixed_res={}
        for key in buggy_state['value']:
            if key not in fixed_state['value']:
                buggy_res[key]=buggy_state['value'][key]
                different[f'{name}.{key}']=[buggy_state['value'][key],{}]
            else:
                b,f=compare(buggy_state['value'][key],fixed_state['value'][key],f'{name}.{key}',different)
                if b!={}:
                    buggy_res[key]=b
                if f!={}:
                    fixed_res[key]=f

        for key in fixed_state['value']:
            if key not in buggy_state['value']:
                fixed_res[key]=fixed_state['value'][key]
                different[f'{name}.{key}']=[{},fixed_state['value'][key]]
        return buggy_res,fixed_res
    else:
        if buggy_state['value']!=fixed_state['value']:
            different[name]=[buggy_state['value'],fixed_state['value']]
            return buggy_state['value'],fixed_state['value']
        else:
            return {},{}
    
def compare_states(buggy_state,fixed_state):
    result=dict()
    for k,v in buggy_state.items():
        if k not in fixed_state:
            result[k]=[v,{}]
            continue
        diffences=dict()
        b,f=compare(v,fixed_state[k],k,diffences)
        if b!={} or f!={}:
            result[k]=[b,f,]
    
    for k,v in fixed_state.items():
        if k not in buggy_state:
            result[k]=[{},v]
    return result

import benchmark

for id,info in benchmark.ANSIBLE_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/ansible/ansible-{id}/ansible/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/ansible/ansible-{id}/ansible/runtimeapr.json',
                                                                            f'benchmarks/ansible/ansible-{id}/ansible/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/ansible-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.BLACK_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/black/black-{id}/black/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/black/black-{id}/black/runtimeapr.json',
                                                                            f'benchmarks/black/black-{id}/black/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/black-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.FASTAPI_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/fastapi/fastapi-{id}/fastapi/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/fastapi/fastapi-{id}/fastapi/runtimeapr.json',
                                                                            f'benchmarks/fastapi/fastapi-{id}/fastapi/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/fastapi-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.LUIGI_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/luigi/luigi-{id}/luigi/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/luigi/luigi-{id}/luigi/runtimeapr.json',
                                                                            f'benchmarks/luigi/luigi-{id}/luigi/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/luigi-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1
        

for id,info in benchmark.PANDAS_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/pandas/pandas-{id}/pandas/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/pandas/pandas-{id}/pandas/runtimeapr.json',
                                                                            f'benchmarks/pandas/pandas-{id}/pandas/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/pandas-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.SCRAPY_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/scrapy/scrapy-{id}/scrapy/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/scrapy/scrapy-{id}/scrapy/runtimeapr.json',
                                                                            f'benchmarks/scrapy/scrapy-{id}/scrapy/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/scrapy-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.SPACY_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/spacy/spacy-{id}/spacy/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/spacy/spacy-{id}/spacy/runtimeapr.json',
                                                                            f'benchmarks/spacy/spacy-{id}/spacy/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/spacy-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.THEFUCK_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/thefuck/thefuck-{id}/thefuck/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/thefuck/thefuck-{id}/thefuck/runtimeapr.json',
                                                                            f'benchmarks/thefuck/thefuck-{id}/thefuck/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/thefuck-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.TORNADO_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/tornado/tornado-{id}/tornado/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/tornado/tornado-{id}/tornado/runtimeapr.json',
                                                                            f'benchmarks/tornado/tornado-{id}/tornado/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/tornado-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.TQDM_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/tqdm/tqdm-{id}/tqdm/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/tqdm/tqdm-{id}/tqdm/runtimeapr.json',
                                                                            f'benchmarks/tqdm/tqdm-{id}/tqdm/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/tqdm-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1

for id,info in benchmark.YOUTUBE_DL_LIST.items():
    i=0
    while os.path.exists(f'benchmarks/youtube-dl/youtube-dl-{id}/youtube-dl/entry-{i}.json'):
        buggy_pos,buggy_kw,buggy_global,fixed_pos,fixed_kw,fixed_global=parse(f'benchmarks/youtube-dl/youtube-dl-{id}/youtube-dl/runtimeapr.json',
                                                                            f'benchmarks/youtube-dl/youtube-dl-{id}/youtube-dl/entry-{i}.json',
                                                                            info[2])
        if buggy_pos is None: break
        with open(f'benchmarks/log/youtube-dl-{id}-states-{i}.log','w') as f:
            print('pos args: ',file=f)
            print(json.dumps(compare_states(buggy_pos,fixed_pos),indent=2),file=f)
            print('kw args: ',file=f)
            print(json.dumps(compare_states(buggy_kw,fixed_kw),indent=2),file=f)
            print('global args: ',file=f)
            print(json.dumps(compare_states(buggy_global,fixed_global),indent=2),file=f)
        i+=1