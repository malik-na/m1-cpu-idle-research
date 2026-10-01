#!/usr/bin/env python3
"""Read-only IMG4/LZFSE inspection of an on-disk kernelcache.

Writes only explicitly selected output files. Never opens live kernel memory,
loads a kernel extension, calls an IOKit user client, or changes a boot setting.
An optional fileset entry view preserves original file offsets and replaces
only the copied container header with the selected embedded Mach-O header.
This view is for static analysis, not execution or booting.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import uuid


def tlv(data, offset):
    tag, size = data[offset:offset + 2]
    offset += 2
    if size & 0x80:
        count = size & 0x7f
        if not 0 < count <= 8:
            raise ValueError("Unsupported ASN.1 length")
        size = int.from_bytes(data[offset:offset + count], "big")
        offset += count
    end = offset + size
    if end > len(data):
        raise ValueError("ASN.1 object exceeds input")
    return tag, offset, end


def payload(data):
    tag, start, end = tlv(data, 0)
    if tag != 0x30:
        raise ValueError("Expected IMG4/IM4P ASN.1 sequence")
    _, a, b = tlv(data, start)
    if data[a:b] == b"IMG4":
        _, start, end = tlv(data, b)
        _, a, b = tlv(data, start)
    if data[a:b] != b"IM4P":
        raise ValueError("Expected IM4P")
    for _ in range(2):
        _, a, b = tlv(data, b)
    tag, a, b = tlv(data, b)
    if tag != 4 or not data[a:b].startswith(b"bvx2"):
        raise ValueError("Expected unencrypted LZFSE kernel payload")
    return data[a:b]


def commands(data, base=0):
    if struct.unpack_from("<I", data, base)[0] != 0xfeedfacf:
        raise ValueError("Expected little-endian 64-bit Mach-O")
    count, size = struct.unpack_from("<II", data, base + 16)
    cursor, limit = base + 32, base + 32 + size
    for _ in range(count):
        cmd, length = struct.unpack_from("<II", data, cursor)
        if length < 8 or cursor + length > limit:
            raise ValueError("Malformed Mach-O command")
        yield cmd, cursor, length
        cursor += length


def image_uuid(data, base=0):
    for cmd, offset, length in commands(data, base):
        if cmd == 0x1b:
            return str(uuid.UUID(bytes=data[offset + 8:offset + 24])).upper()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernelcache", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--entry", help="Optional exact LC_FILESET_ENTRY identifier")
    parser.add_argument("--entry-output", type=Path)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    if bool(args.entry) != bool(args.entry_output):
        parser.error("--entry and --entry-output must be supplied together")
    raw = args.kernelcache.read_bytes()
    compressed = payload(raw)
    limit = 256 * 1024 * 1024
    library = ctypes.CDLL("/usr/lib/libcompression.dylib")
    decode = library.compression_decode_buffer
    decode.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                       ctypes.c_size_t, ctypes.c_void_p, ctypes.c_int]
    decode.restype = ctypes.c_size_t
    destination = ctypes.create_string_buffer(limit)
    size = decode(destination, limit, compressed, len(compressed), None, 0x801)
    if size == 0 or size == limit:
        raise ValueError("Decompression failed or exceeded 256 MiB bound")
    data = destination.raw[:size]
    entries = []
    for cmd, offset, length in commands(data):
        if cmd == 0x80000035:
            vmaddr, fileoff, nameoff, _ = struct.unpack_from("<QQII", data, offset + 8)
            name = data[offset + nameoff:offset + length].split(b"\0", 1)[0].decode()
            entries.append({"name": name, "vmaddr": hex(vmaddr),
                            "fileoff": fileoff, "uuid": image_uuid(data, fileoff)})
    args.output.write_bytes(data)
    if args.entry:
        entry = next(x for x in entries if x["name"] == args.entry)
        start = entry["fileoff"]
        header_size = 32 + struct.unpack_from("<I", data, start + 20)[0]
        if header_size >= min(x["fileoff"] for x in entries):
            raise ValueError("Entry header would overwrite embedded data")
        with args.entry_output.open("wb") as stream:
            stream.write(data)
            stream.seek(0)
            stream.write(data[start:start + header_size])
    report = {"input": str(args.kernelcache),
              "input_sha256": hashlib.sha256(raw).hexdigest(),
              "compressed_size": len(compressed), "decompressed_size": size,
              "output_sha256": hashlib.sha256(data).hexdigest(),
              "fileset_uuid": image_uuid(data), "entries": entries}
    formatted = json.dumps(report, indent=2) + "\n"
    if args.metadata:
        args.metadata.write_text(formatted)
    print(formatted)


if __name__ == "__main__":
    main()
