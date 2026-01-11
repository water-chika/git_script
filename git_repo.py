#!/usr/bin/env python

import pathlib
import os
import argparse
import json
import subprocess
import re
from urllib.parse import urlparse
import shutil
import sys
import fnmatch

from is_same_repo import is_same_repo, remove_git_suffix
from enum import Enum, auto


class CheckoutMode(Enum):
    DEFAULT = auto()
    DISABLED = auto()


def run(*args) -> int:
    """Execute shell command, print it, return exit code (output not captured)."""
    print(*args)
    return os.system(*args)


def run_subprocess(cmds: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Execute command list via subprocess.run, print it, capture output by default."""
    print(' '.join(cmds))
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('encoding', 'utf-8')
    return subprocess.run(cmds, **kwargs)


def parse_submodules(mpath):
    submodules = []
    try:
        with open(mpath, 'r') as file:
            lines = file.readlines()
            path = None
            url = None
            name = None
            for line in lines:
                if line.startswith('[submodule '):
                    if path is not None:
                        submodules.append(
                            {
                                "name": name,
                                "path": path,
                                "url": url
                            }
                        )
                    name = line.split('"')[1]
                    path = None
                    url = None
                elif line.find('path = ') != -1:
                    path = line.split('=')[1].strip()
                elif line.find('url = ') != -1:
                    url = line.split('=')[1].strip()
                else:
                    pass  # empty line
            if path is not None:
                submodules.append(
                    {
                        "name": name,
                        "path": path,
                        "url": url
                    }
                )
    except Exception as e:
        print(f'Failed to parse submodule file: {mpath}', file=sys.stderr)
    return submodules


def init_submodule(name, url, path):
    cpath = pathlib.Path('.').absolute()
    submodule_path = pathlib.Path(path)
    if submodule_path.is_absolute():
        result = run_subprocess(
            ['git', '-C', str(cpath), 'rev-parse', '--show-toplevel'])
        if result.returncode == 0:
            submodule_path = submodule_path.relative_to(
                pathlib.Path(result.stdout.strip()))

    path_normalized = submodule_path.as_posix()
    # Init submodule, same as: git submodule init <path>
    run(f'git -C {cpath} config --local --unset submodule.{name}.url')
    run(f'git -C {cpath} config --local --unset submodule.{name}.active')
    # URL can also be set in local level config
    run(f'git -C {cpath} config --worktree submodule.{name}.url {url}')
    run(f'git -C {cpath} config --worktree submodule.{name}.active true')

    status_output = run_subprocess(
        ['git', '-C', str(cpath), 'rev-parse', f'HEAD:{path_normalized}'])
    if status_output.returncode != 0:
        print(status_output, file=sys.stderr)
        return None

    commit = status_output.stdout.strip()
    print(f'resolved submodule commit', commit)
    return commit


def update_submodule(submodule, recursive, repo_dir, parent_url):
    print(f"Updating submodule: {submodule}")
    submodule["url"] = resolve_submodule_url(submodule["url"], parent_url)
    print(f"Resolved submodule URL: {submodule['url']}")

    commit = init_submodule(**submodule)
    fun(submodule["url"], submodule["path"], commit=commit,
        recursive=recursive, repo_dir=repo_dir)


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


def is_submodule_active(name, path):
    """
    Check if a submodule should be activated based on git config.
    Mimics the behavior of 'git submodule update --init'.

    Returns True if:
    - submodule.<name>.active is explicitly set to true, OR
    - submodule.active pattern matches the path, OR
    - Neither submodule.active nor submodule.<name>.active is set (default: activate all)
    """
    cpath = pathlib.Path('.').absolute()
    # Check submodule.<name>.active
    result = run_subprocess(
        ['git', '-C', str(cpath), 'config', '--get', f'submodule.{name}.active'])
    if result.returncode == 0:
        # Explicitly configured for this submodule
        value = result.stdout.strip().lower()
        return value == 'true'

    # Check submodule.active pattern
    result = run_subprocess(
        ['git', '-C', str(cpath), 'config', '--get-all', 'submodule.active'])
    if result.returncode == 0:
        # submodule.active is set, check if path matches any pattern
        patterns = result.stdout.strip().split('\n')
        for pattern in patterns:
            pattern = pattern.strip()
            if not pattern:
                continue
            # Simple pattern matching (Git uses pathspec, but we'll do basic matching)
            # Convert git pathspec to simple wildcard matching
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern.rstrip('/')):
                return True
        # submodule.active is set but path doesn't match any pattern
        return False

    # Neither submodule.<name>.active nor submodule.active is set
    # Default behavior: activate all submodules
    return True


def filter_active_submodules(submodules):
    """Filter submodules based on active configuration"""
    active_submodules = []
    for submodule in submodules:
        if is_submodule_active(submodule['name'], submodule['path']):
            active_submodules.append(submodule)
        else:
            print(
                f"Skipping inactive submodule: {submodule['name']} at {submodule['path']}")
    return active_submodules


def update_submodules(recursive, repo_dir, url):
    assert (pathlib.Path('.git').exists())
    if pathlib.Path('.gitmodules').exists():
        submodules = parse_submodules('.gitmodules')
        active_submodules = filter_active_submodules(submodules)
        for_submodules(active_submodules, recursive,
                       repo_dir=repo_dir, parent_url=url)


def resolve_url(url):
    while ".." in url:
        loc = url.find("..")
        prev = url.rfind("/", 0, loc-1)
        if prev == -1:
            prev = url.rfind(":", 0, loc-1)
        assert prev != -1, "Cannot resolve url: {}".format(url)
        url = url[:prev+1] + url[loc+3:]
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
        if is_same_repo(url, u):
            print(f'Same repo detected: {url} and {u}')
            return True
    return False


def add_url_to_repo(url, repo):
    """Add a new remote to the repo for the given URL and return the remote name."""
    parsed = urlparse(url)
    # Build a readable remote name: scheme_host_path
    # e.g. https://github.com/user/repo.git -> https_github_com_user_repo
    parts = [parsed.scheme, parsed.netloc, parsed.path]
    raw_name = '_'.join(p for p in parts if p)
    # Sanitize: keep only alphanumeric and underscore, collapse multiple underscores
    remote_name = re.sub(r'[^a-zA-Z0-9]+', '_', raw_name).strip('_')

    res = run_subprocess(
        ['git', '-C', str(repo), 'remote', 'add', remote_name, url])
    if res.returncode != 0:
        print(
            f'fail to add remote {remote_name} for {url}', file=sys.stderr)
    print(f'Added remote {remote_name} for URL {url}')
    return remote_name


def get_repo(url, repo_dir) -> tuple:
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
        print(f"Found remotes in {repo}: {remotes}")

        # Check exact URL match first
        for rname, rurl in remotes.items():
            if rurl == url:
                return repo, rname

        # Check if same repo with different URL format
        if same_repo_url_in(url, remotes.values()):
            new_remote = add_url_to_repo(url, repo)
            return repo, new_remote

        repo_index = repo_index + 1
        repo = repo_dir / (name + '_{}').format(repo_index)
    return repo, None


def exists_commit(repo, commit):
    res = run_subprocess(
        ['git', '-C', str(repo), 'rev-list', '--quiet', '--max-count', '1', commit])
    return 0 == res.returncode


def git_rev_parse(worktree, rev):
    res = run_subprocess(
        ['git', '-C', str(worktree), 'rev-parse', '--verify', '--quiet', rev])
    if res.returncode == 0:
        return res.stdout.strip()
    return None


def get_default_commit(repo, remote_name):
    # Get remote default branch using git ls-remote
    res = run_subprocess(
        ['git', '-C', str(repo), 'ls-remote', '--symref', remote_name, 'HEAD'])
    head_ref = None
    head_oid = None

    # Reference: https://git-scm.com/docs/git-ls-remote.html#_output
    # Symref line:  ref: refs/heads/main\tHEAD
    # Ref line:     <oid>\tHEAD
    symref_re = re.compile(r'^ref:\s+(?P<ref>\S+)\tHEAD\s*$')
    ref_re = re.compile(r'^(?P<oid>[0-9a-fA-F]{40,64})\tHEAD\s*$')

    if res.returncode == 0 and res.stdout:
        for raw_line in res.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            m = symref_re.match(line)
            if m:
                head_ref = m.group('ref')
                continue

            m = ref_re.match(line)
            if m:
                head_oid = m.group('oid')

    if head_ref is None or head_oid is None:
        print(f'Failed to get remote HEAD of {remote_name}!', file=sys.stderr)
        return None

    print(f'Remote HEAD: {head_ref} -> {head_oid}')
    return head_oid


def git_update_head(repo, remote_name):
    remote_head = get_default_commit(repo, remote_name)
    if exists_commit(repo, 'HEAD') and git_rev_parse(repo, 'HEAD') == remote_head:
        return 0

    if not exists_commit(repo, remote_head):
        returncode = run(f'git -C {repo} fetch {remote_name}')
        if returncode != 0:
            print('Errors found when fetching repo {}, retrying...'.format(
                repo), file=sys.stderr)
            returncode = run(f'git -C {repo} fetch {remote_name}')
            assert returncode == 0, f'Unresolved errors when fetching repo {repo}'
    return run(f'git -C {repo} update-ref --no-deref HEAD {remote_head}')


def validate_commit(repo, remote_name, commit, is_repo_latest):
    if commit:
        if exists_commit(repo, commit):
            return git_rev_parse(repo, commit)
        elif is_repo_latest:
            return None
        else:
            if git_update_head(repo, remote_name) != 0:
                return None
            return validate_commit(repo, remote_name, commit, True)
    else:
        if git_update_head(repo, remote_name) != 0:
            return None
        return validate_commit(repo, remote_name, 'HEAD', is_repo_latest)


def apply_sparse_checkout(worktree, checkout, checkout_commit):
    """Apply sparse-checkout with the given set list and checkout the commit."""
    if checkout is CheckoutMode.DISABLED or checkout is CheckoutMode.DEFAULT:
        return

    if not checkout:
        print(
            f'No sparse-checkout paths defined, skipping sparse-checkout', file=sys.stderr)
        return

    assert isinstance(
        checkout, list), "sparse-checkout paths should be a list of strings"

    paths_str = ' '.join(checkout)
    print(f'Applying sparse-checkout with paths: {paths_str}')
    run(f'git -C {worktree} sparse-checkout init --cone')
    run(f'git -C {worktree} sparse-checkout set {paths_str}')
    run(f'git -C {worktree} checkout {checkout_commit}')


def fun(url, worktree, commit, recursive, repo_dir, checkout=CheckoutMode.DEFAULT):
    worktree = pathlib.Path(worktree).absolute()
    repo, remote_name = get_repo(url, repo_dir)

    # no checkout implies no recursive
    if checkout is CheckoutMode.DISABLED:
        recursive = False

    is_repo_latest = False
    if repo.exists():
        run(f'git -C {repo} config extensions.worktreeConfig true')
        run(f'git -C {repo} config --local --unset core.bare')
        run(f'git -C {repo} config --local --unset core.worktree')
    else:
        run(f'git init --bare {repo} -b main')
        run(f'git -C {repo} remote add origin {url}')
        remote_name = 'origin'
        if git_update_head(repo, remote_name) != 0:
            shutil.rmtree(repo)
            return
        # Reference: https://git-scm.com/docs/git-worktree#_configuration_file
        run(f'git -C {repo} config extensions.worktreeConfig true')
        run(f'git -C {repo} config --local --unset core.bare')
        run(f'git -C {repo} config --worktree core.bare true')
        is_repo_latest = True

    checkout_commit = None
    if checkout is not CheckoutMode.DISABLED:
        checkout_commit = validate_commit(
            repo, remote_name, commit, is_repo_latest)
        if checkout_commit is None:
            print('Commit {} does not exist in repo {}, cannot create worktree at {}'
                  .format(commit, repo, worktree), file=sys.stderr)
            return

    if not (worktree / '.git').exists():
        worktree_add_flags = '--detach'
        if checkout is CheckoutMode.DISABLED or checkout is not CheckoutMode.DEFAULT:
            worktree_add_flags += ' --no-checkout'
        run('git -C {} worktree add -f {} {} {}'.format(
            repo, worktree_add_flags, worktree, checkout_commit))

        # Set core.worktree at worktree level config
        run(f'git -C {repo} config --local --unset core.bare')
        run(f'git -C {repo} config --local --unset core.worktree')
        run(f'git -C {worktree} config --worktree core.bare false')
        run(f'git -C {worktree} config --worktree core.worktree {worktree}')
        apply_sparse_checkout(worktree, checkout, checkout_commit)
    else:
        run(f'git -C {worktree} config --worktree core.bare false')
        run(f'git -C {worktree} config --worktree core.worktree {worktree}')

        if checkout is not CheckoutMode.DISABLED:
            # Check if current HEAD is already at the target commit
            if checkout_commit == git_rev_parse(worktree, 'HEAD'):
                print(
                    f'Worktree already at {checkout_commit}, skipping checkout')
            else:
                run(f'git -C {worktree} checkout {checkout_commit}')

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
    print(f'git_dir: {gitdir_path}')
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
                    pass  # empty line
    except Exception as e:
        print(
            f'Failed to parse remote URL from {config_path}', file=sys.stderr)
    return url


def load_config():
    config = None
    config_file = pathlib.Path(os.path.abspath(
        __file__)).resolve().parent / "config.json"
    if not config_file.exists():
        print("config file not exist!", file=sys.stderr)
    else:
        with open(config_file, "r") as config_file:
            config = json.load(config_file)
    return config


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='''Clone git repositories using bare repo + worktree model.

All bare repositories are stored in a central directory (repo_dir from config.json),
and worktrees are created as lightweight checkouts sharing the same object store.
This saves disk space when working with multiple worktrees of the same repository.

Features:
  - Automatic bare repo reuse for same repository URLs
  - Recursive submodule initialization with worktree model
  - Sparse-checkout presets defined in config.json
  - Worktree-level git config isolation''')
    parser.add_argument('url', help='Git repository URL')
    parser.add_argument('-c', '--commit', default='',
                        help='Commit SHA to checkout (default: remote HEAD)')
    parser.add_argument('-w', '--worktree',
                        help='Worktree path (default: repo name from URL)')
    parser.add_argument('--no-recursive', action='store_true',
                        help='Do not init submodules recursively')
    parser.add_argument('--no-checkout', action='store_true',
                        help='Skip checkout (implies --no-recursive)')
    parser.add_argument('--sparse-checkout', metavar='PRESET',
                        help='Use sparse-checkout preset from config.json (new worktrees only)')
    args = parser.parse_args()

    fconfig = load_config()
    if fconfig is None:
        print("Error: config.json not found or invalid", file=sys.stderr)
        sys.exit(1)
    repo_dir = pathlib.Path(fconfig["repo_dir"]).absolute()

    config = {}
    config["url"] = args.url
    if args.worktree is None:
        name = repo_name_from_url(args.url)
        config["worktree"] = pathlib.Path(name).absolute()
    else:
        config["worktree"] = pathlib.Path(args.worktree).absolute()
    config["recursive"] = not args.no_recursive
    config["repo_dir"] = repo_dir
    config['commit'] = args.commit

    # Validate sparse-checkout option
    config['checkout'] = CheckoutMode.DEFAULT
    if args.no_checkout:
        config['checkout'] = CheckoutMode.DISABLED
    elif args.sparse_checkout is not None:
        sparse_presets = fconfig.get('sparse_checkout_presets', {})
        if args.sparse_checkout not in sparse_presets:
            print(
                f'Error: sparse-checkout preset "{args.sparse_checkout}" not found', file=sys.stderr)
            print(
                f'Available: {list(sparse_presets.keys())}', file=sys.stderr)
            sys.exit(1)
        else:
            config['checkout'] = sparse_presets[args.sparse_checkout]

    print(config)
    fun(**config)
