#! python3

import pathlib
import os
import argparse
from urllib.parse import urljoin

repo_dir = pathlib.Path('E:/')

def run(*args):
    print(*args)
    os.system(*args)

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
            submodules.append(
                    {
                        "path": path,
                        "url": url
                    }
                    )
    except:
        print('parse submodules fail')
    return submodules

def resolve_url(url):
    while ".." in url:
        loc = url.find("..")
        prev = url.rfind("/", 0, loc-1)
        url = url[:prev] + url[loc+2:]
    return url

def get_repo(url):
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

def fun(url, worktree, recursive):
    name = pathlib.Path(url).name
    repo = get_repo(url)
    if worktree == None:
        worktree = pathlib.Path(name).absolute()
    else:
        worktree = pathlib.Path(worktree).absolute()
    if not repo.exists():
        run('git clone --bare {} {} --progress'.format(url, repo))
        run('git -C {} config remote.origin.fetch +refs/heads/*:refs/remotes/origin/*'.format(repo))
    else:
        run('git -C {} worktree prune'.format(repo))
    run(
        'git -C {} worktree add -f -B {} {}'
            .format(
               repo,
               "t" + str(worktree).replace(':',"").replace('\\','/'),
               worktree
           )
    )

    if recursive:
        orig_wd = pathlib.Path('.').absolute()
        try:
            os.chdir(worktree)
            if pathlib.Path('.gitmodules').exists():
                submodules = parse_submodules('.gitmodules')
                for submodule in submodules:
                    print('recursive', submodule)
                    if submodule["url"].startswith('../'):
                        submodule["url"] = url + "/" + submodule["url"]
                        print(submodule["url"])
                    if ".." in submodule["url"]:
                        submodule["url"] = resolve_url(submodule["url"])
                        print(submodule["url"])
                    fun(submodule["url"], submodule["path"], recursive)
                    run('git submodule update --init {}'.format(submodule["path"]))
                    fun(submodule["url"], submodule["path"], recursive)
        finally:
            os.chdir(orig_wd)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url', type=str)
    parser.add_argument('--worktree', type=str, default=None)
    parser.add_argument('--recursive', type=bool, default=False)
    args = parser.parse_args()
    fun(args.url,
        args.worktree,
        args.recursive)
