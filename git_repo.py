#!/usr/bin/env python

import pathlib
import os
import argparse
import json
import subprocess
from urllib.parse import urlparse
import shutil

from is_same_repo import is_same_repo,remove_git_suffix

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

def update_submodule(git_path, submodule, recursive, repo_dir, parent_url, prompt):
    print('recursive', submodule)
    submodule["url"] = resolve_submodule_url(submodule["url"], parent_url)
    print('resolved submodule url', submodule['url'])
    status_output = subprocess.run([git_path, 'submodule', 'status', submodule['path']],
                                   capture_output=True, encoding='utf-8')
    print(status_output)
    if status_output.stdout != '':
        commit = status_output.stdout.split()[0][1:]
        fun(git_path, submodule["url"], submodule["path"], commit=commit, recursive=recursive, repo_dir=repo_dir, prompt=prompt)
        subprocess.run([git_path, "submodule", "update", "--init", submodule["path"]])
        subprocess.run([git_path, "submodule", "update", submodule["path"]])
    else:
        print("submodule commit get fail")

def for_submodules(git_path, submodules, recursive, repo_dir, parent_url, prompt):
    args_vector = []
    for submodule in submodules:
        args = []
        args.append(submodule)
        args.append(recursive)
        args.append(repo_dir)
        args.append(parent_url)
        args_vector.append(args)
        update_submodule(git_path, submodule,
                         recursive=recursive, repo_dir=repo_dir,
                         parent_url=parent_url,prompt=prompt)

def update_submodules(git_path, recursive, repo_dir, url, prompt):
    assert(pathlib.Path('.git').exists())
    if pathlib.Path('.gitmodules').exists():
        submodules = parse_submodules('.gitmodules')
        for_submodules(git_path, submodules, recursive, repo_dir=repo_dir, parent_url=url, prompt=prompt)

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

def add_url_to_repo(git_path, url, repo):
    parsed_url = urlparse(url)
    remote_name = parsed_url.scheme + '_' + parsed_url.path.replace('/', '_').replace('.', '_')
    subprocess.run(
            [
                git_path,'-C',repo,'remote', 'add', remote_name, url
                ]
            )

def get_repo(git_path, url, repo_dir, prompt):
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
            add_url_to_repo(git_path, url, repo)
            return repo
        elif prompt:
            print("url: ", url, "repo remotes: ", remotes)
            try:
                import inputimeout
                answer = inputimeout.inputimeout(prompt="Is this same repo?(Y/N):", timeout=5)
                if answer == "Y":
                    add_url_to_repo(git_path, url, repo)
                    return repo
            except e:
                print(e)
        else:
            repo_index = repo_index + 1
            repo = repo_dir / (name + '_{}').format(repo_index)
    return repo

def exists_commit(git_path, repo, commit):
    res = subprocess.run(
            [git_path, '-C', repo, 'rev-list', '--quiet', '--max-count', '1', commit],
            capture_output=True
            )
    return 0 == res.returncode

def fun(git_path, url, worktree, commit, recursive, repo_dir, prompt):
    worktree = pathlib.Path(worktree).absolute()
    repo = get_repo(git_path, url, repo_dir, prompt)
    if commit == None or commit == '':
        commit = 'HEAD'
    if not repo.exists():
        try:
            subprocess.run([git_path, "init", "--bare", repo])
            subprocess.run([git_path, "-C", repo, "remote", "add", "origin", url])
            fetch_res = subprocess.run(
                    [git_path, '-C', repo, 'fetch']
                    )
            if fetch_res.returncode != 0:
                raise RuntimeError("git command failed")
        except:
            print("There is exception, clean repo")
            shutil.rmtree(repo)
            return
        res = subprocess.run(
                [git_path, '-C', repo, 'branch', '--remote', '--list', 'origin/HEAD'],
                capture_output=True,encoding='utf-8'
                )
        if res.stdout != '':
            remote_branch = res.stdout.split()[2]
            print(remote_branch)
            branch = remote_branch[7:]
            subprocess.run(
                    [git_path, "-C", repo, "branch", "--track", branch, remote_branch],
                    capture_output=True,encoding='utf-8'
                    )
            subprocess.run(
                    [git_path, "-C", repo, "reset", "--soft", branch],
                    capture_output=True,encoding='utf-8'
                    )

    if commit != 'HEAD' and not exists_commit(git_path, repo, commit):
        subprocess.run([git_path, "-C", repo, "fetch", "--all"])

    if not (worktree / '.git').exists():
        subprocess.run(
                [git_path, "-C", repo, "worktree", "add", "-f", '--detach', worktree, commit],
                capture_output=True,encoding='utf-8'
                )

    if recursive:
        orig_wd = pathlib.Path('.').absolute()
        try:
            os.chdir(worktree)
            update_submodules(git_path, recursive, repo_dir=repo_dir, url=url, prompt=prompt)
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
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url', type=str, nargs='?')
    parser.add_argument('--git_path', type=str, default=None)
    parser.add_argument('--commit', type=str, default='')
    parser.add_argument('--worktree', type=str)
    parser.add_argument('--recursive', action='store_true', default=False)
    parser.add_argument('--prompt', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--init', action='store_true', default=False)
    parser.add_argument('--cores')
    args = parser.parse_args()
    print(args)

    file_config = load_config()
    assert(file_config != None)
    repo_dir = pathlib.Path(file_config["repo_dir"]).absolute()


    config = {}
    git_path = None
    if args.git_path != None:
        git_path = pathlib.Path(args.git_path).absolute()
    else:
        git_path = pathlib.Path(file_config["git_path"]).absolute()
    assert(git_path != None)
    if args.init:
        if args.worktree == None:
            print("--worktree <worktree> is required")
            return
        worktree =pathlib.Path(args.worktree).absolute()
        repo_name = worktree.name
        if (repo_dir / repo_name).exists():
            print("repo exists, do not init existing repo")
            return
        subprocess.run([git_path, 'init', '--bare', '-b', 'main', repo_dir / repo_name])
        subprocess.run([git_path, '-C', repo_dir / repo_name, 'worktree', 'add', '--orphan', '-b', 'main', '-f', worktree])
        return

    config["git_path"] = git_path
    config["url"] = args.url
    if args.worktree == None:
        name = repo_name_from_url(args.url)
        config["worktree"] = pathlib.Path(name).absolute()
    else:
        config["worktree"] = pathlib.Path(args.worktree).absolute()
    config["recursive"] = args.recursive
    config["repo_dir"] = repo_dir
    config['commit'] = args.commit
    config['prompt'] = args.prompt
    print(config)
    fun(**config)
if __name__ == '__main__':
    main()
