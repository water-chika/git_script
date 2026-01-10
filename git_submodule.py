#!/usr/bin/env python

import git_repo
import pathlib
import os
import argparse
import json
from urllib.parse import urljoin

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='''Initialize and update git submodules using worktree model.

This script initializes submodules in the current git worktree, using the same
bare repo + worktree approach as git_repo. Submodules are stored in the central
repo_dir and linked via worktrees.

If no submodule paths are specified, all registered submodules will be updated.''')
    parser.add_argument('submodules', nargs='*',
                        help='Submodule paths to init (default: all)')
    parser.add_argument('--no-recursive', action='store_true',
                        help='Do not recurse into nested submodules')
    args = parser.parse_args()

    config = None
    config_file = pathlib.Path(os.path.abspath(__file__)).resolve().parent / "config.json"
    if not config_file.exists():
        print("config file not exist!")
    else:
        with open(config_file, "r") as config_file:
            config = json.load(config_file)
    assert(config != None)
    repo_dir = pathlib.Path(config["repo_dir"]).absolute()

    working_dir = pathlib.Path('.').absolute()

    if not git_repo.is_in_git_worktree(working_dir):
        print("not in a git worktree")
        exit(1)
    git_worktree_path = git_repo.git_worktree_path(working_dir)
    registerred_submodules = git_repo.parse_submodules(git_worktree_path / '.gitmodules')
    git_config_path = git_repo.git_dir(working_dir) / 'config'
    print(git_config_path)
    parent_url = git_repo.get_remote_url(git_config_path)
    print(git_repo.git_dir(working_dir))

    for submodule in args.submodules:
        for registerred_submodule in registerred_submodules:
            request_path = working_dir / submodule
            registerred_path = git_worktree_path / registerred_submodule["path"]
            if registerred_path.is_relative_to(request_path):
                config = {}
                submodule_dict = {}
                submodule_dict["name"] = registerred_submodule["name"]
                submodule_dict["url"] = registerred_submodule["url"]
                submodule_dict["path"] = registerred_path
                config["submodule"] = submodule_dict
                config["recursive"] = not args.no_recursive
                config["repo_dir"] = repo_dir
                config["parent_url"] = parent_url
                print(config)
                git_repo.update_submodule(**config)
