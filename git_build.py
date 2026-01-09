#!/usr/bin/env python

import subprocess
import pathlib
from git_repo import load_config
import argparse
import os

def subprocess_run(*args, **kwargs):
    print(*args, kwargs)
    return subprocess.run(*args, **kwargs)

def configure(build_dir):
    build_dir.mkdir(exist_ok=True)
    if pathlib.Path('CMakeLists.txt').exists():
        subprocess_run([
            'cmake', '-S', '.', '-B', str(build_dir)
            ])
    elif pathlib.Path('Kbuild').exists():
        subprocess_run([
            'make', 'O=' + str(build_dir), 'defconfig'
            ])
    elif pathlib.Path('configure').exists():
        subprocess_run([
            str(pathlib.Path('configure').absolute())
            ], cwd=build_dir)
    elif pathlib.Path('meson.build').exists():
        subprocess_run([
            'meson', 'setup', str(build_dir)
            ])


def build_used_process_count():
    return os.cpu_count()

def build(build_dir):
    if not build_dir.exists():
        configure(build_dir)
    if (build_dir / 'CMakeCache.txt').exists():
        subprocess_run([
            'cmake', '--build', str(build_dir), '--parallel', str(build_used_process_count())
            ])
    elif pathlib.Path('PKGBUILD').exists():
        subprocess_run([
            'makepkg'
            ], env={ 'BUILDDIR': str(build_dir)})
    elif pathlib.Path('Kbuild').exists():
        if not (build_dir/'.config').exists():
            configure(build_dir)
        subprocess_run([
            'make', 'O=' + str(build_dir), '-j', str(build_used_process_count())
            ])
    elif pathlib.Path('Makefile').exists():
        subprocess_run([
            'make', 'O=' + str(build_dir), '-j', str(build_used_process_count())
            ])
    elif pathlib.Path('configure').exists():
        if not (build_dir/'Makefile').exists():
            configure(build_dir)
        subprocess_run([
            'make', '-j', str(build_used_process_count())
            ], cwd=build_dir)
    elif pathlib.Path('meson.build').exists():
        subprocess_run(
                ['ninja', '-C', str(build_dir)]
                )

def is_cacheable(build_dir):
    config = load_config()
    if 'need_cached_files' in config and pathlib.Path.cwd().name in config['need_cached_files']:
        return True
    return False

def find_need_cached_files(build_dir):
    config = load_config()
    files = []
    for file in config['need_cached_files'][pathlib.Path.cwd().name]:
        files.append(build_dir / file)
    return files

def git_build(build_dir):
    config = load_config()
    if not is_cacheable(build_dir):
        build(build_dir)
        return

    out = subprocess.run([
        'git', 'rev-parse', 'HEAD'
        ], capture_output=True, encoding='utf-8')
    commit = out.stdout
    cache_dir = pathlib.Path(config['cache_dir']).absolute() / pathlib.Path.cwd().name
    need_cached_files = find_need_cached_files(build_dir)
    cache = cache_dir / commit
    if not cache.exist():
        git_build(build_dir)
        for file in need_cached_files:
            file.move(cache_dir)
    cache.copy_into(build_dir)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', type=str, default='')
    parser.add_argument('--worktree', type=str, default='.')
    parser.add_argument('command', type=str)
    args = parser.parse_args()

    config = load_config()
    builds_dir = pathlib.Path(config['build_dir']).absolute()
    build_dir = builds_dir / pathlib.Path.cwd().name

    if (args.command == 'build'):
        build(build_dir)
    elif (args.command == 'configure'):
        configure(build_dir)
    elif (args.command == 'path'):
        print(build_dir)
    else:
        raise LookupError(args.command)

if __name__ == '__main__':
    main()
