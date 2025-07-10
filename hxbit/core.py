from abc import ABC, abstractmethod
from io import BytesIO
from typing import Any, Dict, Union, BinaryIO, Literal, TypeVar, List
import struct
import inspect
from enum import Enum

T = TypeVar("T", bound="VarInt")


def hxbit_hash(name: str) -> int:
    """
    Reimplements the hxbit.Serializer.hash method - takes a string (fully qualified class name) and returns a hashed int.
    """
    v = 1
    for char in name:
        char_code = ord(char)
        v = v * 223 + char_code
        v &= 0xFFFFFFFF
        if v >= 0x80000000:
            v -= 0x100000000
    v &= 0x3FFFFFFF
    v = 1 + (v % 65423)
    return v


DEBUG = True


def tell(message: str | None = None) -> None:
    """
    Prints the current position in the file-like object.
    Useful for debugging deserialisation.
    """
    global DEBUG
    if not DEBUG:
        return
    frame = inspect.currentframe()
    assert frame is not None
    frame = frame.f_back
    assert frame is not None
    code = frame.f_code
    line_number = frame.f_lineno
    frame_locals = frame.f_locals
    if "f" in frame_locals:
        f = frame_locals["f"]
        print(
            f"DEBUG: {message if message else f'{code.co_filename}:{line_number}'}:      {hex(f.tell())}"
        )
    else:
        print("WARNING: tell() called without a file-like object in locals.")


class Serialisable(ABC):
    """
    Base class for all serialisable objects.
    """
    value: Any

    @abstractmethod
    def __init__(self) -> None:
        self.value = None

    @abstractmethod
    def deserialise(
        self, f: BinaryIO | BytesIO, *args: Any, **kwargs: Any
    ) -> "Serialisable":
        pass

    @abstractmethod
    def serialise(self) -> bytes:
        pass

    def __str__(self) -> str:
        try:
            return str(self.value)
        except AttributeError:
            return super().__repr__()

    def __repr__(self) -> str:
        try:
            return str(self.value)
        except AttributeError:
            return super().__repr__()

    def __eq__(self, other: object) -> Any:
        if not isinstance(other, Serialisable):
            return NotImplemented
        return self.value == other.value

    def __ne__(self, other: object) -> Any:
        if not isinstance(other, Serialisable):
            return NotImplemented
        return self.value != other.value

    def __lt__(self, other: object) -> Any:
        if not isinstance(other, Serialisable):
            return NotImplemented
        return self.value < other.value


class RawData(Serialisable):
    """
    A block of raw data.
    """
    value: bytes
    length: int

    def __init__(self, length: int):
        self.value = b""
        self.length = length

    def deserialise(self, f: BinaryIO | BytesIO) -> "RawData":
        self.value = f.read(self.length)
        return self

    def serialise(self) -> bytes:
        return self.value


class SerialisableInt(Serialisable):
    """
    Integer of the specified byte length.
    """
    value: int
    length: int
    byteorder: Literal["little", "big"]
    signed: bool

    def __init__(self) -> None:
        self.value = -1
        self.length = 4
        self.byteorder = "little"
        self.signed = False

    def deserialise(
        self,
        f: BinaryIO | BytesIO,
        length: int = 4,
        byteorder: Literal["little", "big"] = "little",
        signed: bool = False,
    ) -> "SerialisableInt":
        self.length = length
        self.byteorder = byteorder
        self.signed = signed
        bytes_read = f.read(length)
        if not bytes_read:
            self.value = 0
            return self
        self.value = int.from_bytes(bytes_read, byteorder, signed=signed)
        return self

    def serialise(self) -> bytes:
        return self.value.to_bytes(self.length, self.byteorder, signed=self.signed)


class SerialisableF64(Serialisable):
    """
    A standard 64-bit float.
    """
    value: float

    def __init__(self) -> None:
        self.value = 0.0

    def deserialise(self, f: BinaryIO | BytesIO) -> "SerialisableF64":
        self.value = struct.unpack("<d", f.read(8))[0]
        return self

    def serialise(self) -> bytes:
        return struct.pack("<d", self.value)


