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


REPOS_ROOT_ENV = "GIT_REPO_REPOS_ROOT"
WORKTREES_ROOT_ENV = "GIT_REPO_WORKTREES_ROOT"
GIT_PATH_ENV = "GIT_REPO_GIT_PATH"
WINDOWS_MAX_PATH = 260


def _is_windows(platform=None):
    return (platform or sys.platform).startswith("win")


def default_repo_dir(platform=None):
    return pathlib.Path("C:/repos") if _is_windows(platform) else pathlib.Path("/mnt/repos")


def default_worktrees_dir(platform=None):
    return pathlib.Path("C:/worktrees") if _is_windows(platform) else pathlib.Path("/mnt/worktrees")


def default_git_path(platform=None):
    if _is_windows(platform):
        return pathlib.Path("C:/Program Files/Git/cmd/git.exe")
    return pathlib.Path("/usr/bin/git")


def _resolve_root(cli_value, file_config, config_key, env_key, default_fn,
                  env=None, platform=None):
    env = env if env is not None else os.environ
    if cli_value:
        return pathlib.Path(cli_value)
    if env.get(env_key):
        return pathlib.Path(env[env_key])
    if file_config and file_config.get(config_key):
        return pathlib.Path(file_config[config_key])
    return default_fn(platform)


def resolve_repo_dir(file_config, cli_value=None, env=None, platform=None):
    return _resolve_root(cli_value, file_config, "repo_dir", REPOS_ROOT_ENV,
                         default_repo_dir, env=env, platform=platform)


def resolve_worktrees_dir(file_config, cli_value=None, env=None, platform=None):
    return _resolve_root(cli_value, file_config, "worktree_dir", WORKTREES_ROOT_ENV,
                         default_worktrees_dir, env=env, platform=platform)


def resolve_git_path(file_config, cli_value=None, env=None, platform=None):
    return _resolve_root(cli_value, file_config, "git_path", GIT_PATH_ENV,
                         default_git_path, env=env, platform=platform)


def check_worktree_path_length(worktree, platform=None, limit=WINDOWS_MAX_PATH):
    if not _is_windows(platform):
        return True, "no legacy MAX_PATH limit on this platform"
    length = len(str(pathlib.Path(worktree)))
    if length >= limit:
        return False, f"{worktree} is at/over the legacy Windows MAX_PATH limit ({limit}); enable git core.longpaths or use a shorter worktrees root"
    return True, f"{worktree} is under the {limit}-character legacy limit"


def check_symlink_capable(base_dir, platform=None, symlink_fn=None):
    if not _is_windows(platform):
        return True, "not Windows"
    probe_target = pathlib.Path(base_dir) / ".git_repo_symlink_probe_target"
    probe_link = pathlib.Path(base_dir) / ".git_repo_symlink_probe_link"
    do_symlink = symlink_fn or (lambda link, target: link.symlink_to(target))
    try:
        probe_target.write_text("probe\n")
        do_symlink(probe_link, probe_target)
        return True, "symlink creation succeeded"
    except OSError as exc:
        return False, f"could not create a symlink under {base_dir}: {exc}. Enable Developer Mode"
    finally:
        for path in (probe_link, probe_target):
            try:
                path.unlink()
            except OSError:
                pass


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


def update_submodule(submodule, recursive, repo_dir, parent_url,
                     git_path=None, prompt=True):
    print(f"Updating submodule: {submodule}")
    submodule["url"] = resolve_submodule_url(submodule["url"], parent_url)
    print(f"Resolved submodule URL: {submodule['url']}")

    commit = init_submodule(**submodule)
    if commit is None:
        return False
    return fun(submodule["url"], submodule["path"], commit=commit,
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


def fun(url, worktree, commit, recursive, repo_dir, checkout=CheckoutMode.DEFAULT,
        git_path=None, prompt=True, platform=None):
    worktree = pathlib.Path(worktree).absolute()
    ok, detail = check_worktree_path_length(worktree, platform=platform)
    if not ok:
        print("WARNING:", detail)
    ok, detail = check_symlink_capable(
        worktree.parent if worktree.parent.exists() else repo_dir,
        platform=platform)
    if not ok:
        print("NOTE:", detail)
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
        if not (worktree / '.git').exists():
            print("skip recursion, worktree was not created:", worktree)
            return False
        orig_wd = pathlib.Path('.').absolute()
        try:
            os.chdir(worktree)
            update_submodules(recursive, repo_dir=repo_dir, url=url)
        finally:
            os.chdir(orig_wd)
    return True


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


def main(argv=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Clone repositories using the central bare repo + worktree model.')
    parser.add_argument('url', nargs='?')
    parser.add_argument('-c', '--commit', default='')
    parser.add_argument('-w', '--worktree')
    parser.add_argument('--recursive', action='store_true', default=False)
    parser.add_argument('--no-recursive', action='store_false', dest='recursive')
    parser.add_argument('--no-checkout', action='store_true')
    parser.add_argument('--sparse-checkout', metavar='PRESET')
    parser.add_argument('--prompt', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--init', action='store_true', default=False)
    parser.add_argument('--initial-branch', default='main')
    parser.add_argument('--git_path')
    parser.add_argument('--repo_dir')
    parser.add_argument('--worktrees_dir')
    parser.add_argument('--platform', help=argparse.SUPPRESS)
    parser.add_argument('--cores')
    args = parser.parse_args(argv)

    file_config = load_config()
    if file_config is None:
        print("Error: config.json not found or invalid", file=sys.stderr)
        return 1
    repo_dir = resolve_repo_dir(file_config, args.repo_dir, platform=args.platform)
    worktrees_dir = resolve_worktrees_dir(
        file_config, args.worktrees_dir, platform=args.platform)
    git_path = resolve_git_path(file_config, args.git_path, platform=args.platform)

    if args.init:
        if args.worktree is None:
            print("--worktree <worktree> is required", file=sys.stderr)
            return 2
        worktree = pathlib.Path(args.worktree).absolute()
        repo = repo_dir / worktree.name
        if repo.exists():
            print("repo exists, do not init existing repo", file=sys.stderr)
            return 1
        result = subprocess.run(
            [git_path, 'init', '--bare', '-b', args.initial_branch, repo])
        if result.returncode != 0:
            return result.returncode
        result = subprocess.run(
            [git_path, '-C', repo, 'worktree', 'add', '--orphan', '-b',
             args.initial_branch, '-f', worktree])
        return result.returncode

    if args.url is None:
        parser.error('url is required unless --init is used')
    worktree = pathlib.Path(
        args.worktree if args.worktree is not None else repo_name_from_url(args.url)
    ).absolute()
    try:
        worktree.relative_to(worktrees_dir)
    except ValueError:
        print(f"note: {worktree} is outside configured worktrees root {worktrees_dir}")

    checkout = CheckoutMode.DEFAULT
    if args.no_checkout:
        checkout = CheckoutMode.DISABLED
    elif args.sparse_checkout is not None:
        presets = file_config.get('sparse_checkout_presets', {})
        if args.sparse_checkout not in presets:
            print(f'Error: sparse-checkout preset "{args.sparse_checkout}" not found',
                  file=sys.stderr)
            return 1
        checkout = presets[args.sparse_checkout]

    config = {
        'url': args.url,
        'worktree': worktree,
        'recursive': args.recursive,
        'repo_dir': repo_dir,
        'commit': args.commit,
        'checkout': checkout,
        'git_path': git_path,
        'prompt': args.prompt,
        'platform': args.platform,
    }
    print(config)
    return 0 if fun(**config) is not False else 1


if __name__ == '__main__':
    raise SystemExit(main())
