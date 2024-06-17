from .lisp_interpret import *


def test_ite():
    ite = "(define-fun f ( (_arg_0 Int) (_arg_1 Int)) Int (ite (< _arg_0 5) (- _arg_1 1) _arg_0))"
    f = function_from_string(ite)
    assert f(12, 14) == 12
    assert f(3, 13) == 12


def test_bool():
    b_or = "(define-fun f ( (_arg_0 Bool) (_arg_1 Bool)) Bool (or _arg_1 _arg_0))"
    f = function_from_string(b_or)
    assert f(True, False)
    assert not f(False, False)
    assert f(False, True)
    assert f(True, True)

    b_and = "(define-fun f ( (_arg_0 Bool) (_arg_1 Bool)) Bool (and _arg_1 _arg_0))"
    f = function_from_string(b_and)
    assert not f(True, False)
    assert not f(False, False)
    assert f(True, True)
    assert not f(False, False)

    b_xor = "(define-fun f ( (_arg_0 Bool) (_arg_1 Bool)) Bool (xor _arg_1 _arg_0))"
    f = function_from_string(b_xor)
    assert f(True, False)
    assert not f(False, False)
    assert not f(True, True)
    assert f(False, True)

    b_not = "(define-fun f ((_arg_0 Bool)) Bool (not _arg_0))"
    f = function_from_string(b_not)
    assert not f(True)
    assert f(False)

    b_le = "(define-fun f ( (_arg_0 Int) (_arg_1 Int)) Bool (<= _arg_0 _arg_1))"
    f = function_from_string(b_le)
    assert not f(2, 1)
    assert f(1, 2)
    assert f(2, 2)


def test_str():
    str_len = "(define-fun f ( (_arg_0 String)) Int (str.len _arg_0 ))"
    f = function_from_string(str_len)
    assert f("True") == 4
    assert f("False") == 5

    str_int = "(define-fun f ( (_arg_0 String)) Int (str.to.int _arg_0 ))"
    f = function_from_string(str_int)
    assert f("13") == 13
    assert f("976") == 976

    str_str = "(define-fun f ( (_arg_0 Int)) String (int.to.str _arg_0 ))"
    f = function_from_string(str_str)
    assert f(13) == "13"
    assert f(976) == "976"

    str_at = "(define-fun f ( (_arg_0 String) (_arg_1 Int)) String (str.at _arg_0 _arg_1))"
    f = function_from_string(str_at)
    assert f("13", 1) == "3"
    assert f("abcdef", 5) == "f"

    str_concat = "(define-fun f ( (_arg_0 String) (_arg_1 String)) String (str.++ _arg_0 _arg_1))"
    f = function_from_string(str_concat)
    assert f("13", "14") == "1314"
    assert f("abc", "def") == "abcdef"

    str_cont = "(define-fun f ( (_arg_0 String) (_arg_1 String)) Bool (str.contains _arg_0 _arg_1))"
    f = function_from_string(str_cont)
    assert not f("a human", "fang")
    assert f("alphabet", "bet")

    str_pref = "(define-fun f ( (_arg_0 String) (_arg_1 String)) Bool (str.prefixof _arg_0 _arg_1))"
    f = function_from_string(str_pref)
    assert not f("flower", "coliflower")
    assert f("\\", "\\begin{document}")

    str_suff = "(define-fun f ( (_arg_0 String) (_arg_1 String)) Bool (str.suffixof _arg_0 _arg_1))"
    f = function_from_string(str_suff)
    assert f("flower", "coliflower")
    assert not f("\\", "\\begin{document}")

    str_ind = "(define-fun f ( (_arg_0 String) (_arg_1 String) (_arg_2 Int)) Int (str.indexof _arg_0 _arg_1 _arg_2))"
    f = function_from_string(str_ind)
    assert f("coliflower", "flower", 3) == 4
    assert f("an elephant", "an", 3) == 8

    str_rep = "(define-fun f ( (_arg_0 String) (_arg_1 String) (_arg_2 Int)) String (str.replace _arg_0 _arg_1 _arg_2))"
    f = function_from_string(str_rep)
    assert f("coliflower", "flower", "sion") == "colision"
    assert f("badiboo", "b", "") == "adiboo"
    assert f("okokok", "ok", "") == "okok"

    str_sub = "(define-fun f ( (_arg_0 String) (_arg_1 Int) (_arg_2 Int)) String (str.substr _arg_0 _arg_1 _arg_2))"
    f = function_from_string(str_sub)
    assert f("coliflower", 4, 6) == "flower"
    assert f("KaYaK", 1, 3) == "aYa"


def test_int():
    str_add = "(define-fun f ( (_arg_0 Int) (_arg_1 Int)) Int (+ _arg_0 _arg_1))"
    f = function_from_string(str_add)
    assert f(3, 4) == 7
    assert f(796, 731) == 1527

    str_mul = "(define-fun f ( (_arg_0 Int) (_arg_1 Int)) Int (* _arg_0 _arg_1))"
    f = function_from_string(str_mul)
    assert f(3, 4) == 12
    assert f(11, 11) == 121

    str_div = "(define-fun f ( (_arg_0 Int) (_arg_1 Int)) Int (/ _arg_0 _arg_1))"
    f = function_from_string(str_div)
    assert f(3, 4) == 0
    assert f(-1, 3) == 0
    assert f(-4, 3) == -1

    str_sub = "(define-fun f ( (_arg_0 Int) (_arg_1 Int)) Int (- _arg_0 _arg_1))"
    f = function_from_string(str_sub)
    assert f(3, 4) == -1
    assert f(-1, 3) == -4
    assert f(6854, 6853) == 1

    str_neg = "(define-fun f ( (_arg_0 Int) (_arg_1 Int)) Int (- _arg_0))"
    f = function_from_string(str_neg)
    assert f(3, 4) == -3
    assert f(-1, 3) == 1

    str_mod = "(define-fun f ( (_arg_0 Int) (_arg_1 Int)) Int (% _arg_0 _arg_1))"
    f = function_from_string(str_mod)
    assert f(3, 4) == 3
    assert f(-1, 3) == -1
    assert f(123, 23) == 8


def test_const():
    str_id_int = "(define-fun f ( (_arg_0 Int)) Int (_arg_0))"
    f = function_from_string(str_id_int)
    assert f(3) == 3
    assert f(-1) == -1

    str_const = "(define-fun f ( (_arg_0 Int)) Int (2))"
    f = function_from_string(str_const)
    assert f(3) == 2
    assert f(-1) == 2


def test_args():
    str_const = '(define-fun f ( (_arg_0 String)) String (str.++ _arg_0 " "))'
    f = function_from_string(str_const)
    assert f("a") == "a "


def tests():
    print("Testing...")
    test_bool()
    test_ite()
    test_str()
    test_int()
    test_const()
    print("All good!")


if __name__ == "__main__":
    tests()