class VarInt(Serialisable):
    """
    Represents a variable-length integer using the hxbit serialization format.
    """
    value: int

    def __init__(self, value: int = 0):
        self.value = value

    def deserialise(self: T, f: BinaryIO | BytesIO) -> T:
        tag_byte = f.read(1)
        if not tag_byte:
            raise EOFError("Unexpected end of stream while reading VarInt tag.")

        tag = tag_byte[0]

        if tag == 0x80:
            payload_bytes = f.read(4)
            if len(payload_bytes) < 4:
                raise EOFError(
                    "Unexpected end of stream while reading 4-byte VarInt payload."
                )
            self.value = struct.unpack("<i", payload_bytes)[0]
        else:
            self.value = tag

        return self

    def serialise(self) -> bytes:
        if 0 <= self.value < 0x80:
            return bytes([self.value])
        else:
            marker = b"\x80"
            payload = struct.pack("<i", self.value)
            return marker + payload

    def __repr__(self) -> str:
        return f"VarInt({self.value})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, VarInt):
            return self.value == other.value
        if isinstance(other, int):
            return self.value == other
        return NotImplemented


class Resolvable(ABC):
    """
    Base class for resolvable references.
    """
    @abstractmethod
    def resolve(self, context: "HXSFile") -> Any:
        """
        Resolve this reference to a specific reference in the file.
        """
        pass

class ResolvableVarInt(VarInt, Resolvable, ABC):
    """
    Base class for resolvable VarInts. Call `resolve` to get a direct reference to the object it points to.
    """


class String(Serialisable):
    """
    Represents a string using the hxbit serialization format.
    """
    value: str | None

    def __init__(self, value: str | None = None):
        self.value = value

    def deserialise(self, f: BinaryIO | BytesIO) -> "String":
        length_prefix_varint = VarInt().deserialise(f)
        length_plus_one = length_prefix_varint.value

        if length_plus_one == 0:
            self.value = None
            return self

        string_byte_length = length_plus_one - 1

        if string_byte_length > 0:
            string_bytes = f.read(string_byte_length)
            if len(string_bytes) < string_byte_length:
                raise EOFError(
                    f"Expected {string_byte_length} string bytes, but got {len(string_bytes)}."
                )
            try:
                self.value = string_bytes.decode("utf-8")
            except UnicodeDecodeError as e:
                tell("UnicodeDecodeError: " + str(e))
                raise ValueError(
                    f"Failed to decode string bytes: {string_bytes!r}"
                ) from e
        else:
            self.value = ""

        return self

    def serialise(self) -> bytes:
        if self.value is None:
            return VarInt(0).serialise()

        string_bytes = self.value.encode("utf-8")
        length_plus_one = len(string_bytes) + 1
        prefix_bytes = VarInt(length_plus_one).serialise()

        return prefix_bytes + string_bytes

    def __repr__(self) -> str:
        return f"String({self.value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, String):
            return self.value == other.value
        if isinstance(other, str) or other is None:
            return self.value == other
        return NotImplemented


class ClassDef(Serialisable):
    """Represents a single class definition in the HXS header."""
    name: String
    clid: "CLID"
    crc32: SerialisableInt

    def __init__(self) -> None:
        self.name = String()
        self.clid = CLID()
        self.crc32 = SerialisableInt()
        self.crc32.length = 4

    def deserialise(self, f: BinaryIO | BytesIO) -> "ClassDef":
        self.clid.deserialise(f)
        self.crc32.deserialise(f, length=4, byteorder="little", signed=False)
        return self

    def serialise(self) -> bytes:
        return self.name.serialise() + self.clid.serialise() + self.crc32.serialise()

    def __repr__(self) -> str:
        return (
            f"ClassDef(name={self.name.value!r}, clid={self.clid.value}, "
            f"crc32=0x{self.crc32.value:08X})"
        )


class UID(ResolvableVarInt):
    """
    Represents a unique identifier (UID) to a specific class type in the data.
    """
    _resolved: "Schema | None"

    def __init__(self, value: int = 0):
        super().__init__(value)
        self._resolved = None
    
    def resolve(self, context: "HXSFile") -> "Schema | None":
        """Resolve this UID to its corresponding Schema."""
        if hasattr(context, 'schemas'):
            for schema in context.schemas:
                if schema.uid.value == self.value:
                    self._resolved = schema
                    return self._resolved
        return None
    
    @property
    def schema(self) -> "Schema | None":
        """Returns the resolved schema if available."""
        return self._resolved
    
    def __repr__(self) -> str:
        if self._resolved is not None:
            class_name = None
            if hasattr(self._resolved, 'clid') and self._resolved.clid._resolved:
                class_name = self._resolved.clid.class_name
            if class_name:
                return f"UID({self.value} -> Schema for {class_name})"
            return f"UID({self.value} -> Schema)"
        return f"UID({self.value})"


