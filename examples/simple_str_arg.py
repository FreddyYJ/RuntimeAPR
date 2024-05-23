my_int = 1


def foo(name: str):
    global my_int
    my_int += name.count("a")

    if name == "halo":
        raise ValueError
    return my_int


from runtimeapr.loop import except_handler


def main():
    for n in ["okok", "pasokok", "aaaaaaa", "halo"]:
        try:
            print(foo(n))
        except Exception as _e:
            except_handler(_e)


if __name__ == "__main__":
    main()
