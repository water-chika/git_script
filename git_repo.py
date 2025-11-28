#!/usr/bin/env python

import pathlib
import os
import argparse
import json
import subprocess
from urllib.parse import urlparse

from is_same_repo import is_same_repo,remove_git_suffix

def run(*args):
    print(*args)
    return os.system(*args)

def parse_submodules(path):
    submodules = []
    try:
        with open(path, 'r') as file:
            lines = file.readlines()
            path = None
            url = None
            for line in lines:
                if line.startswith('[submodule '):
                    if path != None:
                        submodules.append(
                            {
                                "path": path,
                                "url": url
                            }
                        )
                    submodule = line.split('"')[1]
                elif line.startswith('\tpath = '):
                    path = line.split(' ')[2].rstrip()
                elif line.startswith('\turl = '):
                    url = line.split(' ')[2].rstrip()
                else:
                    print("empty line", line)
            if path != None:
                submodules.append(
                        {
                            "path": path,
                            "url": url
                        }
                        )
    except:
        print('parse submodules fail')
    return submodules

def update_submodule(submodule, recursive, repo_dir, parent_url):
    print('recursive', submodule)
    submodule["url"] = resolve_submodule_url(submodule["url"], parent_url)
    print('resolved submodule url', submodule['url'])
    status_output = subprocess.run(['git', 'submodule', 'status', submodule['path']],
                                   capture_output=True, encoding='utf-8')
    print(status_output)
    commit = status_output.stdout.split()[0][1:]
    fun(submodule["url"], submodule["path"], commit=commit, recursive=recursive, repo_dir=repo_dir)
    run('git submodule update --init {}'.format(submodule["path"]))
    run('git submodule update {}'.format(submodule["path"]))

def for_submodules(submodules, recursive, repo_dir, parent_url):
    args_vector = []
    for submodule in submodules:
        args = []
        args.append(submodule)
        args.append(recursive)
        args.append(repo_dir)
        args.append(parent_url)
        args_vector.append(args)
        update_submodule(submodule,
                         recursive=recursive, repo_dir=repo_dir,
                         parent_url=parent_url)

def update_submodules(recursive, repo_dir, url):
    assert(pathlib.Path('.git').exists())
    if pathlib.Path('.gitmodules').exists():
        submodules = parse_submodules('.gitmodules')
        for_submodules(submodules, recursive, repo_dir=repo_dir, parent_url=url)

def resolve_url(url):
    while ".." in url:
        loc = url.find("..")
        prev = url.rfind("/", 0, loc-1)
        url = url[:prev] + url[loc+2:]
    return url
def resolve_submodule_url(url, parent_url):
    if url.startswith('../'):
        url = parent_url + "/" + url
    if ".." in url:
        url = resolve_url(url)
    return url

def repo_name_from_url(url):
    name = pathlib.Path(url).name
    return remove_git_suffix(name)

def same_repo_url_in(url, urls):
    for u in urls:
        print(url,u)
        if is_same_repo(url, u):
            return True
    return False

def add_url_to_repo(url, repo):
    parsed_url = urlparse(url)
    remote_name = parsed_url.scheme + '_' + parsed_url.path.replace('/', '_').replace('.', '_')
    subprocess.run(
            [
                'git','-C',repo,'remote', 'add', remote_name, url
                ]
            )

def get_repo(url, repo_dir):
    name = repo_name_from_url(url)
    repo = repo_dir / name
    repo_index = 0
    while repo.exists():
        config = repo / 'config'
        remotes = {}
        remote_name = None
        with open(config, 'r') as file:
            lines = file.readlines()
            for line in lines:
                if line.startswith('[remote'):
                    remote_name = line.split('"')[1]
                elif remote_name not in remotes and \
                line.startswith('\turl = '):
                    remotes[remote_name] = line.split(' ')[2].rstrip()
        print(remotes)
        if url in remotes.values():
            return repo
        elif same_repo_url_in(url, remotes.values()):
            add_url_to_repo(url, repo)
            return repo
        else:
            repo_index = repo_index + 1
            repo = repo_dir / (name + '_{}').format(repo_index)
    return repo

