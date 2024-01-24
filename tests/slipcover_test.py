import pytest
import runtimeapr.slipcover as sc
import runtimeapr.bytecode as bc
import runtimeapr.branch as br
import types
import dis
import sys
import platform
import re


PYTHON_VERSION = sys.version_info[0:2]

def current_line():
    import inspect as i
    return i.getframeinfo(i.currentframe().f_back).lineno

def current_file():
    import inspect as i
    return i.getframeinfo(i.currentframe().f_back).filename

def simple_current_file():
    simp = sc.PathSimplifier()
    return simp.simplify(current_file())

def ast_parse(s):
    import ast
    import inspect
    return ast.parse(inspect.cleandoc(s))


@pytest.mark.parametrize("stats", [False, True])
def test_probe_signal(stats):
    from runtimeapr import probe

    sci = sc.Slipcover(collect_stats=stats)

    t_123 = probe.new(sci, "/foo/bar.py", 123, -1)
    probe.signal(t_123)

    t_42 = probe.new(sci, "/foo2/baz.py", 42, -1)
    probe.signal(t_42)
    probe.signal(t_42)

    t_314 = probe.new(sci, "/foo2/baz.py", 314, -1)
    probe.signal(t_314)

    # line never executed
    t_666 = probe.new(sci, "/foo/beast.py", 666, -1)

    d = sci.newly_seen
    assert ["/foo/bar.py", "/foo2/baz.py"] == sorted(d.keys())
    assert [123] == sorted(list(d["/foo/bar.py"]))
    assert [42, 314] == sorted(list(d["/foo2/baz.py"]))

    assert ("/foo2/baz.py", 42, 1, 0, 2) == probe.get_stats(t_42)
    assert ("/foo2/baz.py", 314, 0, 0, 1) == probe.get_stats(t_314)

    assert ("/foo/beast.py", 666, 0, 0, 0) == probe.get_stats(t_666)


@pytest.mark.parametrize("stats", [False, True])
def test_probe_deinstrument(stats):
    from runtimeapr import probe

    sci = sc.Slipcover(collect_stats=stats)

    t = probe.new(sci, "/foo/bar.py", 123, 3)
    probe.signal(t)

    assert ["/foo/bar.py"] == sorted(sci.newly_seen.keys())

    probe.signal(t)
    probe.signal(t)
    probe.signal(t)   # triggers deinstrument_seen... but not instrumented through sci

    probe.mark_removed(t) # fake it since sci didn't instrument it
    probe.signal(t)   # u-miss

    probe.no_signal(t)

    assert [] == sorted(sci.newly_seen.keys())
    assert ["/foo/bar.py"] == sorted(sci.all_seen.keys())

    assert ("/foo/bar.py", 123, 3, 1, 6) == probe.get_stats(t)




def test_pathsimplifier_not_relative():
    from pathlib import Path

    ps = sc.PathSimplifier()

    assert ".." == ps.simplify("..")


def check_line_probes(code):
    # Are all lines where we expect?
    for (offset, line) in dis.findlinestarts(code):
        if line:
            print(f"checking {code.co_name} line {line}")
            assert bc.op_NOP == code.co_code[offset], f"NOP missing at offset {offset}"
            probe_len = bc.branch2offset(code.co_code[offset+1])
            it = iter(bc.unpack_opargs(code.co_code[offset+2:offset+2+probe_len]))

            if PYTHON_VERSION >= (3,11):
                op_offset, op_len, op, op_arg = next(it)
                assert op == bc.op_PUSH_NULL

            op_offset, op_len, op, op_arg = next(it)
            assert op == bc.op_LOAD_CONST

            op_offset, op_len, op, op_arg = next(it)
            assert op == bc.op_LOAD_CONST

            op_offset, op_len, op, op_arg = next(it)
            if PYTHON_VERSION >= (3,11):
                assert op == bc.op_PRECALL
                op_offset, op_len, op, op_arg = next(it)
                assert op == bc.op_CALL
            else:
                assert op == bc.op_CALL_FUNCTION

            op_offset, op_len, op, op_arg = next(it)
            assert op == bc.op_POP_TOP

            assert next(it, None) is None   # check end of probe

    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            check_line_probes(const)


@pytest.mark.parametrize("stats", [False, True])
def test_instrument(stats):
    sci = sc.Slipcover(collect_stats=stats)

    base_line = current_line()
    def foo(n): #1
        if n == 42:
            return 666
        x = 0
        for i in range(n):
            x += (i+1)
        return x

    sci.instrument(foo)
    dis.dis(foo)

    assert foo.__code__.co_stacksize >= bc.calc_max_stack(foo.__code__.co_code)
    assert '__slipcover__' in foo.__code__.co_consts

    check_line_probes(foo.__code__)

    dis.dis(foo)
    assert 6 == foo(3)

    cov = sci.get_coverage()
    assert {simple_current_file()} == cov['files'].keys()

    cov = cov['files'][simple_current_file()]
    if PYTHON_VERSION >= (3,11):
        assert [1, 2, 4, 5, 6, 7] == [l-base_line for l in cov['executed_lines']]
    else:
        assert [2, 4, 5, 6, 7] == [l-base_line for l in cov['executed_lines']]
    assert [3] == [l-base_line for l in cov['missing_lines']]


