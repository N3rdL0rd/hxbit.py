import argparse
from typing import NoReturn
from .core import HXSFile
from . import debug

def main() -> NoReturn:
    parser = argparse.ArgumentParser(
        description="hxbit.py: A reimplementation of Haxe's hxbit in Python for manipulating serialised Haxe classes."
    )
    parser.add_argument("path", help="The path to the hxbit-serialised data to use.")
    parser.add_argument("-s", "--shims", default="deadcells", help="The type shim library to use to fill in missing types in serialised data. Defaults to information for Dead Cells' save file format.")
    parser.add_argument("-d", "--debug", help="Enable debug logging", action="store_true")
    args = parser.parse_args()
    
    if args.debug:
        debug.DEBUG = True
    
    file = HXSFile(shims=args.shims)
    with open(args.path, "rb") as f:
        file.deserialise(f)
    
    raise SystemExit(0)


if __name__ == "__main__":
    main()
