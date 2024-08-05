#!/bin/bash

# [ "$CRTOOLS_SCRIPT_ACTION" == "post-restore" ] || exit 0

# Check the stage of the process
case "$CRTOOLS_SCRIPT_ACTION" in
    pre-dump)
        echo Hello
        ;;
    post-dump)
        echo World
        ;;
    pre-restore)
        echo Rising
        sudo mkdir /tmp 2>/dev/null
        cp /home/fred/ENS/Stage/M1/RuntimeAPR/test.py /tmp/axolotl_tmp_program.py
        ;;
    post-restore)
        echo "Running post-restore actions"
        mv /tmp/axolotl_tmp_program.py /home/fred/ENS/Stage/M1/RuntimeAPR/test.py
        ;;
esac