@pytest.mark.parametrize("stats", [False, True])
def test_instrument_generators(stats):
    sci = sc.Slipcover(collect_stats=stats)

    base_line = current_line()
    def foo(n):
        n += sum(
            x for x in range(10)
            if x % 2 == 0)
        n += [
            x for x in range(123)
            if x == 42][0]
        return n

    X = foo(123)

#    dis.dis(foo)
    sci.instrument(foo)

    assert foo.__code__.co_stacksize >= bc.calc_max_stack(foo.__code__.co_code)
    assert '__slipcover__' in foo.__code__.co_consts

    # Are all lines where we expect?
    for (offset, _) in dis.findlinestarts(foo.__code__):
        assert bc.op_NOP == foo.__code__.co_code[offset]

#    dis.dis(foo)
    assert X == foo(123)

    cov = sci.get_coverage()
    assert {simple_current_file()} == cov['files'].keys()

    cov = cov['files'][simple_current_file()]
    if PYTHON_VERSION >= (3,11):
        assert [1, 2, 3, 4, 5, 6, 7, 8] == [l-base_line for l in cov['executed_lines']]
    else:
        assert [2, 3, 4, 5, 6, 7, 8] == [l-base_line for l in cov['executed_lines']]

    assert [] == cov['missing_lines']


@pytest.mark.parametrize("stats", [False, True])
def test_instrument_exception(stats):
    sci = sc.Slipcover(collect_stats=stats)

    base_line = current_line()
    def foo(n): #1
        n += 10
        try:
            n += 10
            raise RuntimeError('just testing')
            n = 0 #6
        except RuntimeError:
            n += 15
        finally:
            n += 42

        return n #12

    orig_code = foo.__code__
    X = foo(42)

    sci.instrument(foo)
    dis.dis(orig_code)

    assert foo.__code__.co_stacksize >= orig_code.co_stacksize
    assert '__slipcover__' in foo.__code__.co_consts

    # Are all lines where we expect?
    for (offset, _) in dis.findlinestarts(foo.__code__):
        assert bc.op_NOP == foo.__code__.co_code[offset]

    dis.dis(foo)
    assert X == foo(42)

    cov = sci.get_coverage()
    assert {simple_current_file()} == cov['files'].keys()

    cov = cov['files'][simple_current_file()]
    if PYTHON_VERSION >= (3,11):
        assert [1, 2, 3, 4, 5, 7, 8, 10, 12] == [l-base_line for l in cov['executed_lines']]
    else:
        assert [2, 3, 4, 5, 7, 8, 10, 12] == [l-base_line for l in cov['executed_lines']]

    if PYTHON_VERSION >= (3,10):
        # #6 is unreachable and is omitted from the code
        assert [] == [l-base_line for l in cov['missing_lines']]
    else:
        assert [6] == [l-base_line for l in cov['missing_lines']]


@pytest.mark.skipif(PYTHON_VERSION != (3,10), reason="N/A: only 3.10 seems to generate code like this")
def test_instrument_code_before_first_line():
    sci = sc.Slipcover()

    first_line = current_line()+1
    def foo(n):
        for i in range(n+1):
            yield i
    last_line = current_line()

    dis.dis(foo)
    print([str(l) for l in bc.LineEntry.from_code(foo.__code__)])

    # Generators in 3.10 start with a GEN_START that's not assigned to any lines;
    # that's what we're trying to test here
    first_line_offset, _ = next(dis.findlinestarts(foo.__code__))
    assert 0 != first_line_offset

    sci.instrument(foo)
    dis.dis(foo)

    # Are all lines where we expect?
    for (offset, _) in dis.findlinestarts(foo.__code__):
        assert bc.op_NOP == foo.__code__.co_code[offset]

    assert 6 == sum(foo(3))

    cov = sci.get_coverage()
    assert {simple_current_file()} == cov['files'].keys()

    cov = cov['files'][simple_current_file()]
    assert [*range(first_line+1, last_line)] == cov['executed_lines']
    assert [] == cov['missing_lines']


def test_instrument_threads():
    sci = sc.Slipcover()
    result = None

    base_line = current_line()
    def foo(n):
        nonlocal result
        x = 0
        for i in range(n):
            x += (i+1)
        result = x

    sci.instrument(foo)

    import threading

    t = threading.Thread(target=foo, args=(3,))
    t.start()
    t.join()

    assert 6 == result

    cov = sci.get_coverage()
    assert {simple_current_file()} == cov['files'].keys()

    cov = cov['files'][simple_current_file()]
    if PYTHON_VERSION >= (3,11):
        assert [1, 3, 4, 5, 6] == [l-base_line for l in cov['executed_lines']]
    else:
        assert [3, 4, 5, 6] == [l-base_line for l in cov['executed_lines']]
    assert [] == cov['missing_lines']


