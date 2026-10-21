#!/usr/bin/env python

import argparse
import json
import os
import pathlib

import git_repo


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('submodules', nargs='*', type=str)
    parser.add_argument('--recursive', action='store_true', default=False)
    parser.add_argument('--prompt', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--cores')
    parser.add_argument('--working-directory', default='.')
    args = parser.parse_args(argv)

    config_file = pathlib.Path(os.path.abspath(__file__)).resolve().parent / "config.json"
    if not config_file.exists():
        print("config file not exist!")
        return 1
    with open(config_file, "r") as file:
        config = json.load(file)
    repo_dir = pathlib.Path(config["repo_dir"]).absolute()
    git_path = pathlib.Path(config["git_path"]).absolute()

    working_dir = pathlib.Path(args.working_directory).absolute()
    if not git_repo.is_in_git_worktree(working_dir):
        print("not in a git worktree")
        return 1
    # The git_repo helpers invoke Git without an explicit -C and therefore use
    # the helper process's cwd as repository context. Apply the wrapper's
    # resolved -C directory once here; the original -C arguments are not passed
    # to this helper, so they cannot be applied twice.
    os.chdir(working_dir)
    git_worktree_path = git_repo.git_worktree_path(working_dir)
    registered_submodules = git_repo.parse_submodules(git_worktree_path / '.gitmodules')
    git_config_path = git_repo.git_dir(working_dir) / 'config'
    print(git_config_path)
    parent_url = git_repo.get_remote_url(git_config_path)
    print(git_repo.git_dir(working_dir))

    requested = args.submodules or ['.']
    for submodule in requested:
        for registered_submodule in registered_submodules:
            request_path = (working_dir / submodule).resolve()
            registered_path = (git_worktree_path / registered_submodule["path"]).resolve()
            if registered_path.is_relative_to(request_path):
                submodule_config = {
                    "git_path": git_path,
                    "submodule": {
                        "url": registered_submodule["url"],
                        "path": registered_path,
                    },
                    "recursive": args.recursive,
                    "repo_dir": repo_dir,
                    "parent_url": parent_url,
                    "prompt": args.prompt,
                }
                print(submodule_config)
                if git_repo.update_submodule(**submodule_config) is False:
                    return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
