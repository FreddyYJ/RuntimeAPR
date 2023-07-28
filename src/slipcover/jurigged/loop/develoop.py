import collections
import ctypes
import dataclasses
import gc
import linecache
import pickle
import pickletools
import sys
import threading
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from queue import Queue
import inspect
from types import FunctionType

from executing import Source
from giving import SourceProxy, give, given
from hrepr import pstr

from ..register import registry
from .repairutils import BugInformation


@registry.activity.append
def _(evt):
    # Patch to ensure the executing module's cache is invalidated whenever
    # a source file is changed.
    cache = Source._class_local("__source_cache", {})
    filename = evt.codefile.filename
    if filename in cache:
        del cache[filename]
    linecache.checkcache(filename)


@give.variant
def givex(data):
    return {f"#{k}": v for k, v in data.items()}


def itemsetter(coll, key):
    def setter(value):
        coll[key] = value

    return setter


def itemappender(coll, key):
    def appender(value):
        coll[key] += value

    return appender


class FileGiver:
    def __init__(self, name):
        self.name = name

    def write(self, x):
        give(**{self.name: x})

    def flush(self):
        pass


class Abort(Exception):
    pass


def kill_thread(thread, exctype=Abort):
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread.ident), ctypes.py_object(exctype)
    )


@contextmanager
def watching_changes():
    src = SourceProxy()
    registry.activity.append(src._push)
    try:
        yield src
    finally:
        registry.activity.remove(src._push)


class DeveloopRunner:
    def __init__(self, fn, args, kwargs):
        self.fn:FunctionType = fn
        self.args = args
        self.kwargs = kwargs
        self.num = 0
        self._q = Queue()

    def setcommand(self, cmd):
        while not self._q.empty():
            self._q.get()
        self._q.put(cmd)

    def command(self, name, aborts=False):
        def perform(_=None):
            if aborts:
                # Asynchronously sends the Abort exception to the
                # thread in which the function runs.
                kill_thread(self._loop_thread)
            self.setcommand(name)

        return perform

    def signature(self):
        name = getattr(self.fn, "__qualname__", str(self.fn))
        parts = [pstr(arg, max_depth=0) for arg in self.args]
        parts += [f"{k}={pstr(v, max_depth=0)}" for k, v in self.kwargs.items()]
        args = ", ".join(parts)
        return f"{name}({args})"

    @contextmanager
    def wrap_loop(self):
        yield

    @contextmanager
    def wrap_run(self):
        yield

    def register_updates(self, gv):
        raise NotImplementedError()

    def run(self):
        self.num += 1
        outcome = [None, None]  # [result, error]
        with given() as gv, self.wrap_run():
            t0 = time.time()
            gv["?#result"] >> itemsetter(outcome, 0)
            gv["?#error"] >> itemsetter(outcome, 1)
            self.register_updates(gv)
            try:
                givex(result=self.fn(*self.args, **self.kwargs), status="done")
            except Abort:
                givex(status="aborted")
                raise
            except Exception as error:
                givex(error, status="error")
            givex(walltime=time.time() - t0)
        return outcome

    def loop(self, from_error=None):
        self._loop_thread = threading.current_thread()
        result = None
        err = None

        if from_error:
            self.setcommand("from_error")
        else:
            self.setcommand("go")

        with self.wrap_loop(), watching_changes() as chgs:
            # Rerun once if the source changes
            chgs.debounce(0.05) >> self.command("go", aborts=True)

            while True:
                try:
                    cmd = self._q.get()
                    # (r)erun
                    if cmd == "go":
                        result, err = self.run()
                    # (c)ontinue
                    elif cmd == "cont":
                        break
                    # (a)bort
                    elif cmd == "abort":
                        pass
                    # (q)uit
                    elif cmd == "quit":
                        sys.exit(1)
                    elif cmd == "from_error":
                        with given() as gv:
                            self.register_updates(gv)
                            givex(error=from_error, status="error")
                        result, err = None, from_error

                except Abort:
                    continue

        if err is not None:
            raise err
        else:
            return result

class RedirectDeveloopRunner(DeveloopRunner):
    @contextmanager
    def wrap_run(self):
        out = FileGiver("#stdout")
        err = FileGiver("#stderr")

        with redirect_stdout(out), redirect_stderr(err):
            yield

from ..concolic import ConcolicTracer,get_zvalue,zint
import z3
from jurigged.loop.repairutils import prune_default_global_var
import copy

class Develoop:
    def __init__(self, fn, on_error, runner_class):
        self.fn:FunctionType = fn
        self.on_error = on_error
        self.runner_class = runner_class
        self.buggy_memory=b''
        self.orig_frame=None

    def __get__(self, obj, cls):
        return type(self)(
            self.fn.__get__(obj, cls),
            on_error=self.on_error,
            runner_class=self.runner_class,
        )

    def __call__(self, *args, **kwargs):
        exc = None
        if self.on_error:                
            try:
                # result= tracer[self.fn](*new_args, **kwargs)
                result=self.fn(*args, **kwargs)
            except Exception as _exc:
                exc = _exc
                print(f'Exception: {exc}')
                tb=exc.__traceback__
                info=inspect.getinnerframes(tb)[1]
                buggy_info=BugInformation(buggy_line=info.lineno,buggy_func=info.function,buggy_args_values=dict(),buggy_global_values=dict())
                buggy_info.local_vars=info.frame.f_locals
                buggy_info.global_vars=info.frame.f_globals

                # FIXME: Handle non-RepairLoop
                return self.runner_class(self.fn, args, kwargs,buggy_info).loop(from_error=exc)
        
            return result
        
        return self.runner_class(self.fn, args, kwargs,buggy_info).loop(from_error=exc)