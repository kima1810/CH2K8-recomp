"""Bounded readers for the GPU-backed Xbox and PS3 scorebug scene layouts."""
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def take(data, offset, length):
    require(0 <= offset <= len(data) and 0 <= length <= len(data)-offset,
            'Component extent exceeds file')
    return data[offset:offset+length]


def U(data, offset):
    return struct.unpack('>I', take(data, offset, 4))[0]


def R(data, offset):
    return offset + struct.unpack('>i', take(data, offset, 4))[0] - 1


def string(data, offset):
    end = offset
    while take(data, end, 2) != b'\0\0':
        end += 2
    return data[offset:end].decode('utf-16-be')


def meshes(data, ps3=False):
    result = []
    table = R(data, 0x48)
    count = U(data, 0x44)
    require(0 < count < 100, 'Unsupported mesh count')
    for i in range(count):
        part = table + i * 176
        descriptor = R(data, part+0x88)
        vertices = U(data, descriptor+(16 if ps3 else 8))
        stream_count = U(data, descriptor+20) if ps3 else U(data, descriptor+12) >> 16
        require(0 < vertices < 100000 and 0 < stream_count < 8,
                'Unsupported stream dimensions')
        streams = []
        for j in range(stream_count):
            entry = descriptor + (28 if ps3 else 24) + j * 16
            stride, length = U(data, entry+4), U(data, entry+8)
            start = U(data, entry+12)-1
            require(length == vertices*stride, 'Stream count/stride mismatch')
            streams.append((start, stride, length))
        declarations = R(data, part+0x9c)
        attribute_count = U(data, part+(0x94 if ps3 else 0x98))
        require(0 < attribute_count <= 32, 'Unsupported declaration count')
        attributes = {}
        for j in range(attribute_count):
            entry = declarations + j * 64
            semantic = U(data, entry)
            code = take(data, entry+8, 8)
            attributes[semantic] = (code[2], code[1], code)
        result.append(dict(part=part, name=string(data, R(data, part)),
                           count=vertices, streams=streams, attrs=attributes))
    return result