@pytest.mark.skipif(PYTHON_VERSION >= (3,11), reason="N/A, I think -- how to replicate?", run=False)
@pytest.mark.parametrize("N", [260])#, 65600])
def test_instrument_doesnt_interrupt_ext_sequence(N):
    EXT = bc.op_EXTENDED_ARG

    sci = sc.Slipcover()

    # create code with >256 constants
    src = 'x=0\n' + ''.join([f'y={i}; x += y\n' for i in range(1, N+1)])
    code = compile(src, 'foo', 'exec')


    # Move offsets so that an EXTENDED_ARG is on one line and the rest on another
    # Python 3.9.10 actually generated code like that:
    #
    # 2107        1406 LOAD_NAME               31 (ignore_warnings)
    # 2109        1408 EXTENDED_ARG             1
    # 2108        1410 LOAD_CONST             267 ((False, 'float64'))
    #
    lines = bc.LineEntry.from_code(code)
    for i in range(len(lines)):
        if lines[i].number > 257:
            assert EXT == code.co_code[lines[i].start]
            lines[i].start = lines[i-1].end = lines[i-1].end + 2

    if PYTHON_VERSION == (3,10):
        code = code.replace(co_linetable=bc.LineEntry.make_linetable(1, lines))
    else:
        code = code.replace(co_lnotab=bc.LineEntry.make_lnotab(1, lines))

    orig = {}
    exec(code, globals(), orig)

    instr = {}
    code = sci.instrument(code)
    exec(code, globals(), instr)

    assert orig['x'] == instr['x']

    cov = sci.get_coverage()
    assert {'foo'} == cov['files'].keys()

    cov = cov['files']['foo']
    assert [*range(1, N+2)] == cov['executed_lines']
    assert [] == cov['missing_lines']

    assert 'executed_branches' not in cov
    assert 'missing_branches' not in cov


def test_instrument_branches():
    t = ast_parse("""
        def foo(x):
            if x >= 0:
                if x > 1:
                    if x > 2:
                        return 2
                    return 1

            else:
                return 0

        foo(2)
    """)
    t = br.preinstrument(t)

    sci = sc.Slipcover(branch=True)
    code = compile(t, 'foo', 'exec')
    code = sci.instrument(code)
#    dis.dis(code)

    check_line_probes(code)

    g = dict()
    exec(code, g, g)

    cov = sci.get_coverage()
    assert {'foo'} == cov['files'].keys()

    cov = cov['files']['foo']
    assert [1,2,3,4,6,11] == cov['executed_lines']
    assert [5,9] == cov['missing_lines']

    assert [(2,3),(3,4),(4,6)] == cov['executed_branches']
    assert [(2,9),(3,0),(4,5)] == cov['missing_branches']


@pytest.mark.parametrize("x", [5, 20])
def test_instrument_branch_into_line_block(x):
    # the 5->7 branch may lead to a jump into the middle of line # 7's block;
    # will it miss its line probe?  Happens with Python 3.10.9.
    t = ast_parse(f"""
        import pytest

        def foo(x):
            y = x + 10
            if y > 20:
                y -= 1
            return y

        foo({x})
    """)
    t = br.preinstrument(t)

    sci = sc.Slipcover(branch=True)
    code = compile(t, 'foo', 'exec')
    code = sci.instrument(code)
    dis.dis(code)

    check_line_probes(code)

    g = dict()
    exec(code, g, g)

    cov = sci.get_coverage()
    assert {'foo'} == cov['files'].keys()

    cov = cov['files']['foo']
    if (x+10)>20:
        assert [1,3,4,5,6,7,9] == cov['executed_lines']
        assert [] == cov['missing_lines']

        assert [(5,6)] == cov['executed_branches']
        assert [(5,7)] == cov['missing_branches']
    else:
        assert [1,3,4,5,7,9] == cov['executed_lines']
        assert [6] == cov['missing_lines']

        assert [(5,7)] == cov['executed_branches']
        assert [(5,6)] == cov['missing_branches']

def test_instrument_branches_pypy_crash():
    """In Python 3.9, the branch instrumentation at the beginning of foo's code
       object shows as being on line 5; that leads to a branch probe and a line
       probe being inserted at the same offset (0), but the instrumentation loop
       used to assume that insertion offsets rose monotonically."""
    t = ast_parse("""
        # this comment and the whitespace below are important



        def foo():
            while True:
                f()
    """)
    t = br.preinstrument(t)

    sci = sc.Slipcover(branch=True)
    code = compile(t, 'foo', 'exec')
    code = sci.instrument(code)
    dis.dis(code)

    check_line_probes(code)