class CLID(Resolvable):
    """
    Represents a fixed 2-byte unsigned integer in big-endian order.
    """
    value: int
    _resolved: ClassDef | None

    def __init__(self, value: int = 0):
        if not (0 <= value <= 0xFFFF):
            raise ValueError(f"CLID must be in 0..65535, got {value}")
        self.value = value
        self._resolved = None

    def deserialise(self, f: BinaryIO | BytesIO) -> "CLID":
        data = f.read(2)
        if len(data) < 2:
            raise EOFError("Unexpected end of stream while reading CLID.")
        self.value = struct.unpack(">H", data)[0]
        return self

    def serialise(self) -> bytes:
        return struct.pack(">H", self.value)

    def resolve(self, context: "HXSFile") -> ClassDef | None:
        """Resolve this CLID to its corresponding ClassDef."""
        if hasattr(context, 'classdefs'):
            for classdef in context.classdefs:
                if classdef.clid.value == self.value:
                    self._resolved = classdef
                    return self._resolved
        return None
    
    @property
    def class_name(self) -> str | None:
        """Returns the class name if resolved, otherwise None."""
        if self._resolved:
            return self._resolved.name.value
        return None
    
    def __repr__(self) -> str:
        if self._resolved is not None:
            return f"CLID({self.value} -> {self._resolved.name.value})"
        elif self.class_name:
            return f"CLID({self.value} -> {self.class_name})"
        return f"CLID({self.value})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, CLID):
            return self.value == other.value
        if isinstance(other, int):
            return self.value == other
        return NotImplemented
    
class VarCLID(ResolvableVarInt):
    """
    Represents a variable-length CLID that can be resolved to a specific ClassDef.
    """
    _resolved: ClassDef | None

    def __init__(self, value: int = 0):
        super().__init__(value)
        self._resolved = None

    def resolve(self, context: "HXSFile") -> ClassDef | None:
        """Resolve this VarCLID to its corresponding ClassDef."""
        if hasattr(context, 'classdefs'):
            for classdef in context.classdefs:
                if classdef.clid.value == self.value:
                    self._resolved = classdef
                    return self._resolved
        return None

    @property
    def class_name(self) -> str | None:
        """Returns the class name if resolved, otherwise None."""
        if self._resolved:
            return self._resolved.name.value
        return None

class Boolean(Serialisable):
    """
    Represents a boolean value in the hxbit serialization format.
    """
    value: bool

    def __init__(self, value: bool = False):
        self.value = value

    def deserialise(self, f: BinaryIO | BytesIO) -> "Boolean":
        byte = f.read(1)
        if not byte:
            raise EOFError("Unexpected end of stream while reading Boolean.")
        self.value = byte[0] != 0
        return self

    def serialise(self) -> bytes:
        return bytes([1 if self.value else 0])

    def __repr__(self) -> str:
        return f"Boolean({self.value})"


class PropTypeDesc(Serialisable):
    class Kind(Enum):
        PInt = 0
        PFloat = 1
        PBool = 2
        PString = 3
        PBytes = 4
        PSerializable = 5
        PEnum = 6
        PMap = 7
        PArray = 8
        PObj = 9
        PAlias = 10
        PVector = 11
        PNull = 12
        PUnknown = 13
        PDynamic = 14
        PInt64 = 15
        PFlags = 16
        PCustom = 17
        PSerInterface = 18
        PStruct = 19
        PAliasCDB = 20
        PNoSave = 21
    
    value: int
    kind: Kind

    def __init__(self, value: int = 0):
        super().__init__()
        self.value = value
        self.kind = PropTypeDesc.Kind(value)

    def deserialise(self, f: BinaryIO | BytesIO) -> "PropTypeDesc":
        byte = f.read(1)
        if not byte:
            raise EOFError("Unexpected end of stream while reading PropTypeDesc kind.")

        stream_value = byte[0]

        if stream_value == 0:
            raise ValueError("This should be handled by the PropType deserializer.")

        haxe_index = stream_value - 1
        self.value = haxe_index
        self.kind = PropTypeDesc.Kind(self.value)
        return self

    def serialise(self) -> bytes:
        value_to_serialise = self.value + 1
        return bytes([value_to_serialise])

    def __repr__(self) -> str:
        return f"PropTypeDesc({self.kind.name})"


