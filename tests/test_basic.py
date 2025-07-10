import pytest
from hxbit import HXSFile
from glob import glob

test_files = glob("tests/hxs/*.bin")


@pytest.mark.parametrize("path", test_files)
def test_reser_basic(path: str):
    with open(path, "rb") as f:
        code = HXSFile().deserialise(f)
        f.seek(0)
        if not f.read() == code.serialise():
            # find 1st non-matching byte
            ser = code.serialise()
            f.seek(0)
            c = 0
            msg = ""
            while True:
                a = f.read(1)
                b = ser[c : c + 1]
                t = f.tell() - 1
                if a != b:
                    msg = f"First mismatch at {hex(t)}: {a!r} != {b!r}"
                    print(msg)
                    break
                c += 1
            assert False, "Failed matching reser: " + msg
