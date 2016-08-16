### Copyright (C) 2011-2015 Peter Williams <pwil3058@gmail.com>
###
### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.
###
### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.
###
### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

'''Encode/decode binary bytes to/from text strings using git's coding'''

import collections
import re

class Error(Exception): pass
class ParseError(Error): pass
class RangerError(Error): pass

ENCODE = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~"
assert len(set(ENCODE)) == 85
DECODE = { chr(ENCODE[index]) : index for index in range(len(ENCODE)) }
assert len(DECODE) == 85

Encoding = collections.namedtuple("Encoding", ["string", "size"])

def is_consistent(encoding):
    if len(encoding.string) % 5 != 0:
        return False
    max_bytes = (len(encoding.string) // 5) * 4
    return (max_bytes >= encoding.size) and (max_bytes - encoding.size < 4)

# bytes() in Encoding() out
def encode(data):
    index = 0
    estring = bytes()
    size = len(data)
    while index < size:
        acc = 0
        for cnt in (24, 16, 8, 0):
            acc |= data[index] << cnt
            index += 1
            if index == size:
                break
        snippet = bytes()
        for _cnt in range(5):
            val = acc % 85
            acc //= 85
            snippet = bytes([ENCODE[val]]) + snippet
        estring += snippet
    return Encoding(estring.decode("utf8"), size)

_MAX_VAL = 0xFFFFFFFF

# Encoding() in bytes() out
def decode(encoding):
    assert is_consistent(encoding)
    data = bytearray(encoding.size)
    dindex = 0
    sindex = 0
    while dindex < encoding.size:
        acc = 0
        for _cnt in range(5):
            try:
                acc = acc * 85 + DECODE[encoding.string[sindex]]
            except KeyError:
                raise ParseError(_("Illegal git base 85 character"))
            sindex += 1
        if acc > _MAX_VAL:
            raise RangeError(_("{0} too big.").format(acc))
        for _cnt in range(4):
            if dindex == encoding.size:
                break
            acc = (acc << 8) | (acc >> 24)
            data[dindex] = acc % 256
            dindex += 1
    return data

# test over a range of data sizes
_TESTDATA = b"uioyf2oyqo;3nhi8uydjauyo98ua 54\000jhkh\034hh;kjjh"
for i in range(10):
    assert decode(encode(_TESTDATA[i:])) == _TESTDATA[i:]

# Now encode/decode into/from text lines
# Each 5-byte sequence of base-85 encodes up to 4 bytes,
# and we would limit the patch line to 66 characters,
# so one line can fit up to 13 groups that would decode
# to 52 bytes max.  The length byte "A"-"Z" corresponds
# to 1-26 bytes, and "a"-"z" corresponds to 27-52 bytes.
MAX_BYTES_PER_LINE = 52
def encode_size(size):
    assert size <= MAX_BYTES_PER_LINE
    return chr((size + ord("A") - 1) if size <=26 else (size + ord("a") - 26 - 1))

def decode_size(char):
    if "A" <= char and char <= "Z":
        return ord(char) - ord("A") + 1
    elif "a" <= char and char <= "z":
        return ord(char) - ord("a") + 27
    raise ValueError(_("decode_size: argument must be in [a-zA-Z]"))

def encode_to_lines(data, max_line_length=1 + (MAX_BYTES_PER_LINE // 4) * 5):
    assert max_line_length > 5
    bytes_per_line = min(((max_line_length - 1) // 5) * 4, MAX_BYTES_PER_LINE)
    index = 0
    lines = []
    while index < len(data):
        encoding = encode(data[index:index + bytes_per_line])
        lines.append("{0}{1}\n".format(encode_size(encoding.size), encoding.string))
        index += bytes_per_line
    return lines

def decode_line(line):
    return decode(Encoding(line[1:].rstrip(), decode_size(line[0])))

def decode_lines(lines):
    data = bytes()
    for line in lines:
        data += decode_line(line)
    return data

LINE_CRE = re.compile("^([a-zA-Z])(([0-9a-zA-Z" + re.sub("-", "", str(ENCODE[62:])) + "-]{5})+)$")

assert decode_lines(encode_to_lines(_TESTDATA * 10)) == _TESTDATA * 10
