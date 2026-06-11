"""
Generates hxbit type shims from HashLink bytecode.

For every class in a set of HXS save files that has an array-of-anonymous-object
field (PArray<PObj{...}>), this resolves the anonymous object's field types by
finding the class's `unserialize` function in the game's bytecode and inspecting
the HashLink `Virtual` type(s) referenced by that function's registers.

Usage:
    uv run python scripts/gen_shims.py <path-to-hlboot.dat> [hxs-files...]

If no hxs files are given, the bundled Dead Cells test saves are used.
"""

import sys
import pprint
from typing import Dict, Any, FrozenSet, List, Tuple

from crashlink.core import Bytecode, Type, Virtual

from hxbit.core import HXSFile, PropTypeDesc, TypeDef, ObjDef
from hxbit.shims import deadcells

DEFAULT_SAVES = [
    "tests/hxs/dcsteam/Bit_00_S_User_steam.bin",
    "tests/hxs/dcsteam/Bit_01_S_Game.bin",
    "tests/hxs/dcsteam/Bit_02_S_UserAndGameData.bin",
]

# Maps HashLink register/field type kinds to hxbit shim type names.
HL_KIND_TO_SHIM_TYPE = {
    Type.Kind.I32: "Int",
    Type.Kind.I64: "Int",
    Type.Kind.F32: "Float",
    Type.Kind.F64: "Float",
    Type.Kind.BOOL: "Bool",
    Type.Kind.BYTES: "String",
}


def find_anon_array_fields(save_paths: list[str]) -> Dict[str, Dict[str, FrozenSet[str]]]:
    """
    Returns {class_name: {field_name: frozenset(anon object field names)}}
    for every PArray<PObj{...}> field found across the given save files.
    """
    found: Dict[str, Dict[str, FrozenSet[str]]] = {}
    for path in save_paths:
        hxs = HXSFile.from_path(path)
        for cdef, schema in zip(hxs.classdefs, hxs.schemas):
            class_name = cdef.name.value
            if class_name is None:
                continue
            for field_name, field_type in zip(schema.field_names, schema.field_types):
                if not (field_type.kind and field_type.kind.kind == PropTypeDesc.Kind.PArray):
                    continue
                if not isinstance(field_type.defn, TypeDef):
                    continue
                inner = field_type.defn.type
                if not (inner.kind and inner.kind.kind == PropTypeDesc.Kind.PObj):
                    continue
                if not isinstance(inner.defn, ObjDef):
                    continue
                names = frozenset(
                    f.name.value for f in inner.defn.fields if f.name is not None
                )
                if not names:
                    continue
                found.setdefault(class_name, {})[field_name.value] = names
    return found


def build_virtual_index(code: Bytecode) -> Dict[FrozenSet[str], List[Tuple[str, Virtual]]]:
    """
    Scans every `unserialize` function in the bytecode and returns a map of
    frozenset(field names) -> [(owning class name, Virtual type definition), ...].

    This is global (not scoped to a particular class) so that fields inherited
    from a base class (e.g. `Entity.receivedAffixes`) can be resolved even when
    the concrete subclass doesn't define its own `unserialize`.
    """
    index: Dict[FrozenSet[str], List[Tuple[str, Virtual]]] = {}
    for func in code.functions:
        proto = code.get_proto_for(func.findex.value)
        if proto is None:
            continue
        if proto.name.resolve(code) != "unserialize":
            continue
        full_name = code.full_func_name(func)
        class_name = full_name.rsplit(".", 1)[0]
        for reg_type_idx in func.regs:
            typ = reg_type_idx.resolve(code)
            if typ.kind.value != Type.Kind.VIRTUAL.value:
                continue
            defn = typ.definition
            assert isinstance(defn, Virtual)
            names = frozenset(f.name.resolve(code) for f in defn.fields)
            index.setdefault(names, []).append((class_name, defn))
    return index


def field_to_shim(code: Bytecode, field_type: Type, field_name: str) -> Dict[str, Any]:
    kind = Type.Kind(field_type.kind.value)

    if kind == Type.Kind.OBJ:
        obj_name = field_type.definition.name.resolve(code)  # type: ignore[union-attr]
        if obj_name == "String":
            return {"type": "String"}
        return {"type": "Serializable", "name": obj_name}
    if kind == Type.Kind.ENUM:
        enum_name = field_type.definition.name.resolve(code)  # type: ignore[union-attr]
        return {"type": "Enum", "name": enum_name}
    if kind == Type.Kind.NULL:
        inner = field_type.definition.type.resolve(code)  # type: ignore[union-attr]
        return {"type": "Null", "payload": field_to_shim(code, inner, field_name)}

    try:
        return {"type": HL_KIND_TO_SHIM_TYPE[kind]}
    except KeyError:
        raise NotImplementedError(
            f"No shim type mapping for HashLink type kind {kind.name} "
            f"(field '{field_name}')"
        )


def virtual_to_obj_shim(code: Bytecode, virtual: Virtual) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for field in virtual.fields:
        name = field.name.resolve(code)
        field_type = field.type.resolve(code)
        fields[name] = field_to_shim(code, field_type, name)
    return {"type": "Obj", "fields": fields}


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path-to-hlboot.dat> [hxs-files...]")
        sys.exit(1)

    bytecode_path = sys.argv[1]
    save_paths = sys.argv[2:] or DEFAULT_SAVES

    print(f"Scanning {len(save_paths)} save file(s) for anonymous array fields...")
    anon_fields = find_anon_array_fields(save_paths)
    for class_name, fields in anon_fields.items():
        for field_name, names in fields.items():
            print(f"  {class_name}.{field_name}: {{{', '.join(sorted(names))}}}")

    print(f"\nLoading bytecode from {bytecode_path}...")
    code = Bytecode.from_path(bytecode_path)

    print("Resolving Virtual types from unserialize() functions...")
    virtual_index = build_virtual_index(code)

    generated: Dict[str, Any] = {}
    for class_name, fields in anon_fields.items():
        for field_name, names in fields.items():
            matches = virtual_index.get(names)
            if not matches:
                print(
                    f"  WARNING: no matching Virtual{{{', '.join(sorted(names))}}} "
                    f"for {class_name}.{field_name}"
                )
                continue
            owner_class, virtual = matches[0]
            if len(matches) > 1:
                shapes = {tuple((f.name.resolve(code), f.type.resolve(code).kind.value) for f in v.fields) for _, v in matches}
                if len(shapes) > 1:
                    owners = ", ".join(c for c, _ in matches)
                    print(
                        f"  WARNING: ambiguous Virtual{{{', '.join(sorted(names))}}} "
                        f"for {class_name}.{field_name} (candidates: {owners}); using {owner_class}"
                    )
            try:
                generated[f"{class_name}.{field_name}"] = {
                    "type": "Array",
                    "payload": virtual_to_obj_shim(code, virtual),
                }
            except NotImplementedError as e:
                print(f"  WARNING: skipping {class_name}.{field_name}: {e}")

    print("\nGenerated shims:")
    pprint.pprint(generated, sort_dicts=False)

    print("\nDiff against hxbit/shims/deadcells.py:")
    any_diff = False
    for key, value in generated.items():
        existing = deadcells.TYPES.get(key)
        if existing != value:
            any_diff = True
            print(f"  MISMATCH for {key}:")
            print(f"    existing:  {existing}")
            print(f"    generated: {value}")
    for key in deadcells.TYPES:
        if key not in generated:
            any_diff = True
            print(f"  MISSING from generated output: {key}")
    if not any_diff:
        print("  (matches existing shims exactly)")


if __name__ == "__main__":
    main()
