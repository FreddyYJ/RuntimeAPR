# Axolotl

## Installation
Please install criu version `3.17.1`. The latest are not always supported by Ubuntu. One may need to clone [criu repository](https://github.com/checkpoint-restore/criu) and run `git checkout  d46f40f` to achieve this.

To install it completly, one may run `export PATH="$(pwd)/axolotl:$PATH"` or add this command to their `~/.bashrc` file and source it.

It is also asked to install the runtimeapr module with `python -m pip install .` once at the folder location. Read more about the possible issues [here](#problems)
## Usage
Here is the basic information on how to run axolotl script:
```
Syntax: sudo axolotl [ OPTIONS ] script_to_run.py
With OPTION among the following:
    -[h?] | --help
        Show this message.
    -v | --verbose
        Print additional information.
    -d | --docker
        Run it on docker rather than on a process.
    -l | --log <file.log>
        File for the logs. Will be moved to <working-dir>/<file.log> if set.
    -n | --normal-run
        Run the program without any additional work (simple interpretor call)
    -D | --working-dir <path/to/dir>
        The directory in which the images and additional files will be saved. Absolute or relative work.
    -m | --max-saves <n>
        The maximal number of backup stored. Default -1 represents an infinite amount.
```

For example, if one want to run a (possibly faulty) python code called `src/my_folder/my_faulty_code.py`, they can simply run:
```
sudo axolotl src/my_folder/my_faulty_code.py
```
The root permissions are necessary to run `criu`, if one is interested in running their program without the restoration phase they may use `axolotl --normal-run src/my_folder/my_faulty_code.py`. It will run the simple python interpreter.

## Overview
The `--docker` option is still experimental so far, it will not be descussed below but follow the same principles as the CRIU restoration process.

The default parameters enable the program reparation. Here is how the framework works under the hood. 

- Run the code in parallel on a different process of PID `_pid`.
- Every `SLEEP` seconds, look if the process is still working (is likely to be changed to a `wait $_pid` to improve performances)
    - if the process is still running, take a "screenshot" of the state of the shell. This is done using [CRIU](https://github.com/checkpoint-restore/criu) and more specifically the command `criu dump`. We used the `--leave-running` argument not to stop the process and `--prev-images-dir` to save the data incrementally (i.e. we only save the changes compared with the last checkpoint to allow us to go further back in time).
    - if the process is stoped with an error message, restore the last checkpoint (may be improved to adapt to the time of the last function call). This is done using the `criu restore` command. The argument `--action-script` is given to post-process the code and [repair](#repair) it before starting it again.

### Repair


### Problems

- To run the repair part, it is asked to have python version 3.8. It can be changed using an environment like `python -m venv env` or `conda create -n "env" python=3.8.19`. 
- One may have noticed the use of the keyword `python` all along. It is also used inside the code and should be defined upstram. It can be set by running `sudo cp "$(which python3)" /usr/bin/python` or `sudo apt-get install python-is-python3` (probably safer).
- Set properly `OPENAI_API_KEY`
- The most important one: the restored program is ran erasing the changes. To correct that one may change the `PYTHON` variable for `PYTHON="python -m runtimeapr"`, add a switch of the form `if os.environ.get('SWITCH') == 'V1'` and modify the `SWITCH` variable in `./action_script.sh`. 
- There may also be an issue with the obtained pid. Look at `--pidfile` to get a possibly changing pid.


