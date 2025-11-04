#!/usr/bin/env python

import pathlib
import os
import argparse
import json
from urllib.parse import urljoin
import multiprocessing
import subprocess

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

def update_submodule(submodule, recursive, repo_dir, parent_url, process_pool):
    print('recursive', submodule)
    submodule["url"] = resolve_submodule_url(submodule["url"], parent_url)
    print('resolved submodule url', submodule['url'])
    status_output = subprocess.run(['git', 'submodule', 'status', submodule['path']],
                                   capture_output=True, encoding='utf-8')
    print(status_output)
    commit = status_output.stdout.split()[0][1:]
    fun(submodule["url"], submodule["path"], commit=commit, recursive=recursive, repo_dir=repo_dir, process_pool=process_pool)
    run('git submodule update --init {}'.format(submodule["path"]))
    run('git submodule update {}'.format(submodule["path"]))

def for_submodules(submodules, recursive, repo_dir, parent_url, process_pool):
    args_vector = []
    for submodule in submodules:
        args = []
        args.append(submodule)
        args.append(recursive)
        args.append(repo_dir)
        args.append(parent_url)
        args_vector.append(args)
        #process_pool.apply_async(update_submodule, (submodule, recursive, repo_dir, parent_url))
        update_submodule(submodule,
                         recursive=recursive, repo_dir=repo_dir,
                         parent_url=parent_url, process_pool=process_pool)

def update_submodules(recursive, repo_dir, url, process_pool):
    assert(pathlib.Path('.git').exists())
    if pathlib.Path('.gitmodules').exists():
        submodules = parse_submodules('.gitmodules')
        for_submodules(submodules, recursive, repo_dir=repo_dir, parent_url=url, process_pool=process_pool)

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

def get_repo(url, repo_dir):
    name = pathlib.Path(url).name
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
        else:
            repo_index = repo_index + 1
            repo = repo_dir / (name + '_{}').format(repo_index)
    return repo

def fun(url, worktree, commit, recursive, repo_dir, process_pool):
    worktree = pathlib.Path(worktree).absolute()
    repo = get_repo(url, repo_dir)
    if not repo.exists():
        run('git clone --bare {} {} --progress'.format(url, repo))
        run('git -C {} config remote.origin.fetch +refs/heads/*:refs/remotes/origin/*'.format(repo))
    elif commit != None and 0!=run('git -C {} rev-parse {}'.format(repo, commit)):
        run('git -C {} fetch --all'.format(repo))

    if not (repo / worktree / '.git').exists():
        run(
            'git -C {} worktree add -f --detach {} {}'
                .format(
                repo,
                worktree,
                commit
            )
        )

    if recursive:
        orig_wd = pathlib.Path('.').absolute()
        try:
            os.chdir(worktree)
            update_submodules(recursive, repo_dir=repo_dir, url=url, process_pool=process_pool)
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url', type=str)
    parser.add_argument('--commit', type=str, default='HEAD')
    parser.add_argument('--worktree', type=str, default=None)
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

    config["url"] = args.url
    if args.worktree == None:
        name = pathlib.Path(args.url).name
        config["worktree"] = pathlib.Path(name).absolute()
    else:
        config["worktree"] = pathlib.Path(args.worktree).absolute()
    config["recursive"] = args.recursive
    config["repo_dir"] = repo_dir
    config['commit'] = args.commit
    print(config)

    with multiprocessing.Pool(args.cores) as p:
        config["process_pool"] = p
        fun(**config)
        p.close()
        p.join()