class PropTypeDef(Serialisable, ABC):
    @abstractmethod
    def __repr__(self) -> str:
        pass


class Empty(PropTypeDef):
    def __init__(self) -> None:
        pass

    def deserialise(self, f: BinaryIO | BytesIO) -> "Empty":
        return self

    def serialise(self) -> bytes:
        return b""

    def __repr__(self) -> str:
        return "None"


class NameDef(PropTypeDef):
    name: String

    def __init__(self) -> None:
        self.name = String()

    def deserialise(self, f: BinaryIO | BytesIO) -> "NameDef":
        self.name.deserialise(f)
        return self

    def serialise(self) -> bytes:
        return self.name.serialise()

    def __repr__(self) -> str:
        return f"NameDef(name={self.name.value!r})"


class MapDef(PropTypeDef):
    key_type: "PropType"
    value_type: "PropType"

    def __init__(self) -> None:
        self.key_type = PropType()
        self.value_type = PropType()

    def deserialise(self, f: BinaryIO | BytesIO) -> "MapDef":
        self.key_type.deserialise(f)
        self.value_type.deserialise(f)
        return self

    def serialise(self) -> bytes:
        return self.key_type.serialise() + self.value_type.serialise()

    def __repr__(self) -> str:
        return f"MapDef(key_type={self.key_type}, value_type={self.value_type})"


class TypeDef(PropTypeDef):
    type: "PropType"

    def __init__(self) -> None:
        self.type = PropType()

    def deserialise(self, f: BinaryIO | BytesIO) -> "TypeDef":
        self.type.deserialise(f)
        return self

    def serialise(self) -> bytes:
        return self.type.serialise()

    def __repr__(self) -> str:
        return f"TypeDef(type={self.type})"
    
    def __str__(self) -> str:
        return self.__repr__()


class ObjFieldDef(Serialisable):
    name: String | None
    type: "PropType | None"
    opt: Boolean

    def __init__(self) -> None:
        self.name = None
        self.type = None
        self.opt = Boolean()

    def deserialise(self, f: BinaryIO | BytesIO) -> "ObjFieldDef":
        fbits = VarInt().deserialise(f)

        if fbits.value == 0:
            self.opt.deserialise(f)
            return self

        val = fbits.value - 1

        if val & 1:
            self.name = String().deserialise(f)

        if val & 2:
            prop_type_val = PropType().deserialise(f)
            self.type = None if prop_type_val.kind is None else prop_type_val

        self.opt.deserialise(f)

        return self

    def serialise(self) -> bytes:
        return b"".join([
            VarInt((1 if self.name else 0) + (2 if self.type else 0) + 1).serialise(),
            self.name.serialise() if self.name else b"",
            self.type.serialise() if self.type else b"",
            self.opt.serialise() if self.opt else Boolean(False).serialise()
        ])

    def __repr__(self) -> str:
        return (
            f"ObjFieldDef(name={self.name.value if self.name else 'None'}, "
            f"type={self.type}, opt={self.opt.value})"
        )


class ObjDef(PropTypeDef):
    fields: List[ObjFieldDef]

    def __init__(self) -> None:
        self.fields = []

    def deserialise(self, f: BinaryIO | BytesIO) -> "ObjDef":
        nfields_plus_1 = VarInt().deserialise(f)
        if nfields_plus_1.value > 1:
            num_fields = nfields_plus_1.value - 1
            for _ in range(num_fields):
                field_def = ObjFieldDef().deserialise(f)
                self.fields.append(field_def)
        return self

    def serialise(self) -> bytes:
        return b"".join([
            VarInt(len(self.fields) + 1).serialise(),
            b"".join(field.serialise() for field in self.fields if field is not None)
        ])

    def __repr__(self) -> str:
        return f"ObjDef(fields={self.fields})"


