#!/usr/bin/env python

import subprocess
import pathlib
from git_repo import load_config
import argparse
import os

def subprocess_run(cmds):
    print(cmds)
    return subprocess.run(cmds)

def build(build_dir):
    build_dir.mkdir(exist_ok=True)
    subprocess_run([
        'cmake', '-S', '.', '-B', build_dir
        ])
    subprocess_run([
        'cmake', '--build', build_dir
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
    elif (args.command == 'path'):
        print(build_dir)
    else:
        raise LookupError(args.command)

if __name__ == '__main__':
    main()
