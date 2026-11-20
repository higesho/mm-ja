# -*- coding: utf-8 -*-
"""create_project で作った VS プロジェクトに Ogg Vorbis（libvorbis）を足す（CD 版の声 MUSIC\\xeenNN.ogg 用）。

python -I tools/add_vorbis.py build/msvc_pub build/msvc_test
部品（ogg.lib・vorbis.lib・vorbisfile.lib と include/ogg・include/vorbis）は build/libs に置いておく
（vcpkg の libvorbis:x64-windows-static-md で作ったもの）。何度当てても同じ結果になる。
"""
import io, os, re, sys


def rw(path, fn):
    s = io.open(path, encoding='utf-8-sig', newline='').read()
    t = fn(s)
    if t != s:
        bom = io.open(path, 'rb').read(3) == b'\xef\xbb\xbf'
        io.open(path, 'w', encoding='utf-8-sig' if bom else 'utf-8', newline='').write(t)
        print('直した:', path)


for d in sys.argv[1:]:
    def proj(s):
        if 'audio\\decoders\\vorbis.cpp' not in s:
            a = '<ClCompile Include="..\\scummvm-src\\audio\\decoders\\xan_dpcm.cpp" />'
            i = s.index(a)
            nl = '\r\n' if '\r\n' in s else '\n'
            indent = re.search(r'([ \t]*)' + re.escape(a), s).group(1)
            s = s[:i + len(a)] + nl + indent + '<ClCompile Include="..\\scummvm-src\\audio\\decoders\\vorbis.cpp" />' + s[i + len(a):]
        s = re.sub(r'(<AdditionalDependencies>)(?!vorbisfile\.lib)', r'\1vorbisfile.lib;vorbis.lib;ogg.lib;', s)
        return s
    rw(os.path.join(d, 'scummvm.vcxproj'), proj)

    for p in os.listdir(d):
        if p.startswith('ScummVM_Global') and p.endswith('.props'):
            rw(os.path.join(d, p), lambda s: s if 'USE_VORBIS;' in s else
               s.replace('<PreprocessorDefinitions>', '<PreprocessorDefinitions>USE_VORBIS;', 1))