class Struct(PropTypeDef):
    name: String
    fields: List[Dict[str, Union[String, "PropType"]]]

    def __init__(self) -> None:
        self.name = String()
        self.fields = []

    def deserialise(self, f: BinaryIO | BytesIO) -> "Struct":
        self.name.deserialise(f)
        nfields = VarInt().deserialise(f).value
        tell(f"Struct '{self.name.value}' has {nfields} fields.")
        for _ in range(nfields):
            field_name = String().deserialise(f)
            field_type = PropType().deserialise(f)
            self.fields.append({"name": field_name, "type": field_type})
        return self

    def serialise(self) -> bytes:
        nfields = VarInt(len(self.fields)).serialise()
        fields_data = b"".join(
            field["name"].serialise() + field["type"].serialise() # type: ignore
            for field in self.fields
        )
        return self.name.serialise() + nfields + fields_data

    def __repr__(self) -> str:
        fields_repr = ", ".join(
            f"{field['name'].value!r}: {field['type']}" for field in self.fields # type: ignore
        )
        return f"Struct(name={self.name.value!r}, fields=[{fields_repr}])"


class PropType(Serialisable):
    MAP: Dict[PropTypeDesc.Kind, type[PropTypeDef]] = {
        PropTypeDesc.Kind.PInt: Empty,
        PropTypeDesc.Kind.PFloat: Empty,
        PropTypeDesc.Kind.PBool: Empty,
        PropTypeDesc.Kind.PString: Empty,
        PropTypeDesc.Kind.PBytes: Empty,
        PropTypeDesc.Kind.PSerializable: NameDef,
        PropTypeDesc.Kind.PEnum: NameDef,
        PropTypeDesc.Kind.PMap: MapDef,
        PropTypeDesc.Kind.PArray: TypeDef,
        PropTypeDesc.Kind.PObj: ObjDef,
        PropTypeDesc.Kind.PAlias: TypeDef,
        PropTypeDesc.Kind.PVector: TypeDef,
        PropTypeDesc.Kind.PNull: TypeDef,
        PropTypeDesc.Kind.PUnknown: Empty,
        PropTypeDesc.Kind.PDynamic: Empty,
        PropTypeDesc.Kind.PInt64: Empty,
        PropTypeDesc.Kind.PFlags: TypeDef,
        PropTypeDesc.Kind.PCustom: Empty,
        PropTypeDesc.Kind.PSerInterface: NameDef,
        PropTypeDesc.Kind.PStruct: Struct,
        PropTypeDesc.Kind.PAliasCDB: TypeDef,
        PropTypeDesc.Kind.PNoSave: TypeDef,
    }

    kind: PropTypeDesc | None
    defn: PropTypeDef | None

    def __init__(self) -> None:
        self.kind = None
        self.defn = None

    def deserialise(self, f: BinaryIO | BytesIO) -> "PropType":
        kind_byte_val = f.read(1)
        if not kind_byte_val:
            raise EOFError("Unexpected EOF while reading PropType kind byte.")

        kind_byte = kind_byte_val[0]

        if kind_byte == 0:
            return self

        haxe_index = kind_byte - 1
        self.kind = PropTypeDesc(haxe_index)

        if self.kind.kind in self.MAP:
            self.defn = self.MAP[self.kind.kind]()
            self.defn.deserialise(f)
        else:
            raise ValueError(f"Unknown PropTypeDesc kind: {self.kind.value}")
        return self

    def serialise(self) -> bytes:
        if self.kind is None:
            return b"\x00"

        kind_bytes = self.kind.serialise()
        defn_bytes = self.defn.serialise() if self.defn else b""
        return kind_bytes + defn_bytes

    def __repr__(self) -> str:
        if self.kind is None:
            return "PropType(null)"
        return f"PropType(kind={self.kind.kind.name}, defn={self.defn})"
    
    def pprint(self, indent: int = 0, context: "HXSFile | None" = None) -> str:
        """Returns a pretty-printed representation of the PropType with proper indentation."""
        if self.kind is None:
            return "null"
        
        kind_name = self.kind.kind.name
        
        if isinstance(self.defn, Empty):
            return kind_name
        elif isinstance(self.defn, NameDef):
            return f"{kind_name}<{self.defn.name.value}>"
        elif isinstance(self.defn, TypeDef):
            nested = self.defn.type.pprint(indent + 1, context=context)
            return f"{kind_name}<{nested}>"
        elif isinstance(self.defn, MapDef):
            key_type = self.defn.key_type.pprint(indent + 1, context=context)
            value_type = self.defn.value_type.pprint(indent + 1, context=context)
            return f"{kind_name}<{key_type}, {value_type}>"
        elif isinstance(self.defn, ObjDef):
            if not self.defn.fields:
                return f"{kind_name}{{}}"
            
            spaces = "  " * (indent + 1)
            fields_str = ""
            for field in self.defn.fields:
                field_name = field.name.value if field.name else "<unnamed>"
                field_type = field.type.pprint(indent + 1, context=context) if field.type else "<untyped>"
                optional = " (optional)" if field.opt.value else ""
                fields_str += f"\n{spaces}{field_name}: {field_type}{optional}"
            
            return f"{kind_name}{{{fields_str}\n{'  ' * indent}}}"
        elif isinstance(self.defn, Struct):
            if not self.defn.fields:
                return f"{kind_name}<{self.defn.name.value}>{{}}"
            
            spaces = "  " * (indent + 1)
            fields_str = ""
            for field in self.defn.fields:
                field_name = field["name"].value # type: ignore
                field_type = field["type"].pprint(indent + 1, context=context) # type: ignore
                fields_str += f"\n{spaces}{field_name}: {field_type}"
            
            return f"{kind_name}<{self.defn.name.value}>{{{fields_str}\n{'  ' * indent}}}"
        else:
            return f"{kind_name}<{self.defn}>"


