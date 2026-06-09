import argparse
import sys
from typing import NoReturn
from .core import HXSFile
from . import debug
from .gui import launch_gui

def main() -> NoReturn:
    parser = argparse.ArgumentParser(
        description="hxbit.py: A reimplementation of Haxe's hxbit in Python for manipulating serialised Haxe classes."
    )
    parser.add_argument("path", nargs="?", help="The path to the hxbit-serialised data to use.")
    parser.add_argument("-s", "--shims", default="deadcells", help="The type shim library to use to fill in missing types in serialised data. Defaults to information for Dead Cells' save file format.")
    parser.add_argument("-d", "--debug", help="Enable debug logging", action="store_true")
    parser.add_argument("-g", "--gui", help="Launch the graphical editor.", action="store_true")
    parser.add_argument("--diagnostics", help="Print parser diagnostics after loading.", action="store_true")
    args = parser.parse_args()
    
    if args.debug:
        debug.DEBUG = True

    if args.gui or args.path is None:
        launch_gui(initial_path=args.path, initial_shims=args.shims)
        raise SystemExit(0)
    
    file = HXSFile(shims=args.shims)
    assert args.path is not None
    with open(args.path, "rb") as f:
        file.deserialise(f)

    if args.diagnostics or file.object_parse_error is not None or file.unresolved_clids:
        print(file.pprint_unresolved_clids(), file=sys.stderr)
        if file.object_parse_error is not None:
            print("", file=sys.stderr)
            print(f"Object parse error: {file.object_parse_error}", file=sys.stderr)
    
    raise SystemExit(0)


if __name__ == "__main__":
    main()
