"""LithTech REZ (RezMgr Version 1) の一覧・抜き出し。

使い方:
  python rez.py list  <REZ>             一覧
  python rez.py extract <REZ> <出力先> [絞り込み語]
"""
import os
import struct
import sys

HDR = 127


def read_header(f):
    f.seek(HDR)
    (ver, root_pos, root_size, root_time, next_write, time_, lk, ldn, lrn, lc) = struct.unpack('<10I', f.read(40))
    sorted_ = f.read(1)[0]
    return dict(ver=ver, root_pos=root_pos, root_size=root_size, next_write=next_write,
                lk=lk, ldn=ldn, lrn=lrn, lc=lc, sorted=sorted_)


def cstr(buf, i):
    j = buf.index(b'\0', i)
    return buf[i:j].decode('latin-1'), j + 1


def walk(f, pos, size, path=''):
    f.seek(pos)
    buf = f.read(size)
    i = 0
    while i < len(buf):
        typ, p, s, t = struct.unpack_from('<4I', buf, i)
        i += 16
        if typ == 1:
            name, i = cstr(buf, i)
            yield from walk(f, p, s, path + name + '/')
            f.seek(0)
        else:
            rid, ext, nkeys = struct.unpack_from('<I4sI', buf, i)
            i += 12
            name, i = cstr(buf, i)
            desc, i = cstr(buf, i)
            i += 4 * nkeys
            ext = ext.rstrip(b'\0')[::-1].decode('latin-1')
            yield dict(path=path, name=name, ext=ext, pos=p, size=s, id=rid, desc=desc, time=t)


def entries(fn):
    with open(fn, 'rb') as f:
        h = read_header(f)
        return list(walk(f, h['root_pos'], h['root_size']))


def full(e):
    return e['path'] + e['name'] + ('.' + e['ext'] if e['ext'] else '')


def main():
    cmd, fn = sys.argv[1], sys.argv[2]
    es = entries(fn)
    if cmd == 'list':
        for e in es:
            print(f"{e['pos']:10d} {e['size']:9d} {e['id']:6d} {full(e)}")
    elif cmd == 'extract':
        out = sys.argv[3]
        flt = sys.argv[4].lower() if len(sys.argv) > 4 else None
        with open(fn, 'rb') as f:
            for e in es:
                p = full(e)
                if flt and flt not in p.lower():
                    continue
                dst = os.path.join(out, p)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                f.seek(e['pos'])
                with open(dst, 'wb') as g:
                    g.write(f.read(e['size']))
        print(len(es), 'entries')


if __name__ == '__main__':
    main()
