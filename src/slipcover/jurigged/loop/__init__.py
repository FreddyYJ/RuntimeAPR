import builtins
import functools
from types import SimpleNamespace

from giving import give, given

from .basic import BasicDeveloopRunner
from .develoop import Develoop, DeveloopRunner, RedirectDeveloopRunner
from .repairloop import RepairloopRunner,except_handler
from .repairutils import prune_default_global_var,BugInformation
from .funcast import FunctionFinderVisitor


# def keyword_decorator(deco):
#     """Wrap a decorator to optionally takes keyword arguments."""

#     @functools.wraps(deco)
#     def new_deco(fn=None, **kwargs):
#         if fn is None:

#             @functools.wraps(deco)
#             def newer_deco(fn):
#                 return deco(fn, **kwargs)

#             return newer_deco
#         else:
#             return deco(fn, **kwargs)

#     return new_deco


# @keyword_decorator
# def loop(fn, interface=None, only_on_error=False):
#     if interface is None:
#         try:
#             import rich

#             interface = "rich"
#         except ModuleNotFoundError:
#             interface = "basic"
#     # interface='basic'

#     if interface == "rich":
#         from .richloop import RichDeveloopRunner

#         interface = RichDeveloopRunner
#     elif interface == "basic":
#         interface = BasicDeveloopRunner
#     elif isinstance(interface, str):
#         raise Exception(f"Unknown develoop interface: '{interface}'")

#     interface=RepairloopRunner
#     # FIXME: Too large overhead at calling Develoop in target program
#     return Develoop(fn, on_error=only_on_error, runner_class=interface)


# loop_on_error = functools.partial(loop, only_on_error=True)
# xloop = loop_on_error

# __ = SimpleNamespace(
#     loop=loop,
#     loop_on_error=loop_on_error,
#     xloop=xloop,
#     give=give,
#     given=given,
# )


# def inject():
#     builtins.__ = __
