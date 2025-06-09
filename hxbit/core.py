
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Any, Dict, Union, BinaryIO, Literal, TypeVar, List
import struct
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


class Serialisable(ABC):
    """
    Base class for all serialisable objects.
    """

    @abstractmethod
    def __init__(self) -> None:
        self.value: Any = None

    @abstractmethod
    def deserialise(self, f: BinaryIO | BytesIO, *args: Any, **kwargs: Any) -> "Serialisable":
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

    def __init__(self, length: int):
        self.value: bytes = b""
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

    def __init__(self) -> None:
        self.value: int = -1
        self.length = 4
        self.byteorder: Literal["little", "big"] = "little"
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
        bytes = f.read(length)
        if all(b == 0 for b in bytes):
            self.value = 0
            return self
        while bytes[-1] == 0:
            bytes = bytes[:-1]
        self.value = int.from_bytes(bytes, byteorder, signed=signed)
        return self

    def serialise(self) -> bytes:
        return self.value.to_bytes(self.length, self.byteorder, signed=self.signed)


class SerialisableF64(Serialisable):
    """
    A standard 64-bit float.
    """

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

    The format is optimized for small, non-negative integers:
    - Values in [0, 127] are encoded as a single byte.
    - All other integer values are encoded as a 5-byte sequence:
      a marker byte (0x80) followed by the standard 4-byte (32-bit)
      signed little-endian representation of the integer.
    """

    def __init__(self, value: int = 0):
        """Initializes the VarInt with an integer value."""
        self.value: int = value

    def deserialise(self: T, f: BinaryIO | BytesIO) -> T:
        """
        Reads a hxbit-formatted VarInt from a file-like object and updates self.value.
        """
        # Read the first byte, which is either the value or a marker.
        tag_byte = f.read(1)
        if not tag_byte:
            raise EOFError("Unexpected end of stream while reading VarInt tag.")
        
        tag = tag_byte[0]

        # Case 1: 5-byte format (marker 0x80 + 4-byte s32le)
        if tag == 0x80:
            payload_bytes = f.read(4)
            if len(payload_bytes) < 4:
                raise EOFError("Unexpected end of stream while reading 4-byte VarInt payload.")
            # Unpack as signed 32-bit little-endian integer ('<i')
            self.value = struct.unpack('<i', payload_bytes)[0]
        # Case 2: Single-byte format
        else:
            self.value = tag
            
        return self

    def serialise(self) -> bytes:
        """
        Encodes the integer value into its hxbit-formatted byte representation.

        Returns:
            A bytes object with the serialized VarInt.
        """
        # Case 1: Single-byte format for small, non-negative integers
        if 0 <= self.value < 0x80:
            return bytes([self.value])
        
        # Case 2: 5-byte format for all other integers
        else:
            # Marker byte (0x80) + signed 32-bit little-endian payload ('<i')
            marker = b'\x80'
            payload = struct.pack('<i', self.value)
            return marker + payload

    def __repr__(self) -> str:
        """Provides a developer-friendly representation of the object."""
        return f"VarInt({self.value})"

    def __eq__(self, other) -> bool:
        """Allows comparison with other VarInt objects or raw integers."""
        if isinstance(other, VarInt):
            return self.value == other.value
        if isinstance(other, int):
            return self.value == other
        return NotImplemented

class String(Serialisable):
    """
    Represents a string using the hxbit serialization format.
    """

    def __init__(self, value: str | None = None):
        """Initializes the String with a str or None value."""
        self.value: str | None = value

    def deserialise(self, f: BinaryIO | BytesIO) -> "String":
        """
        Reads a hxbit-formatted String from a file-like object and updates self.value.
        """
        length_prefix_varint = VarInt().deserialise(f)
        length_plus_one = length_prefix_varint.value

        if length_plus_one == 0:
            self.value = None
            return self

        string_byte_length = length_plus_one - 1

        if string_byte_length > 0:
            string_bytes = f.read(string_byte_length)
            if len(string_bytes) < string_byte_length:
                raise EOFError(f"Expected {string_byte_length} string bytes, but got {len(string_bytes)}.")
            self.value = string_bytes.decode('utf-8')
        else:
            self.value = ""
            
        return self

    def serialise(self) -> bytes:
        """
        Encodes the string value into its hxbit-formatted byte representation.

        Returns:
            A bytes object with the serialized String.
        """
        if self.value is None:
            return VarInt(0).serialise()

        string_bytes = self.value.encode('utf-8')
        
        length_plus_one = len(string_bytes) + 1
        prefix_bytes = VarInt(length_plus_one).serialise()

        return prefix_bytes + string_bytes

    def __repr__(self) -> str:
        """Provides a developer-friendly representation of the object."""
        return f"String({self.value!r})"

    def __eq__(self, other) -> bool:
        """Allows comparison with other String objects or raw str/None."""
        if isinstance(other, String):
            return self.value == other.value
        if isinstance(other, str) or other is None:
            return self.value == other
        return NotImplemented

class ClassDef(Serialisable):
    """Represents a single class definition in the HXS header."""
    def __init__(self) -> None:
        self.name = String()
        self.clid = SerialisableInt()
        self.clid.length = 2
        self.clid.byteorder = 'big'
        self.crc32 = SerialisableInt()
        self.crc32.length = 4

    def deserialise(self, f: BinaryIO | BytesIO) -> "ClassDef":
        """Deserialises the full class definition from the stream."""
        self.clid.deserialise(f, length=2, byteorder='big', signed=False)
        self.crc32.deserialise(f, length=4, byteorder='little', signed=False)
        return self
    
    def serialise(self) -> bytes:
        return self.name.serialise() + self.clid.serialise() + self.crc32.serialise()
    
    def __repr__(self) -> str:
        return (f"ClassDef(name={self.name.value!r}, clid={self.clid.value}, "
                f"crc32=0x{self.crc32.value:08X})")

class UID(VarInt):
    """
    Represents a unique identifier (UID) to a specific class type in the data.
    """

    def __init__(self, value: int = 0):
        super().__init__(value)

    def __repr__(self) -> str:
        return f"UID({self.value})"
    
class CLID(VarInt):
    """
    Represents a class identifier (CLID) to a specific class type in the data.
    """

    def __init__(self, value: int = 0):
        super().__init__(value)

    def __repr__(self) -> str:
        return f"CLID({self.value})"

class Boolean(Serialisable):
    """
    Represents a boolean value in the hxbit serialization format.
    """

    def __init__(self, value: bool = False):
        self.value: bool = value

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

# enum PropTypeDesc<PropType> {
# 	PInt;
# 	PFloat;
# 	PBool;
# 	PString;
# 	PBytes;
# 	PSerializable( name : String );
# 	PEnum( name : String );
# 	PMap( k : PropType, v : PropType );
# 	PArray( k : PropType );
# 	PObj( fields : Array<{ name : String, type : PropType, opt : Bool }> );
# 	PAlias( k : PropType );
# 	PVector( k : PropType );
# 	PNull( t : PropType );
# 	PUnknown;
# 	PDynamic;
# 	PInt64;
# 	PFlags( t : PropType );
# 	PCustom;
# 	PSerInterface( name : String );
# 	PStruct( name : String, fields : Array<{ name : String, type : PropType }> );
# 	PAliasCDB( k : PropType );
# 	PNoSave( k : PropType );
# }

class PropTypeDesc(VarInt):
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
    
    def __init__(self, value: int = 0):
        super().__init__(value)
        self.kind: PropTypeDesc.Kind = PropTypeDesc.Kind(value)
    
    def deserialise(self, f: BinaryIO | BytesIO) -> "PropTypeDesc":
        super().deserialise(f)
        self.kind = PropTypeDesc.Kind(self.value)
        return self
    
    def serialise(self) -> bytes:
        return super().serialise()

class PropTypeDef(Serialisable):
    """
    Property type definition base class.
    """

class Empty(PropTypeDef):
    """
    Represents an empty property type definition.
    """
    
    def __init__(self) -> None:
        pass

    def deserialise(self, f: BinaryIO | BytesIO) -> "Empty":
        return self

    def serialise(self) -> bytes:
        return b""
    
class NameDef(PropTypeDef):
    """
    Represents a named property type definition.
    """
    
    def __init__(self) -> None:
        self.name = String()

    def deserialise(self, f: BinaryIO | BytesIO) -> "NameDef":
        self.name.deserialise(f)
        return self

    def serialise(self) -> bytes:
        return self.name.serialise()
    
class MapDef(PropTypeDef):
    """
    Represents a map property type definition.
    """
    
    def __init__(self) -> None:
        self.key_type = PropType()
        self.value_type = PropType()

    def deserialise(self, f: BinaryIO | BytesIO) -> "MapDef":
        self.key_type.deserialise(f)
        self.value_type.deserialise(f)
        return self

    def serialise(self) -> bytes:
        return self.key_type.serialise() + self.value_type.serialise()

class TypeDef(PropTypeDef):
    """
    Represents a property type definition that has a single type.
    """
    
    def __init__(self) -> None:
        self.type = PropType()

    def deserialise(self, f: BinaryIO | BytesIO) -> "TypeDef":
        self.type.deserialise(f)
        return self

    def serialise(self) -> bytes:
        return self.type.serialise()

class Obj(PropTypeDef):
    """
    Represents an object property type definition.
    """
    
    def __init__(self) -> None:
        self.fields: List[Dict[str, Union[String, PropType]]] = []

    def deserialise(self, f: BinaryIO | BytesIO) -> "Obj":
        nfields = VarInt().deserialise(f).value
        for _ in range(nfields):
            field_name = String().deserialise(f)
            field_type = PropType().deserialise(f)
            self.fields.append({"name": field_name, "type": field_type})
        return self

    def serialise(self) -> bytes:
        nfields = VarInt(len(self.fields)).serialise()
        fields_data = b"".join(
            field["name"].serialise() + field["type"].serialise() for field in self.fields
        )
        return nfields + fields_data
    
class Struct(PropTypeDef):
    """
    Represents a struct property type definition.
    """
    
    def __init__(self) -> None:
        self.name = String()
        self.fields: List[Dict[str, Union[String, PropType]]] = []

    def deserialise(self, f: BinaryIO | BytesIO) -> "Struct":
        self.name.deserialise(f)
        nfields = VarInt().deserialise(f).value
        for _ in range(nfields):
            field_name = String().deserialise(f)
            field_type = PropType().deserialise(f)
            self.fields.append({"name": field_name, "type": field_type})
        return self

    def serialise(self) -> bytes:
        nfields = VarInt(len(self.fields)).serialise()
        fields_data = b"".join(
            field["name"].serialise() + field["type"].serialise() for field in self.fields
        )
        return self.name.serialise() + nfields + fields_data

class PropType(Serialisable):
    """
    Represents a property type.
    """
    
    defn: PropTypeDef
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
        PropTypeDesc.Kind.PObj: Obj,
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

    def __init__(self) -> None:
        self.kind = PropTypeDesc()
        self.defn = Empty()
    
    def deserialise(self, f: BinaryIO | BytesIO) -> "PropType":
        self.kind.deserialise(f)
        val = PropTypeDesc.Kind(self.kind.value)
        print(hex(f.tell()), f"Deserialising PropTypeDesc kind: {val.name}")
        if val in self.MAP:
            self.defn = self.MAP[val]()
            self.defn.deserialise(f)
        else:
            raise ValueError(f"Unknown PropTypeDesc kind: {self.kind.value}")
        return self
    
    def serialise(self) -> bytes:
        kind_bytes = self.kind.serialise()
        defn_bytes = self.defn.serialise()
        return kind_bytes + defn_bytes

class Schema(Serialisable):
    """
    Represents a serialised instance of the Schema class - which stores information about the classes in the hxbit data.
    """
    
    def __init__(self) -> None:
        self.uid = SerialisableInt()
        self.uid.length = 4
        self.clid = CLID()
        self.is_final = Boolean()
        self.nfield_names = VarInt()
        self.field_names: List[String] = []
        self.nfield_types = VarInt()
        self.field_types: List[PropType] = []
        
    def deserialise(self, f: BinaryIO | BytesIO) -> "Schema":
        self.uid.deserialise(f, length=4, byteorder='little', signed=False)
        self.clid.deserialise(f)
        self.is_final.deserialise(f)
        self.nfield_names.deserialise(f)
        for _ in range(self.nfield_names.value - 1):
            field_name = String().deserialise(f)
            self.field_names.append(field_name)
        self.nfield_types.deserialise(f)
        for _ in range(self.nfield_types.value):
            field_type = PropType().deserialise(f)
            self.field_types.append(field_type)
        return self
    
    def serialise(self) -> bytes:
        pass # TODO
    
    def __repr__(self) -> str:
        return (f"Schema(uid={self.uid}, clid={self.clid}, "
                f"is_final={self.is_final.value}, "
                f"nfield_names={self.nfield_names.value}, "
                f"field_names={self.field_names})")

class HXSFile(Serialisable):
    """
    Represents a serialised hxbit file - with the 'HXS' magic.
    """
    
    def __init__(self) -> None:
        self.magic = String()
        self.version = SerialisableInt()
        self.version.length = 1
        self.classdefs: List[ClassDef] = []
        self.schema_size = VarInt()
        self.schemas: List[Schema] = []
        
    def deserialise(self, f: BinaryIO | BytesIO) -> "HXSFile":
        self.magic.deserialise(f)
        assert self.magic.value == 'HXS', f"Invalid magic! Expected 'HXS', got {self.magic.value!r}"
        
        self.version.deserialise(f, length=1)
        assert self.version.value == 1, f"Unsupported version! Expected 1, got {self.version.value}"
        
        while True:
            name = String().deserialise(f)
            if name.value is None:
                break # terminated by null string
            
            cdef = ClassDef()
            cdef.name = name
            cdef.deserialise(f)
            self.classdefs.append(cdef)
        
        self.schema_size = VarInt().deserialise(f)
        schema = Schema().deserialise(f)
        self.schemas.append(schema)
    
            
        return self
    
    def serialise(self) -> bytes:
        # TODO
        return b""