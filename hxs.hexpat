#include <std/io.pat>

struct VarInt {
    u8 tag;
    if (this.tag == 0x80)
        s32 value_full;
    s32 value = this.tag == 0x80 ? this.value_full : this.tag;
};

struct String {
    VarInt length;
    if (length.value > 1) {
        char value[length.value - 1];
    }
};

struct ClassDef {
    String name;
    be u16 clid;
    u32 crc;
};

struct Header {
    String magic;
    u8 version;
};

using Type;

struct MapDef {
    Type key_type;
    Type value_type;
};

struct ObjField {
    VarInt fbits;

    if (fbits.value > 0) {
        if (fbits.value - 1 & 1) { // bit 0 for 'name'
            String name;
        }
        if (fbits.value - 1 & 2) { // bit 1 for 'type'
            Type type;
        }
    }
    
    u8 opt;
};

struct ObjDef {
    VarInt nfields; // This is (number of fields + 1)
    if (nfields.value > 1) {
        ObjField fields[nfields.value - 1];
    }
};

struct StructField {
    String name;
    Type type;
};

struct StructDef {
    String name;
    VarInt nfields;
    if (nfields.value > 0)
        StructField fields[nfields.value];
};


enum Kind : u8 {
    PInt = 1,
    PFloat,
    PBool,
    PString,
    PBytes,
    PSerializable,
    PEnum,
    PMap,
    PArray,
    PObj,
    PAlias,
    PVector,
    PNull,
    PUnknown,
    PDynamic,
    PInt64,
    PFlags,
    PCustom,
    PSerInterface,
    PStruct,
    PAliasCDB,
    PNoSave,
};

struct Type {
    Kind kind;
    
    if (this.kind == Kind::PSerializable ||
        this.kind == Kind::PEnum ||
        this.kind == Kind::PSerInterface) {
        String name;
    }
    else if (this.kind == Kind::PMap) {
        MapDef map_def;
    }
    else if (this.kind == Kind::PObj) {
        std::print("obj!");
        ObjDef obj_def;
    }
    else if (this.kind == Kind::PStruct) {
        StructDef struct_def;
    }
    else if (this.kind == Kind::PArray ||
             this.kind == Kind::PAlias ||
             this.kind == Kind::PVector ||
             this.kind == Kind::PNull ||
             this.kind == Kind::PFlags ||
             this.kind == Kind::PAliasCDB ||
             this.kind == Kind::PNoSave) {
        Type type;
    }
};

struct Schema {
    VarInt uid;
    VarInt clid;
    VarInt nnames;
    String names[nnames.value - 1];
    VarInt ntypes;
    Type types[ntypes.value - 1];
    
};

struct File {
    Header header;
    ClassDef defs[10];
    String pad;
    VarInt schemaSize;
    u64 schemaStart = $;
    Schema schema[while($ < schemaStart + schemaSize.value)];
};

File file @0x0;