import sys
from pathlib import Path
from typing import Any, Dict
import runtimeapr as sc
import runtimeapr.branch as br
import ast
import atexit
import platform


#
# The intended usage is:
#
#   slipcover.py [options] (script | -m module [module_args...])
#
# but argparse doesn't seem to support this.  We work around that by only
# showing it what we need.
#
import argparse

from . import Instrumenter, RuntimeAPRFileMatcher,RuntimeAPRImportManager
from .configure import Configure

ap = argparse.ArgumentParser(prog='slipcover')
ap.add_argument('--branch', action='store_true', help="measure both branch and line coverage")
ap.add_argument('--json', action='store_true', help="select JSON output")
ap.add_argument('--pretty-print', action='store_true', help="pretty-print JSON output")
ap.add_argument('--out', type=Path, help="specify output file name")
ap.add_argument('--source', help="specify directories or files to cover, seperated by comma(,)")
ap.add_argument('--omit', help="specify file(s) to omit")
ap.add_argument('--immediate', action='store_true',
                help=(argparse.SUPPRESS if platform.python_implementation() == "PyPy" else "request immediate de-instrumentation"))
ap.add_argument('--skip-covered', action='store_true', help="omit fully covered files (from text, non-JSON output)")
ap.add_argument('--fail-under', type=float, default=0, help="fail execution with RC 2 if the overall coverage lays lower than this")
ap.add_argument('--threshold', type=int, default=50, metavar="T",
                help="threshold for de-instrumentation (if not immediate)")
ap.add_argument('--missing-width', type=int, default=80, metavar="WIDTH", help="maximum width for `missing' column")

# intended for slipcover development only
ap.add_argument('--silent', action='store_true', help=argparse.SUPPRESS)
ap.add_argument('--dis', action='store_true', help=argparse.SUPPRESS)
ap.add_argument('--stats', action='store_true', help=argparse.SUPPRESS)
ap.add_argument('--debug', action='store_true', help=argparse.SUPPRESS)
ap.add_argument('--dont-wrap-pytest', action='store_true', help=argparse.SUPPRESS)

# Custon options for RuntimeAPR
ap.add_argument('--throw-exception', action='store_true', help="throw exception when an error is occured")
ap.add_argument('--original-sc', action='store_true', help="run original slipcover instead of runtime apr")

g = ap.add_mutually_exclusive_group(required=True)
g.add_argument('-m', dest='module', nargs=1, help="run given module as __main__")
g.add_argument('script', nargs='?', type=Path, help="the script to run")
ap.add_argument('script_or_module_args', nargs=argparse.REMAINDER)
ap.add_argument('--ignore-repair', action='store_true', help="only parse the input file and ignore any possible reparation")

if '-m' in sys.argv: # work around exclusive group not handled properly
    minus_m = sys.argv.index('-m')
    args = ap.parse_args(sys.argv[1:minus_m+2])
    args.script_or_module_args = sys.argv[minus_m+2:]
else:
    args = ap.parse_args(sys.argv[1:])

base_path = Path(args.script).resolve().parent if args.script \
            else Path('.').resolve()

if args.debug:
    Configure.debug=True

if args.original_sc:
    file_matcher = sc.FileMatcher()
else:
    file_matcher = RuntimeAPRFileMatcher()

if args.source:
    for s in args.source.split(','):
        file_matcher.addSource(s)
elif args.script:
    file_matcher.addSource(Path(args.script).resolve().parent)

if args.omit:
    for o in args.omit.split(','):
        file_matcher.addOmit(o)


if args.original_sc:
    sci = sc.Slipcover(collect_stats=args.stats, immediate=args.immediate,
                    d_miss_threshold=args.threshold, branch=args.branch,
                    skip_covered=args.skip_covered, disassemble=args.dis)
else:
    sci=Instrumenter()


if args.original_sc and not args.dont_wrap_pytest:
    sc.wrap_pytest(sci, file_matcher)



def print_coverage(outfile):
    if args.json:
        import json
        print(json.dumps(sci.get_coverage(), indent=(4 if args.pretty_print else None)),
              file=outfile)
    else:
        sci.print_coverage(missing_width=args.missing_width, outfile=outfile)


def sci_atexit():
    if args.out:
        with open(args.out, "w") as outfile:
            print_coverage(outfile)
    else:
        print_coverage(sys.stdout)

if args.original_sc and not args.silent:
    atexit.register(sci_atexit)

if not args.original_sc and args.throw_exception:
    sci.throw_exception_when_error=True

if args.script:
    if not args.original_sc:
        sci.is_script_mode=True
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
        t = ast.parse(f.read())
        if args.original_sc and args.branch:
            t = br.preinstrument(t)
        code = compile(t, str(Path(args.script).resolve()), "exec")

    if args.original_sc:
        code = sci.instrument(code)
        with sc.ImportManager(sci, file_matcher):
            exec(code, script_globals)
    else:
        if not args.ignore_repair:
            code = sci.insert_try_except(code)
        with RuntimeAPRImportManager(sci, file_matcher):
            exec(code, script_globals)

else:
    import runpy
    sys.argv = [*args.module, *args.script_or_module_args]
    if args.original_sc:
        with sc.ImportManager(sci, file_matcher):
            runpy.run_module(*args.module, run_name='__main__', alter_sys=True)
    else:
        with RuntimeAPRImportManager(sci, file_matcher):
            runpy.run_module(*args.module, run_name='__main__', alter_sys=True)

if args.original_sc and args.fail_under:
    cov = sci.get_coverage()
    if cov['summary']['percent_covered'] < args.fail_under:
        sys.exit(2)