def exists_commit(repo, commit):
    return 0 == run('git -C {} rev-parse -q --verify {}'.format(repo, commit))

def fun(url, worktree, commit, recursive, repo_dir):
    worktree = pathlib.Path(worktree).absolute()
    repo = get_repo(url, repo_dir)
    if not repo.exists():
        run('git clone --bare {} {} --progress'.format(url, repo))
        run('git -C {} config remote.origin.fetch +refs/heads/*:refs/remotes/origin/*'.format(repo))

    if not (repo / worktree / '.git').exists():
        if commit != '' and not exists_commit(repo, commit):
            run('git -C {} fetch --all'.format(repo))
        detach_or_orphan_flag = '--detach'
        if commit == '' and not exists_commit(repo, 'HEAD'):
            detach_or_orphan_flag = '--orphan'
        run(
            'git -C {} worktree add -f {} {} {}'
                .format(repo, detach_or_orphan_flag, worktree, commit)
        )

    if recursive:
        orig_wd = pathlib.Path('.').absolute()
        try:
            os.chdir(worktree)
            update_submodules(recursive, repo_dir=repo_dir, url=url)
        finally:
            os.chdir(orig_wd)

def is_in_git_worktree(path):
    path = path.absolute()
    contain_git = (path / '.git').exists()
    while not contain_git and path != path.parent:
        path = path.parent
        contain_git = (path / '.git').exists()
    return contain_git
def git_worktree_path(path):
    path = path.absolute()
    contain_git = (path / '.git').exists()
    while not contain_git and path != path.parent:
        path = path.parent
        contain_git = (path / '.git').exists()
    return path
def git_dir(path):
    path = path.absolute()
    contain_git = (path / '.git').exists()
    while not contain_git and path != path.parent:
        path = path.parent
        contain_git = (path / '.git').exists()
    gitdir_path = path / '.git'
    if gitdir_path.is_file():
        with open(gitdir_path) as file:
            line = file.readline()
            gitdir_path = pathlib.Path(line.split(' ')[1].rstrip()).absolute()
            with open(gitdir_path / 'commondir') as file:
                line = file.readline().rstrip()
                gitdir_path = (gitdir_path / line).resolve()
    print(gitdir_path)
    return gitdir_path.resolve()

def get_remote_url(config_path):
    url = None
    try:
        print(config_path)
        with open(config_path, 'r') as file:
            lines = file.readlines()
            code = 0
            for line in lines:
                if code == 0 and line.startswith('[remote '):
                    code = 1
                elif code == 1 and line.startswith('\turl = '):
                    url = line.split(' ')[2].rstrip()
                    code = 2
                    break
                else:
                    print("empty line", line)
    except:
        print('parse config remote url fail')
    return url

def load_config():
    config = None
    config_file = pathlib.Path(os.path.abspath(__file__)).resolve().parent / "config.json"
    if not config_file.exists():
        print("config file not exist!")
    else:
        with open(config_file, "r") as config_file:
            config = json.load(config_file)
    return config

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url', type=str)
    parser.add_argument('--commit', type=str, default='')
    parser.add_argument('--worktree', type=str)
    parser.add_argument('--recursive', type=bool, default=True)
    parser.add_argument('--cores')
    args = parser.parse_args()

    config = load_config()
    assert(config != None)
    repo_dir = pathlib.Path(config["repo_dir"]).absolute()

    config["url"] = args.url
    if args.worktree == None:
        name = repo_name_from_url(args.url)
        config["worktree"] = pathlib.Path(name).absolute()
    else:
        config["worktree"] = pathlib.Path(args.worktree).absolute()
    config["recursive"] = args.recursive
    config["repo_dir"] = repo_dir
    config['commit'] = args.commit
    print(config)
    fun(**config)