@pytest.mark.parametrize("do_branch", [True, False])
def test_meta_in_results(do_branch):
    t = ast_parse("""
        def foo(x):
            if x >= 0:
                if x > 1:
                    if x > 2:
                        return 2
                    return 1

            else:
                return 0

        foo(2)
    """)
    if do_branch:
        t = br.preinstrument(t)

    sci = sc.Slipcover(branch=do_branch)
    code = compile(t, 'foo', 'exec')
    code = sci.instrument(code)

    g = dict()
    exec(code, g, g)

    cov = sci.get_coverage()

    assert 'meta' in cov
    meta = cov['meta']
    assert 'slipcover' == meta['software']
    assert sc.VERSION == meta['version']
    assert 'timestamp' in meta
    assert do_branch == meta['branch_coverage']


def test_get_coverage_detects_lines():
    base_line = current_line()
    def foo(n):             # 1
        """Foo.

        Bar baz.
        """
        x = 0               # 6

        def bar():          # 8
            x += 42

        # now we loop
        for i in range(n):  # 12
            x += (i+1)

        return x

    sci = sc.Slipcover()
    sci.instrument(foo)

    cov = sci.get_coverage()
    assert {simple_current_file()} == cov['files'].keys()

    cov = cov['files'][simple_current_file()]
    if PYTHON_VERSION >= (3,11):
        assert [1, 6, 8, 9, 12, 13, 15] == [l-base_line for l in cov['missing_lines']]
    else:
        assert [6, 8, 9, 12, 13, 15] == [l-base_line for l in cov['missing_lines']]
    assert [] == cov['executed_lines']


def gen_long_jump_code(N):
    return "x = 0\n" + \
           "for _ in range(1):\n" + \
           "    " + ("x += 1;" * N) + "pass\n"