class Schema(Serialisable):
    uid: UID
    clid: VarInt
    field_names: List[String]
    field_types: List[PropType]

    def __init__(self) -> None:
        self.uid = UID()
        self.clid = VarInt()
        self.field_names = []
        self.field_types = []

    def deserialise(self, f: BinaryIO | BytesIO) -> "Schema":
        self.uid.deserialise(f)
        self.clid.deserialise(f)

        nfield_names = VarInt().deserialise(f)
        if nfield_names.value > 1:
            tell(f"Schema has {nfield_names.value - 1} field names")
            for _ in range(nfield_names.value - 1):
                tell("Deserialising field name")
                field_name = String().deserialise(f)
                self.field_names.append(field_name)

        nfield_types = VarInt().deserialise(f)
        if nfield_types.value > 1:
            for _ in range(nfield_types.value - 1):
                field_type = PropType().deserialise(f)
                self.field_types.append(field_type)

        return self

    def serialise(self) -> bytes:
        return b"".join(
            [
                self.uid.serialise(),
                self.clid.serialise(),
                VarInt(len(self.field_names) + 1).serialise(),
                b"".join(field_name.serialise() for field_name in self.field_names),
                VarInt(len(self.field_types) + 1).serialise(),
                b"".join(field_type.serialise() for field_type in self.field_types),
            ]
        )

    def __repr__(self) -> str:
        return (
            f"Schema(uid={self.uid}, "
            f"field_names={self.field_names}, "
            f"field_types={self.field_types})"
        )

    def pprint(self, context: "HXSFile | None" = None) -> str:
        """Returns a nicely formatted representation of the schema."""
        uid_str = str(self.uid.value)
        clid_str = str(self.clid.value)
        
        # Resolve UID and CLID if context is provided
        if context:
            if hasattr(self.uid, 'resolve'):
                resolved_uid = self.uid.resolve(context)
                if resolved_uid:
                    uid_str = f"{self.uid.value} (resolved)"
            
            # Resolve CLID to get class name
            resolved_clid = None
            for classdef in context.classdefs:
                if classdef.clid.value == self.clid.value:
                    resolved_clid = classdef
                    break
            
            if resolved_clid:
                clid_str = f"{self.clid.value} -> {resolved_clid.name.value}"
        
        lines = [f"Schema(uid={uid_str}, clid={clid_str})"]
        
        if self.field_names:
            lines.append("  Fields:")
            for i, (name, field_type) in enumerate(zip(self.field_names, self.field_types)):
                field_name = name.value
                type_str = field_type.pprint(indent=2, context=context)
                lines.append(f"    {field_name}: {type_str}")
        else:
            lines.append("  No fields")
        
        return "\n".join(lines)


