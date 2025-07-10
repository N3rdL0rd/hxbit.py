import argparse
from typing import NoReturn


def main() -> NoReturn:
    parser = argparse.ArgumentParser(
        description="hxbit.py: A reimplementation of Haxe's hxbit in Python for manipulating serialised Haxe classes."
    )
    args = parser.parse_args()
    raise SystemExit(0)


if __name__ == "__main__":
    main()
