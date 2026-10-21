#!/usr/bin/env python

import argparse
import json
import os
import pathlib

import git_repo


def main(argv=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Initialize and update submodules using the worktree model.')
    parser.add_argument('submodules', nargs='*', help='Submodule paths (default: all)')
    parser.add_argument('--recursive', action='store_true', default=False)
    parser.add_argument('--no-recursive', action='store_false', dest='recursive')
    parser.add_argument('--prompt', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--working-directory', default='.')
    parser.add_argument('--cores')
    args = parser.parse_args(argv)

    config_file = pathlib.Path(__file__).resolve().parent / 'config.json'
    if not config_file.exists():
        print('config file not exist!')
        return 1
    with open(config_file) as file:
        config = json.load(file)
    repo_dir = pathlib.Path(config['repo_dir']).absolute()
    git_path = git_repo.resolve_git_path(config)

    working_dir = pathlib.Path(args.working_directory).absolute()
    if not git_repo.is_in_git_worktree(working_dir):
        print('not in a git worktree')
        return 1
    os.chdir(working_dir)
    worktree = git_repo.git_worktree_path(working_dir)
    registered = git_repo.parse_submodules(worktree / '.gitmodules')
    parent_url = git_repo.get_remote_url(git_repo.git_dir(working_dir) / 'config')

    requested = args.submodules or ['.']
    for requested_path in requested:
        request_root = (working_dir / requested_path).resolve()
        for submodule in registered:
            submodule_path = (worktree / submodule['path']).resolve()
            if submodule_path.is_relative_to(request_root):
                item = dict(submodule)
                item['path'] = submodule_path
                if git_repo.update_submodule(
                        item, recursive=args.recursive, repo_dir=repo_dir,
                        parent_url=parent_url, git_path=git_path,
                        prompt=args.prompt) is False:
                    return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