class HXSFile(Serialisable):
    magic: String
    version: SerialisableInt
    classdefs: List[ClassDef]
    schema_size: VarInt
    schemas: List[Schema]
    objects: Dict[int, Schema]
    
    def __init__(self) -> None:
        self.magic = String()
        self.version = SerialisableInt()
        self.version.length = 1
        self.classdefs = []
        self.schema_size = VarInt()
        self.schemas = []
        self.objects = {}

    def deserialise(self, f: BinaryIO | BytesIO) -> "HXSFile":
        self.magic.deserialise(f)
        assert self.magic.value == "HXS", (
            f"Invalid magic! Expected 'HXS', got {self.magic.value!r}"
        )

        self.version.deserialise(f, length=1)
        assert self.version.value == 1, (
            f"Unsupported version! Expected 1, got {self.version.value}"
        )

        while True:
            name = String().deserialise(f)
            if name.value is None:
                break

            cdef = ClassDef()
            cdef.name = name
            cdef.deserialise(f)
            self.classdefs.append(cdef)

        self.schema_size.deserialise(f)

        if self.schema_size.value > 0:
            schemas_start_pos = f.tell()
            schemas_end_pos = schemas_start_pos + self.schema_size.value

            while f.tell() < schemas_end_pos:
                schema = Schema().deserialise(f)
                self.schemas.append(schema)
                self.objects[schema.uid.value] = schema

            if f.tell() != schemas_end_pos:
                actual_pos = f.tell()
                tell(f"Schema section size mismatch: expected to end at {hex(schemas_end_pos)}, but ended at {hex(actual_pos)}")

        return self

    def serialise(self) -> bytes:
        return b"".join([
            String("HXS").serialise(), # self.magic.serialise()
            self.version.serialise(),
            b"".join(cdef.serialise() for cdef in self.classdefs),
            b"\x00", # End of class defs marker
            self.schema_size.serialise(),
            b"".join(schema.serialise() for schema in self.schemas)
        ])

    @classmethod
    def from_path(cls, path: str) -> "HXSFile":
        with open(path, "rb") as f:
            instance = cls().deserialise(f)
        return instance

    @classmethod
    def from_bytes(cls, data: bytes) -> "HXSFile":
        with BytesIO(data) as f:
            instance = cls().deserialise(f)
        return instance

    def pprint_schemas(self) -> str:
        """Returns a nicely formatted representation of all schemas."""
        if not self.schemas:
            return "No schemas found"
        
        # Resolve all resolvable references first
        self._resolve_all_references()
        
        lines = [f"Found {len(self.schemas)} schemas:"]
        lines.append("")
        
        for schema in self.schemas:
            lines.append(schema.pprint(context=self))
            lines.append("")
        
        return "\n".join(lines)
    
    def _resolve_all_references(self) -> None:
        """Resolve all resolvable references in the file."""
        # Resolve class definitions
        for classdef in self.classdefs:
            if hasattr(classdef.clid, 'resolve'):
                classdef.clid.resolve(self)
        
        # Resolve schemas
        for schema in self.schemas:
            if hasattr(schema.uid, 'resolve'):
                schema.uid.resolve(self)
            if hasattr(schema.clid, 'resolve'):
                # VarInt doesn't have resolve, but VarCLID does.
                # The type of schema.clid is VarInt, but it might be a subclass.
                if isinstance(schema.clid, Resolvable):
                    schema.clid.resolve(self)
            
            # Resolve field types recursively
            for field_type in schema.field_types:
                self._resolve_prop_type(field_type)
    
    def _resolve_prop_type(self, prop_type: PropType) -> None:
        """Recursively resolve all resolvable references in a PropType."""
        if prop_type.defn is None:
            return
        
        if isinstance(prop_type.defn, TypeDef):
            self._resolve_prop_type(prop_type.defn.type)
        elif isinstance(prop_type.defn, MapDef):
            self._resolve_prop_type(prop_type.defn.key_type)
            self._resolve_prop_type(prop_type.defn.value_type)
        elif isinstance(prop_type.defn, ObjDef):
            for field in prop_type.defn.fields:
                if field.type:
                    self._resolve_prop_type(field.type)
        elif isinstance(prop_type.defn, Struct):
            for field in prop_type.defn.fields:
                # The value is a PropType, so we can resolve it.
                self._resolve_prop_type(field["type"]) # type: ignore

    def pprint_classdefs(self) -> str:
        """Returns a nicely formatted representation of all class definitions."""
        if not self.classdefs:
            return "No class definitions found"
        
        lines = [f"Found {len(self.classdefs)} class definitions:"]
        lines.append("")
        
        for classdef in self.classdefs:
            lines.append(f"  {classdef.name.value} (CLID: {classdef.clid.value}, CRC32: 0x{classdef.crc32.value:08X})")
        
        return "\n".join(lines)
