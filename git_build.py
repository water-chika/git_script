import subprocess
import pathlib

def build():
    subprocess.run([
        'cmake', '-S', '.', '-B', 'build'
        ])
    subprocess.run([
        'cmake', '--build', 'build'
        ])
    return [
            pathlib.Path('build/bin/test-backends-ops').Absolute()
            ]

def main():
    out = subprocess.run([
        'git', 'rev-parse', 'HEAD'
        ], capture_output=True, encoding='utf-8')
    commit = out.stdout
    cache_dir = pathlib.Path('/mnt/builds/llama.cpp')
    cache = cache_dir / commit
    if not cache.exist():
        cached_files = build()
        for file in cached_files:
            file.move(cache_dir)
    cache.copy_into('build/bin')

    pass
if __name__ == '__main__':
    main()
