"""Xbox TXTR base-level DDS bridge. All descriptor fields are big-endian.

Only validated 2D BC base levels are exported. Higher original mips remain in
the preserved data. Unknown layouts are never guessed. Tiling follows the runtime's
GetTiledOffset2D (BSD-licensed Xenia/ReXGlue); see its LICENSE.
"""
import struct

FORMATS = {18: (b'DXT1', 8), 19: (b'DXT3', 16), 20: (b'DXT5', 16), 49: (b'ATI2', 16), 59: (b'ATI1', 8)}


def tiled_offset(x, y, pitch, log_bpp):
    pitch = (pitch + 31) & ~31
    macro = ((x >> 5) + (y >> 5) * (pitch >> 5)) << (log_bpp + 7)
    micro = ((x & 7) + ((y & 14) << 2)) << log_bpp
    offset = macro + ((micro & ~15) << 1) + (micro & 15) + ((y & 1) << 4)
    return ((offset & ~511) << 3) + ((y & 16) << 7) + ((offset & 448) << 2) + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6) + (offset & 63)


def describe(cpu, gpu=None):
    if len(cpu) < 0xAC:
        raise ValueError('short Xbox TXTR descriptor')
    words = struct.unpack_from('>6I', cpu, 0x94)
    a, b, size, _, lod, dimension = words
    fmt = b & 63
    if a & 3 != 2 or fmt not in FORMATS or (dimension >> 9) & 3 != 1:
        raise ValueError('unsupported Xbox texture format/dimension')
    if (b >> 10) & 1 or (size >> 26):
        raise ValueError('stacked Xbox texture not yet supported')
    width, height = (size & 8191) + 1, ((size >> 13) & 8191) + 1
    if width%4 or height%4:
        raise ValueError('non-block-aligned BC texture requires host decompression')
    pitch = ((a >> 22) & 511) * 32
    start = 0x6C + struct.unpack_from('>i', cpu, 0x6C)[0] - 1
    length = struct.unpack_from('>I', cpu, 0x70)[0]
    # [CONFIRMED] Inline legalpage textures use a relative pointer to the
    # 4-KiB-aligned tiled payload. Split-block resources require separate proof.
    if dimension & 0x800 and min(width,height) <= 16:
        raise ValueError('base level is in a packed mip tail')
    # [CONFIRMED by descriptor/payload bounds and DDS round trips] Split TXTR
    # CPU records retain an unresolved +0x6C pointer (value 1); their second IFF
    # component begins at the base-level GPU data.
    if gpu is not None:
        # [CONFIRMED, Xbox SCNE corpus] Embedded descriptors store a GPU
        # component offset + 1 here; standalone records store 1 (offset zero).
        start=struct.unpack_from('>I',cpu,0x6C)[0]-1
    if (gpu is None and start < 0xAC) or start + length > len(gpu if gpu is not None else cpu) or pitch < width:
        raise ValueError('unsupported split or out-of-bounds Xbox texture payload')
    return dict(width=width, height=height, pitch=pitch, start=start,
                length=length, tiled=bool(a >> 31), endian=(b >> 6) & 3,
                format=fmt, mips=((lod>>6)&15)+1)


def swap(data, endian):
    if endian == 0:
        return data
    unit = 2 if endian == 1 else 4
    if len(data) % unit:
        raise ValueError('unaligned texture endianness unit')
    if endian in (1, 2):
        return b''.join(data[i:i+unit][::-1] for i in range(0, len(data), unit))
    return b''.join(data[i+2:i+4] + data[i:i+2] for i in range(0, len(data), 4))


def addresses(info):
    _, bpp = FORMATS[info['format']]
    w, h = (info['width'] + 3) // 4, (info['height'] + 3) // 4
    pitch = info['pitch'] // 4
    for y in range(h):
        for x in range(w):
            off = tiled_offset(x, y, pitch, bpp.bit_length()-1) if info['tiled'] else (y*pitch+x)*bpp
            if off + bpp > info['length']:
                raise ValueError('texture address exceeds payload')
            yield off


def export_dds(cpu, gpu=None):
    info = describe(cpu,gpu)
    fourcc, bpp = FORMATS[info['format']]
    source=gpu if gpu is not None else cpu
    payload = b''.join(swap(source[info['start']+off:info['start']+off+bpp], info['endian']) for off in addresses(info))
    header = bytearray(128)
    header[:4] = b'DDS '
    struct.pack_into('<7I', header, 4, 124, 0x81007, info['height'], info['width'], len(payload), 0, 1)
    struct.pack_into('<II4s', header, 76, 32, 4, fourcc)
    struct.pack_into('<I', header, 108, 0x1000)
    return bytes(header) + payload


def apply_dds(cpu, dds):
    info = describe(cpu)
    fourcc, bpp = FORMATS[info['format']]
    if len(dds) < 128 or dds[:4] != b'DDS ' or struct.unpack_from('<I', dds, 4)[0] != 124:
        raise ValueError('invalid DDS header')
    h, w = struct.unpack_from('<II', dds, 12)
    mips = struct.unpack_from('<I', dds, 28)[0]
    pf_size, flags = struct.unpack_from('<II', dds, 76)
    caps2 = struct.unpack_from('<I', dds, 112)[0]
    if (w, h) != (info['width'], info['height']) or mips not in (0, 1):
        raise ValueError('DDS dimensions/mips must match the Xbox texture; upscaling requires native GPU replacements')
    if pf_size != 32 or flags != 4 or dds[84:88] != fourcc or caps2:
        raise ValueError('DDS must retain the original BC format and be a single 2D texture')
    expected = ((w+3)//4)*((h+3)//4)*bpp
    if len(dds) != 128 + expected:
        raise ValueError('DDS payload length mismatch')
    out = bytearray(cpu)
    for i, off in enumerate(addresses(info)):
        out[info['start']+off:info['start']+off+bpp] = swap(dds[128+i*bpp:128+(i+1)*bpp], info['endian'])
    return bytes(out)