def gen_test_sequence():
    code = compile(gen_long_jump_code(64*1024), "foo", "exec")
    branches = bc.Branch.from_code(code)

    b = next(b for b in branches if b.is_relative)

    # we want to generate Ns so that Slipcover's instrumentation forces
    # the "if" branch to grow in length (with an additional extended_arg)
    return [(64*1024*arg)//b.arg() for arg in [0xFF, 0xFFFF]]#, 0xFFFFFF]]


@pytest.mark.skipif(PYTHON_VERSION == (3,11), reason='brittle test')
@pytest.mark.parametrize("N", gen_test_sequence())
def test_instrument_long_jump(N):
    # each 'if' adds a branch
    src = gen_long_jump_code(N)

    code = compile(src, "foo", "exec")
    dis.dis(code)

    orig_branches = bc.Branch.from_code(code)
    assert 2 <= len(orig_branches)

    sci = sc.Slipcover()
    code = sci.instrument(code)

    dis.dis(code)

    # Are all lines where we expect?
    for (offset, _) in dis.findlinestarts(code):
        # This catches any lines not where we expect,
        # such as any not adjusted after adjusting branch lengths
        assert bc.op_NOP == code.co_code[offset]

    # we want at least one branch to have grown in length
    print([b.arg() for b in orig_branches])
    print([b.arg() for b in bc.Branch.from_code(code)])
    assert any(b.length > orig_branches[i].length for i, b in enumerate(bc.Branch.from_code(code)))

    exec(code, locals(), globals())
    assert N == x

    cov = sci.get_coverage()['files']['foo']
    assert [*range(1, 4)] == cov['executed_lines']
    assert [] == cov['missing_lines']


@pytest.mark.parametrize("stats", [False, True])
def test_deinstrument(stats):
    base_line = current_line()
    def foo(n):
        def bar(n):
            return n+1
        x = 0
        for i in range(bar(n)):
            x += i
        return x
    last_line = current_line()

    sci = sc.Slipcover(collect_stats=stats)
    assert not sci.get_coverage()['files'].keys()

    sci.instrument(foo)
    sci.deinstrument(foo, {*range(base_line+1, last_line)})
    dis.dis(foo)
    assert 6 == foo(3)
    assert [] == sci.get_coverage()['files'][simple_current_file()]['executed_lines']


@pytest.mark.skipif(platform.python_implementation() == 'PyPy', reason="Immediate de-instrumentation does not work with PyPy")
@pytest.mark.parametrize("stats", [False, True])
def test_deinstrument_immediately(stats):
    base_line = current_line()
    def foo(n):
        def bar(n):
            return n+1
        x = 0
        for i in range(bar(n)):
            x += i
        return x
    last_line = current_line()

    sci = sc.Slipcover(collect_stats=stats, immediate=True)
    assert not sci.get_coverage()['files'].keys()

    sci.instrument(foo)

    for off, *_ in dis.findlinestarts(foo.__code__):
        assert foo.__code__.co_code[off] == bc.op_NOP

    assert 6 == foo(3)

    for off, *_ in dis.findlinestarts(foo.__code__):
        assert foo.__code__.co_code[off] == bc.op_JUMP_FORWARD


@pytest.mark.parametrize("stats", [False, True])
def test_deinstrument_with_many_consts(stats):
    sci = sc.Slipcover(collect_stats=stats)

    N = 1024
    src = 'x=0\n' + ''.join([f'x = {i}\n' for i in range(1, N)])

    code = compile(src, "foo", "exec")

    assert len(code.co_consts) >= N

    code = sci.instrument(code)

    # this is the "important" part of the test: check that it can
    # update the probe(s) even if it requires processing EXTENDED_ARGs
    code = sci.deinstrument(code, set(range(1, N)))
    dis.dis(code)

    exec(code, locals(), globals())
    assert N-1 == x

    cov = sci.get_coverage()['files']['foo']
    assert [N] == cov['executed_lines']
    assert [*range(1,N)] == cov['missing_lines']


@pytest.mark.parametrize("stats", [False, True])
def test_deinstrument_some(stats):
    sci = sc.Slipcover(collect_stats=stats)

    base_line = current_line()
    def foo(n):
        x = 0
        for i in range(n): #3
            x += (i+1)
        return x

    assert not sci.get_coverage()['files'].keys()

    sci.instrument(foo)
    sci.deinstrument(foo, {base_line+3, base_line+4})

    assert 6 == foo(3)
    cov = sci.get_coverage()['files'][simple_current_file()]
    if PYTHON_VERSION >= (3,11):
        assert [1, 2, 5] == [l-base_line for l in cov['executed_lines']]
    else:
        assert [2, 5] == [l-base_line for l in cov['executed_lines']]
    assert [3, 4] == [l-base_line for l in cov['missing_lines']]


@pytest.mark.parametrize("do_branch", [False, True])
def test_deinstrument_seen_upon_d_miss_threshold(do_branch):
    from runtimeapr import probe as tr

    t = ast_parse("""
        def foo(n):
            x = 0;
            for _ in range(100):
                x += n
            return x    # line 5
    """)
    if do_branch:
        t = br.preinstrument(t)
    g = dict()
    exec(compile(t, "foo", "exec"), g, g)
    foo = g['foo']

    sci = sc.Slipcover(branch=do_branch)
    assert not sci.get_coverage()['files']

    sci.instrument(foo)
    old_code = foo.__code__

    foo(0)

    assert old_code != foo.__code__, "Code never de-instrumented"

    # skip probes with d_miss == 0, as these may not have been de-instrumented
    probes = [t for t in old_code.co_consts if type(t).__name__ == 'PyCapsule' and tr.get_stats(t)[2] > 0]
    assert len(probes) > 0
    for t in probes:
        assert tr.was_removed(t), f"probe still instrumented: {tr.get_stats(t)}"

    cov = sci.get_coverage()['files']['foo']
    if PYTHON_VERSION >= (3,11):
        assert [1,2,3,4,5] == cov['executed_lines']
    else:
        assert [2,3,4,5] == cov['executed_lines']
    assert [] == cov['missing_lines']
    if do_branch:
        assert [(3,4),(3,5)] == cov['executed_branches']
        assert [] == cov['missing_branches']

    foo(1)


def test_deinstrument_seen_upon_d_miss_threshold_doesnt_count_while_deinstrumenting():
    sci = sc.Slipcover()

    base_line = current_line()
    def foo(n):
        class Desc:  # https://docs.python.org/3/howto/descriptor.html
            def __get__(self, obj, objtype=None):
                return 10   # 4 <-- shouldn't be seen
        class Bar:
            v = Desc()
        x = 0
        for _ in range(100):
            x += n
        return x

    assert not sci.get_coverage()['files']

    sci.instrument(foo)
    old_code = foo.__code__

    foo(0)

    assert old_code != foo.__code__, "Code never de-instrumented"

    foo(1)

    cov = sci.get_coverage()['files'][simple_current_file()]
    if PYTHON_VERSION >= (3,11):
        assert [1, 2, 3, 5, 6, 7, 8, 9, 10] == [l-base_line for l in cov['executed_lines']]
    else:
        assert [2, 3, 5, 6, 7, 8, 9, 10] == [l-base_line for l in cov['executed_lines']]
    assert [4] == [l-base_line for l in cov['missing_lines']]


def test_deinstrument_seen_descriptor_not_invoked():
    sci = sc.Slipcover()

    base_line = current_line()
    def foo(n):
        class Desc:  # https://docs.python.org/3/howto/descriptor.html
            def __get__(self, obj, objtype=None):
                raise TypeError("just testing!") #4
        class Bar:
            v = Desc()
        x = 0
        for _ in range(100):
            x += n
        return x
    last_line = current_line()

    assert not sci.get_coverage()['files']

    sci.instrument(foo)
    old_code = foo.__code__

    foo(0)

    assert old_code != foo.__code__, "Code never de-instrumented"

    foo(1)

    cov = sci.get_coverage()['files'][simple_current_file()]
    if PYTHON_VERSION >= (3,11):
        assert [1, 2, 3, 5, 6, 7, 8, 9, 10] == [l-base_line for l in cov['executed_lines']]
    else:
        assert [2, 3, 5, 6, 7, 8, 9, 10] == [l-base_line for l in cov['executed_lines']]
    assert [4] == [l-base_line for l in cov['missing_lines']]


def test_no_deinstrument_seen_negative_threshold():
    sci = sc.Slipcover(d_miss_threshold=-1)

    first_line = current_line()+2
    def foo(n):
        x = 0;
        for _ in range(100):
            x += n
        return x
    last_line = current_line()

    assert not sci.get_coverage()['files']

    sci.instrument(foo)
    old_code = foo.__code__

    foo(0)

    assert old_code == foo.__code__, "Code de-instrumented"


def test_format_missing():
    fm = sc.Slipcover.format_missing

    assert "" == fm([],[],[])
    assert "" == fm([], [1,2,3], [])
    assert "2, 4" == fm([2,4], [1,3,5], [])
    assert "2-4, 6, 9" == fm([2,3,4, 6, 9], [1, 5, 7,8], [])

    assert "2-6, 9-11" == fm([2,4,6, 9,11], [1, 7,8], [])

    assert "2-11" == fm([2,4,6, 9,11], [], [])

    assert "2-6, 9-11" == fm([2,4,6, 9,11], [8], [])


    assert "1->3" == fm([], [1,2,3], [(1,3)])
    assert "2->exit" == fm([], [1,2,3], [(2,0)])

    assert "2->exit, 4" == fm([4], [1,2,3], [(2,0)])

    assert "2->exit, 4, 22" == fm([4, 22], [1,2,3,21], [(2,0)])

    # omit missing branches involving lines that are missing
    assert "2, 4" == fm([2,4], [1,3,5], [(2,3), (3,4)])


@pytest.mark.parametrize("stats", [False, True])
def test_print_coverage(stats, capsys):
    sci = sc.Slipcover(collect_stats=stats)

    base_line = current_line()
    def foo(n):
        if n == 42:
            return 666 #3
        x = 0
        for i in range(n):
            x += (i+1)
        return x

    sci.instrument(foo)
    foo(3)
    sci.print_coverage(sys.stdout)

    cov = sci.get_coverage()['files'][simple_current_file()]
    execd = len(cov['executed_lines'])
    missd = len(cov['missing_lines'])
    total = execd+missd

    # TODO test more cases (multiple files, etc.)
    output = capsys.readouterr()[0]
    print(output)
    output = output.splitlines()
    assert re.match(f'^tests[/\\\\]slipcover_test\\.py + {total} + {missd} +{round(100*execd/total)} +' + str(base_line+3), output[3])

    if stats:
        assert re.match('^tests[/\\\\]slipcover_test\\.py +[\\d.]+ +0', output[8])


def test_print_coverage_branch(capsys):
    t = ast_parse("""
        def foo(x):
            if x >= 0:
                if x > 1:
                    if x > 2:
                        return 2
                    return 1

            else:
                return 0

        foo(2)
    """)
    t = br.preinstrument(t)

    sci = sc.Slipcover(branch=True)
    code = compile(t, 'foo.py', 'exec')
    code = sci.instrument(code)

    sci.print_coverage(sys.stdout)

    cov = sci.get_coverage()['files']['foo.py']
    exec_l = len(cov['executed_lines'])
    miss_l = len(cov['missing_lines'])
    total_l = exec_l + miss_l
    exec_b = len(cov['executed_branches'])
    miss_b = len(cov['missing_branches'])
    total_b = exec_b + miss_b

    pct = round(100*(exec_l+exec_b)/(total_l+total_b))

    # TODO test more cases (multiple files, etc.)
    output = capsys.readouterr()[0]
    print(output)
    output = output.splitlines()
    assert re.match(f'^foo\\.py +{total_l} +{miss_l} +{total_b} +{miss_b} +{pct}', output[3])


@pytest.mark.parametrize("do_stats", [False, True])
@pytest.mark.parametrize("do_branch", [True, False])
def test_print_coverage_zero_lines(do_branch, do_stats, capsys):
    t = ast_parse("")
    if do_branch:
        t = br.preinstrument(t)

    sci = sc.Slipcover(branch=do_branch)
    code = compile(t, 'foo.py', 'exec')
    code = sci.instrument(code)
    #dis.dis(code)

    g = dict()
    exec(code, g, g)
    sci.print_coverage(sys.stdout)
    output = capsys.readouterr()[0]
    output = output.splitlines()
    assert re.match(f'^foo\\.py +{"1" if PYTHON_VERSION < (3,11) else "0"} +0{" +0 +0" if do_branch else ""} +100', output[3])


def test_print_coverage_skip_covered():
    import subprocess

    p = subprocess.run(f"{sys.executable} -m slipcover --skip-covered tests/importer.py".split(), check=True, capture_output=True)
    output = str(p.stdout)
    assert '__init__.py' in output
    assert 'importer.py' not in output


def test_find_functions():
    import class_test as t

    def func_names(funcs):
        return sorted(map(lambda f: f.__name__, funcs))

    assert ["b", "b_classm", "b_static", "f1", "f2", "f3", "f4", "f5", "f7",
            "f_classm", "f_static"] == \
           func_names(sc.Slipcover.find_functions(t.__dict__.values(), set()))

    assert ["b", "b_classm", "b_static", "f1", "f2", "f3", "f4",
            "f_classm", "f_static"] == \
           func_names(sc.Slipcover.find_functions([t.Test], set()))

    assert ["f5", "f7"] == \
           func_names(sc.Slipcover.find_functions([t.f5, t.f7], set()))

    visited = set()
    assert ["b", "b_classm", "b_static", "f1", "f2", "f3", "f4", "f5", "f7",
            "f_classm", "f_static"] == \
           func_names(sc.Slipcover.find_functions([*t.__dict__.values(), t.Test.Inner],
                                                  visited))

    assert [] == \
           func_names(sc.Slipcover.find_functions([*t.__dict__.values(), t.Test.Inner],
                                                  visited))


@pytest.mark.parametrize("do_branch", [True, False])
def test_interpose_on_module_load(tmp_path, do_branch):
    # TODO include in coverage info
    from pathlib import Path
    import subprocess
    import json

    out_file = tmp_path / "out.json"

    subprocess.run(f"{sys.executable} -m slipcover {'--branch ' if do_branch else ''}--json --out {out_file} tests/importer.py".split(),
                   check=True)
    with open(out_file, "r") as f:
        cov = json.load(f)

    module_file = str(Path('tests') / 'imported' / '__init__.py')

    assert module_file in cov['files']
    assert [1,2,3,4,5,6,8] == cov['files'][module_file]['executed_lines']
    assert [9] == cov['files'][module_file]['missing_lines']
    if do_branch:
        assert [[3,4], [4,5], [4,6]] == cov['files'][module_file]['executed_branches']
        assert [[3,6]] == cov['files'][module_file]['missing_branches']
    else:
        assert 'executed_branches' not in cov['files'][module_file]
        assert 'missing_branches' not in cov['files'][module_file]


def test_pytest_interpose(tmp_path):
    # TODO include in coverage info
    from pathlib import Path
    import subprocess
    import json

    out_file = tmp_path / "out.json"

    test_file = str(Path('tests') / 'pyt.py')

    subprocess.run(f"{sys.executable} -m slipcover --json --out {out_file} -m pytest {test_file}".split(),
                   check=True)
    with open(out_file, "r") as f:
        cov = json.load(f)

    assert test_file in cov['files']
    assert {test_file} == set(cov['files'].keys())  # any unrelated files included?
    cov = cov['files'][test_file]
    assert [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14] == cov['executed_lines']
    assert [] == cov['missing_lines']


def test_pytest_interpose_branch(tmp_path):
    # TODO include in coverage info
    from pathlib import Path
    import subprocess
    import json

    test_file = str(Path('tests') / 'pyt.py')
    def cache_files():
        return list(Path("tests/__pycache__").glob(f"pyt*{sys.implementation.cache_tag}-pytest*.pyc"))

    # remove and create a clean pytest cache, to make sure it's not interfering
    for p in cache_files(): p.unlink()
    subprocess.run(f"{sys.executable} -m pytest {test_file}".split(), check=True)
    pytest_cache_files = cache_files()
    assert len(pytest_cache_files) == 1
    pytest_cache_content = pytest_cache_files[0].read_bytes()

    out_file = tmp_path / "out.json"
    subprocess.run(f"{sys.executable} -m slipcover --branch --json --out {out_file} -m pytest {test_file}".split(),
                   check=True)
    with open(out_file, "r") as f:
        cov = json.load(f)

    assert test_file in cov['files']
    assert {test_file} == set(cov['files'].keys())  # any unrelated files included?
    cov = cov['files'][test_file]
    assert [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14] == cov['executed_lines']
    assert [] == cov['missing_lines']
    assert [[3,4], [4,5], [4,6]] == cov['executed_branches']
    assert [[3,6]] == cov['missing_branches']

    new_cache_files = set(cache_files())
    sc_cache_files = set(fn for fn in new_cache_files if ('slipcover-' + sc.VERSION) in fn.name)

    # ensure ours is being cached
    assert {} != sc_cache_files

    # and that nothing else changed
    assert set(pytest_cache_files) == new_cache_files - sc_cache_files
    assert (pytest_cache_content == pytest_cache_files[0].read_bytes())


def test_pytest_plugins_visible():
    import subprocess

    def pytest_plugins():
        from importlib import metadata
        return [dist.metadata['Name'] for dist in metadata.distributions() \
                if any(ep.group == "pytest11" for ep in dist.entry_points)]

    assert pytest_plugins, "No pytest plugins installed, can't tell if they'd be visible."

    plain = subprocess.run(f"{sys.executable} -m pytest -VV".split(), check=True, capture_output=True)
    with_sc = subprocess.run(f"{sys.executable} -m slipcover --silent -m pytest -VV".split(), check=True,
                             capture_output=True)

    assert plain.stdout == with_sc.stdout


@pytest.mark.parametrize("do_branch", [True, False])
def test_summary_in_output(tmp_path, do_branch):
    # TODO include in coverage info
    from pathlib import Path
    import subprocess
    import json

    out_file = tmp_path / "out.json"

    subprocess.run(f"{sys.executable} -m slipcover {'--branch ' if do_branch else ''}--json --out {out_file} tests/importer.py".split(),
                   check=True)
    with open(out_file, "r") as f:
        cov = json.load(f)

    for fn in cov['files']:
        assert 'summary' in cov['files'][fn]
        summ = cov['files'][fn]['summary']

        assert len(cov['files'][fn]['executed_lines']) == summ['covered_lines']
        assert len(cov['files'][fn]['missing_lines']) == summ['missing_lines']

        nom = summ['covered_lines']
        den = summ['covered_lines'] + summ['missing_lines']

        if do_branch:
            assert len(cov['files'][fn]['executed_branches']) == summ['covered_branches']
            assert len(cov['files'][fn]['missing_branches']) == summ['missing_branches']

            nom += summ['covered_branches']
            den += summ['covered_branches'] + summ['missing_branches']

        assert pytest.approx(100*nom/den) == summ['percent_covered']

    assert 'summary' in cov
    summ = cov['summary']

    missing_lines = sum(cov['files'][fn]['summary']['missing_lines'] for fn in cov['files'])
    executed_lines = sum(cov['files'][fn]['summary']['covered_lines'] for fn in cov['files'])

    nom = executed_lines
    den = nom + missing_lines

    assert missing_lines == summ['missing_lines']
    assert executed_lines == summ['covered_lines']

    if do_branch:
        missing_branches = sum(cov['files'][fn]['summary']['missing_branches'] for fn in cov['files'])
        executed_branches = sum(cov['files'][fn]['summary']['covered_branches'] for fn in cov['files'])

        nom += executed_branches
        den += missing_branches + executed_branches

        assert missing_branches == summ['missing_branches']
        assert executed_branches == summ['covered_branches']

    assert pytest.approx(100*nom/den) == summ['percent_covered']


@pytest.mark.parametrize("do_branch", [True, False])
def test_summary_in_output_zero_lines(do_branch):
    t = ast_parse("")
    if do_branch:
        t = br.preinstrument(t)

    sci = sc.Slipcover(branch=do_branch)
    code = compile(t, 'foo', 'exec')
    code = sci.instrument(code)
    #dis.dis(code)

    g = dict()
    exec(code, g, g)

    cov = sci.get_coverage()

    for fn in cov['files']:
        assert 'summary' in cov['files'][fn]
        summ = cov['files'][fn]['summary']

        if PYTHON_VERSION >= (3,11):
            assert 0 == summ['covered_lines']
        else:
            assert 1 == summ['covered_lines']

        assert 0 == summ['missing_lines']

        if do_branch:
            assert 0 == summ['covered_branches']
            assert 0 == summ['missing_branches']

        assert 100.0 == summ['percent_covered']


    assert 'summary' in cov
    summ = cov['summary']

    if PYTHON_VERSION >= (3,11):
        assert 0 == summ['covered_lines']
    else:
        assert 1 == summ['covered_lines']
    assert 0 == summ['missing_lines']

    if do_branch:
        assert 0 == summ['missing_branches']
        assert 0 == summ['covered_branches']

    assert 100.0 == summ['percent_covered']


@pytest.mark.parametrize("json_flag", ["", "--json"])
def test_fail_under(json_flag):
    import subprocess

    p = subprocess.run(f"{sys.executable} -m slipcover {json_flag} --fail-under 100 tests/branch.py".split(), check=False)
    assert 0 == p.returncode

    p = subprocess.run(f"{sys.executable} -m slipcover {json_flag} --branch --fail-under 83 tests/branch.py".split(), check=False)
    assert 0 == p.returncode

    p = subprocess.run(f"{sys.executable} -m slipcover {json_flag} --branch --fail-under 84 tests/branch.py".split(), check=False)
    assert 2 == p.returncode
