import git_repo
import pathlib
import os
import argparse
import json
from urllib.parse import urljoin
import multiprocessing

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('submodules', nargs='*', type=str)
    parser.add_argument('--recursive', type=bool, default=True)
    parser.add_argument('--cores')
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

    with multiprocessing.Pool(args.cores) as process_pool:
        for submodule in args.submodules:
            for registerred_submodule in registerred_submodules:
                request_path = working_dir / submodule
                registerred_path = git_worktree_path / registerred_submodule["path"]
                if registerred_path.is_relative_to(request_path):
                    config = {}
                    config["url"] = git_repo.resolve_submodule_url(registerred_submodule["url"], parent_url)
                    config["worktree"] = registerred_path
                    config["recursive"] = args.recursive
                    config["process_pool"] = process_pool
                    config["repo_dir"] = repo_dir
                    print(config)
                    git_repo.fun(**config)
        process_pool.close()
        process_pool.join()
