import subprocess
import pathlib
from git_repo import load_config

def build():
    subprocess.run([
        'cmake', '-S', '.', '-B', 'build'
        ])
    subprocess.run([
        'cmake', '--build', 'build'
        ])

def git_build():
    out = subprocess.run([
        'git', 'rev-parse', 'HEAD'
        ], capture_output=True, encoding='utf-8')
    commit = out.stdout
    config = load_config()
    cache_dir = pathlib.Path(config['cache_dir']).absolute()
    need_cached_files = config['need_cached_files']
    cache = cache_dir / commit
    if not cache.exist():
        build()
        for file in need_cached_files:
            file.move(cache_dir)
    cache.copy_into('build/bin')

def main():
    pass

if __name__ == '__main__':
    main()
