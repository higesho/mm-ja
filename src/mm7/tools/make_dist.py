"""配布物を作る: dist/MightAndMagic7_JP.zip（dinput.dll、MM7JP/mm7jp.tsv、説明書.txt）。
原作の文は入れない（訳だけ。DLL が元の表に当てる）。"""
import os, sys, zipfile, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')


def main():
    subprocess.run([sys.executable, '-I', os.path.join(HERE, 'collect.py')], check=True)
    out = os.path.join(ROOT, 'dist')
    os.makedirs(out, exist_ok=True)
    stage = os.path.join(out, 'stage')
    subprocess.run([sys.executable, '-I', os.path.join(HERE, 'build.py'), os.path.join(stage, 'MM7JP')], check=True)
    z = os.path.join(out, 'MightAndMagic7_JP.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as f:
        f.write(os.path.join(ROOT, 'dll', 'dinput.dll'), 'dinput.dll')
        f.write(os.path.join(stage, 'MM7JP', 'mm7jp.tsv'), 'MM7JP/mm7jp.tsv')
        f.write(os.path.join(ROOT, 'dist_files', '説明書.txt'), '説明書.txt')
    print(z, os.path.getsize(z), 'バイト')


if __name__ == '__main__':
    main()
