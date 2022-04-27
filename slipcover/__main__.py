import sys
from pathlib import Path
from typing import Any, Dict
from slipcover import slipcover as sc
import atexit


from importlib.abc import MetaPathFinder, Loader
from importlib.util import spec_from_loader

class SlipcoverLoader(Loader):
    def __init__(self, sci, orig_loader):
        self.sci = sci
        self.orig_loader = orig_loader

    def create_module(self, spec):
        return self.orig_loader.create_module(spec)

    def get_code(self, name):   # expected by pyrun
        return self.orig_loader.get_code(name)

    def exec_module(self, module):
        code = self.orig_loader.get_code(module.__name__)
        sci.register_module(module)
        code = sci.instrument(code)
        exec(code, module.__dict__)

class SlipcoverMetaPathFinder(MetaPathFinder):
    def __init__(self, args, sci, file_matcher, meta_path):
        self.args = args
        self.sci = sci
        self.file_matcher = file_matcher
        self.meta_path = meta_path

    def find_spec(self, fullname, path, target=None):
        if self.args.debug:
            print(f"Looking for {fullname}")
        for f in self.meta_path:
            found = f.find_spec(fullname, path, target)
            if (found):
                if found.origin and file_matcher.matches(found.origin):
                    if self.args.debug:
                        print(f"adding {fullname} from {found.origin}")
                    found.loader = SlipcoverLoader(self.sci, found.loader)
                return found

        return None

#
# The intended usage is:
#
#   slipcover.py [options] (script | -m module [module_args...])
#
# but argparse doesn't seem to support this.  We work around that by only
# showing it what we need.
#
import argparse
ap = argparse.ArgumentParser(prog='slipcover')
ap.add_argument('--json', action='store_true', help="select JSON output")
ap.add_argument('--pretty-print', action='store_true', help="pretty-print JSON output")
ap.add_argument('--out', type=Path, help="specify output file name")
ap.add_argument('--source', help="specify directories to cover")
ap.add_argument('--omit', help="specify file(s) to omit")
ap.add_argument('--threshold', type=int, default=50, metavar="T", help="threshold for de-instrumentation")

# intended for slipcover development only
ap.add_argument('--silent', action='store_true', help=argparse.SUPPRESS)
ap.add_argument('--stats', action='store_true', help=argparse.SUPPRESS)
ap.add_argument('--debug', action='store_true', help=argparse.SUPPRESS)
ap.add_argument('--dont-wrap-pytest', action='store_true', help=argparse.SUPPRESS)

g = ap.add_mutually_exclusive_group(required=True)
g.add_argument('-m', dest='module', nargs=1, help="run given module as __main__")
g.add_argument('script', nargs='?', type=Path, help="the script to run")
ap.add_argument('script_or_module_args', nargs=argparse.REMAINDER)

if '-m' in sys.argv: # work around exclusive group not handled properly
    minus_m = sys.argv.index('-m')
    args = ap.parse_args(sys.argv[1:minus_m+2])
    args.script_or_module_args = sys.argv[minus_m+2:]
else:
    args = ap.parse_args(sys.argv[1:])

base_path = Path(args.script).resolve().parent if args.script \
            else Path('.').resolve()

file_matcher = sc.FileMatcher()

if args.source:
    for s in args.source.split(','):
        file_matcher.addSource(s)
elif args.script:
    file_matcher.addSource(Path(args.script).resolve().parent)

if args.omit:
    for o in args.omit.split(','):
        file_matcher.addOmit(o)

sci = sc.Slipcover(collect_stats=args.stats, d_threshold=args.threshold)

def wrap_pytest():
    import dis

    def exec_wrapper(obj, g):
        obj = sci.instrument(obj)
        exec(obj, g)

    load_g_op, load_const_op, call_op = (dis.opmap['LOAD_GLOBAL'],
                                         dis.opmap['LOAD_CONST'],
                                         dis.opmap['CALL_FUNCTION'])

    try:
        import _pytest.assertion.rewrite
    except ModuleNotFoundError:
        return

    for f in sc.Slipcover.find_functions(_pytest.assertion.rewrite.__dict__.values(), set()):
        if 'exec' in f.__code__.co_names:
            co = f.__code__

            patch = None

            exec_wrapper_index = len(co.co_consts) # will be appended

            exec_index = co.co_names.index('exec')
            seq = bytes(sc.opcode_arg(load_g_op, exec_index))
            # FIXME refactor function call finder, break and test
            for start in [i for i in range(0, len(co.co_code), 2) if co.co_code[i:i+len(seq)] == seq]:
                exts_used = (len(seq)-2)//2
                end = None
                stack_size = 0
                for (off, oplen, op, arg) in sc.unpack_opargs(co.co_code[start:]):
                    stack_size += dis.stack_effect(op, arg if op >= dis.HAVE_ARGUMENT else None)
                    if (op == call_op and stack_size == 1):
                        end = start + off + oplen
                        break
                    if not stack_size or op in dis.hasjrel or op in dis.hasjabs:
                        break   # couldn't find call sequence

                # FIXME rewrite adjusting branches, etc.
                if end and sc.arg_ext_needed(exec_wrapper_index) <= exts_used:
                    if not patch:
                        patch = bytearray(co.co_code)

                    patch[start:start+len(seq)] = sc.opcode_arg(load_const_op, exec_wrapper_index, exts_used)

            if patch:
                consts = list(co.co_consts)
                consts.append(exec_wrapper)

                f.__code__ = co.replace(
                    co_code=bytes(patch),
                    co_consts=tuple(consts),
                )

if not args.dont_wrap_pytest:
    wrap_pytest()

sys.meta_path=[SlipcoverMetaPathFinder(args, sci, file_matcher, sys.meta_path)]


def print_coverage(outfile):
    if args.json:
        import json
        print(json.dumps(sci.get_coverage(), indent=(4 if args.pretty_print else None)),
              file=outfile)
    else:
        sci.print_coverage(outfile=outfile)

def sci_atexit():
    if args.out:
        with open(args.out, "w") as outfile:
            print_coverage(outfile)
    else:
        print_coverage(sys.stdout)

if not args.silent:
    atexit.register(sci_atexit)

if args.script:
    # python 'globals' for the script being executed
    script_globals: Dict[Any, Any] = dict()

    # needed so that the script being invoked behaves like the main one
    script_globals['__name__'] = '__main__'
    script_globals['__file__'] = args.script

    sys.argv = [args.script, *args.script_or_module_args]

    # the 1st item in sys.path is always the main script's directory
    sys.path.pop(0)
    sys.path.insert(0, str(base_path))

    with open(args.script, "r") as f:
        code = compile(f.read(), str(Path(args.script).resolve()), "exec")

    code = sci.instrument(code)
    exec(code, script_globals)

else:
    import runpy
    sys.argv = [*args.module, *args.script_or_module_args]
    runpy.run_module(*args.module, run_name='__main__', alter_sys=True)
