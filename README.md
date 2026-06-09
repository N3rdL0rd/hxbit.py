# hxbit.py

A reimplementation of Haxe's hxbit in Python for manipulating serialised Haxe classes.

## GUI

Launch the GUI editor with:

```powershell
python -m hxbit --gui
```

Or open a file directly:

```powershell
python -m hxbit --gui tests/hxs/dcsteam/Bit_00_S_User_steam.bin
```

The GUI can inspect schemas, show parsed object data, edit parsed scalar fields, and save the result.
If typed object parsing fails for a file, the GUI still opens it and can save it losslessly using the preserved raw object payload.
