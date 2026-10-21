#!/usr/bin/env python

import pathlib
import os
import sys
import argparse
import json
import subprocess
from urllib.parse import urlparse
import shutil

from is_same_repo import is_same_repo,remove_git_suffix

# --- Windows portability: configurable roots + honest platform checks ------
#
# This machine's standing convention (see the git-workflow skill) is
# `cd /mnt/worktrees && yes Y | git clone <url>`: bare repos live under one
# root, checkouts (worktrees) under another. Both roots used to be reachable
# only via this machine's own config.json (repo_dir) or, for the worktree
# side, purely by the caller's cwd. Making both explicitly configurable -
# with a sensible platform default and an env override - is what lets a role
# running natively on Windows (no /mnt anything) use the exact same
# convention against C:/repos and C:/worktrees, without editing this file.
#
# Precedence for both roots (highest wins): CLI flag > env var > this
# machine's config.json > platform default. On THIS machine, config.json
# already pins repo_dir to /mnt/repos and no env var is set, so every
# existing invocation resolves to exactly the same path as before this
# change - nothing here alters current Linux behaviour.

REPOS_ROOT_ENV = "GIT_REPO_REPOS_ROOT"
WORKTREES_ROOT_ENV = "GIT_REPO_WORKTREES_ROOT"
GIT_PATH_ENV = "GIT_REPO_GIT_PATH"

WINDOWS_MAX_PATH = 260  # legacy MAX_PATH; a checkout at/near this is a real,
                        # confusing git failure on Windows, not a wrapper bug.


def _is_windows(platform=None):
    """True if `platform` (defaults to sys.platform) names a Windows host.
    Takes an explicit override purely so the Windows-specific branches below
    are unit-testable from a Linux box - there is no Windows machine to test
    this on in this pass."""
    return (platform or sys.platform).startswith("win")


def default_repo_dir(platform=None):
    return pathlib.Path("C:/repos") if _is_windows(platform) else pathlib.Path("/mnt/repos")


def default_worktrees_dir(platform=None):
    return pathlib.Path("C:/worktrees") if _is_windows(platform) else pathlib.Path("/mnt/worktrees")


def default_git_path(platform=None):
    # Matches this project's own CMakeLists.txt GIT_PATH defaults, so a
    # Windows install without config.json yet still finds the git a normal
    # "Git for Windows" install places there.
    if _is_windows(platform):
        return pathlib.Path("C:/Program Files/Git/cmd/git.exe")
    return pathlib.Path("/usr/bin/git")


def _resolve_root(cli_value, file_config, config_key, env_key, default_fn,
                   env=None, platform=None):
    """CLI flag > env var > config.json key > platform default - the one
    precedence rule shared by repo_dir/worktrees_dir/git_path resolution.
    Deliberately does NOT force `.absolute()` (unlike the cwd-relative
    worktree-target path elsewhere in this file): every value here - CLI,
    env, config.json, or a platform default - is already meant to be an
    absolute root, and calling `.absolute()` on a `C:/...`-style path while
    running on a real POSIX host (as the Windows-branch unit tests do, with
    no Windows box available) would wrongly treat it as cwd-relative,
    since plain pathlib.Path is POSIX-flavoured on a POSIX host regardless
    of the injected `platform` override."""
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
    """Windows honesty check: a checkout whose path is already near the
    legacy MAX_PATH (260 chars) will make individual files deep inside it
    fail with a confusing 'The system cannot find the path specified' from
    git itself, long after this script has already exited successfully. Only
    meaningful on Windows (a real long-path-aware filesystem, or Linux, has
    no such limit) - report it up front instead. Returns (ok, detail)."""
    if not _is_windows(platform):
        return True, "no legacy MAX_PATH limit on this platform"
    length = len(str(pathlib.Path(worktree)))
    if length >= limit:
        return False, (
            f"{worktree} is {length} chars, at/over the legacy Windows "
            f"MAX_PATH limit ({limit}) - files nested inside this checkout "
            "will likely fail with a confusing git error later, not now. "
            "Fix: enable `git config --global core.longpaths true` AND "
            "`fsutil behavior set symlinkevaluation` /longpaths support "
            "(Windows 10 1607+, needs the registry policy "
            "LongPathsEnabled=1, admin required), or clone under a shorter "
            f"worktrees root (e.g. {default_worktrees_dir('win32')} instead "
            "of a deeply nested one)."
        )
    return True, f"{worktree} is {length} chars, well under the {limit}-char legacy limit"


def check_symlink_capable(base_dir, platform=None, symlink_fn=None):
    """Windows honesty check: unlike Linux, an unprivileged Windows account
    can only create a symlink if Developer Mode (or an equivalent group
    policy) is enabled - fixture_home.py in this user's copilot-automation
    tooling already hit this (OSError WinError 1314) and falls back to
    directory junctions/hard links. git_repo.py itself never creates a
    symlink, but role tooling built on top of a cloned worktree (e.g.
    fixture_home.py) does, so report this honestly up front rather than
    letting a much later, unrelated-looking failure be the first sign of it.
    Returns (ok, detail); a no-op (True, ...) on non-Windows platforms -
    Unix symlinks need no special privilege, so there is nothing to probe
    and no extra filesystem access on the common path."""
    if not _is_windows(platform):
        return True, "not Windows - unprivileged symlinks are the norm here"
    probe_target = pathlib.Path(base_dir) / ".git_repo_symlink_probe_target"
    probe_link = pathlib.Path(base_dir) / ".git_repo_symlink_probe_link"
    do_symlink = symlink_fn or (lambda link, target: link.symlink_to(target))
    try:
        probe_target.write_text("probe\n")
        do_symlink(probe_link, probe_target)
        return True, "symlink creation succeeded (Developer Mode or equivalent policy is enabled)"
    except OSError as exc:
        return False, (
            f"could not create a symlink under {base_dir}: {exc}. Enable "
            "Developer Mode (Settings > Privacy & Security > For "
            "developers) or an equivalent 'create symbolic links' group "
            "policy before relying on any tool here that symlinks (e.g. "
            "fixture_home.py) - it will otherwise fail confusingly deep "
            "inside an unrelated operation."
        )
    finally:
        for p in (probe_link, probe_target):
            try:
                p.unlink()
            except OSError:
                pass


def submodule_git_options(url):
    """Extra `git -c` options needed to update a submodule from `url`.

    Only file:// mirrors (e.g. a sshfs-mounted checkout of another machine)
    need them, so remotes that speak a real transport keep stock behaviour.
    """
    if not str(url).startswith('file://'):
        return []
    return [
        # A submodule url is resolved relative to the superproject's own
        # remote, so a file:// mirror is exactly as trusted as the parent that
        # was already cloned from it. git has refused file transport for
        # submodules since CVE-2022-39253.
        '-c', 'protocol.file.allow=always',
        # There is no LFS server behind a plain path, so the smudge filter
        # fails and aborts the checkout. Leave LFS pointers in the worktree
        # instead of losing the entire checkout over them.
        '-c', 'filter.lfs.smudge=',
        '-c', 'filter.lfs.process=',
        '-c', 'filter.lfs.required=false',
    ]

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
    # --cached reports the commit the superproject records, rather than the one
    # currently checked out; without it an out-of-sync submodule (status prefix
    # '+') would be re-fetched and pinned at its stale checkout.
    status_output = subprocess.run([git_path, 'submodule', 'status', '--cached', submodule['path']],
                                   capture_output=True, encoding='utf-8')
    print(status_output)
    if status_output.stdout != '':
        commit = status_output.stdout.split()[0]
        # A status line is prefixed '-' (uninitialised), '+' (checked out
        # commit differs) or 'U' (merge conflict); the rest is the sha.
        if commit[0] in '-+U':
            commit = commit[1:]
        if fun(git_path, submodule["url"], submodule["path"], commit=commit,
               recursive=recursive, repo_dir=repo_dir, prompt=prompt) is False:
            return False
        options = submodule_git_options(submodule["url"])
        result = subprocess.run(
            [git_path, *options, "submodule", "update", "--init", submodule["path"]]
        )
        if result.returncode != 0:
            return False
        result = subprocess.run([git_path, *options, "submodule", "update", submodule["path"]])
        return result.returncode == 0
    print("submodule commit get fail")
    return False

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
    if not pathlib.Path('.git').exists():
        print("not a git worktree, skip:", pathlib.Path('.').absolute())
        return
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
    remote_name = parsed_url.scheme.replace('@','_') + '_' + parsed_url.path.replace('/', '_').replace('.', '_').replace('@','_')
    subprocess.run(
            [
                git_path,'-C',repo,'remote', 'add', remote_name, url
                ]
            )
    return remote_name

def get_repo_and_remote(git_path, url, repo_dir, prompt):
    name = repo_name_from_url(url)
    repo = repo_dir / name
    repo_index = 0
    while repo.exists():
        config = repo / 'config'
        remotes = {}
        remote_name = None
        url_remotes = {}
        with open(config, 'r') as file:
            lines = file.readlines()
            for line in lines:
                if line.startswith('[remote'):
                    remote_name = line.split('"')[1]
                elif remote_name not in remotes and \
                line.startswith('\turl = '):
                    this_url = line.split(' ')[2].rstrip()
                    remotes[remote_name] = this_url
                    url_remotes[this_url] = remote_name
        print(remotes, url_remotes)
        if url in remotes.values():
            return repo,url_remotes[url]
        elif same_repo_url_in(url, remotes.values()):
            add_url_to_repo(git_path, url, repo)
            return repo,url_remotes[url]
        elif prompt:
            print("url: ", url, "repo remotes: ", remotes)
            try:
                import inputimeout
                answer = inputimeout.inputimeout(prompt="Is this same repo?(Y/N):", timeout=600)
                if answer == "Y":
                    remote_name = add_url_to_repo(git_path, url, repo)
                    return repo,remote_name
            except:
                pass
        repo_index = repo_index + 1
        repo = repo_dir / (name + '_{}').format(repo_index)
    return repo,'origin'

def exists_commit(git_path, repo, commit):
    res = subprocess.run(
            [git_path, '-C', repo, 'rev-list', '--quiet', '--max-count', '1', commit]
            )
    return 0 == res.returncode

def fun(git_path, url, worktree, commit, recursive, repo_dir, prompt, platform=None):
    worktree = pathlib.Path(worktree).absolute()
    # Windows honesty checks: report likely-fatal-later conditions up front
    # instead of a confusing git failure well after this prints "success".
    # No-ops (and no extra filesystem access) on non-Windows platforms.
    ok, detail = check_worktree_path_length(worktree, platform=platform)
    if not ok:
        print("WARNING:", detail)
    ok, detail = check_symlink_capable(worktree.parent if worktree.parent.exists() else repo_dir, platform=platform)
    if not ok:
        print("NOTE:", detail)
    repo,remote = get_repo_and_remote(git_path, url, repo_dir, prompt)
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
            if repo.exists():
                shutil.rmtree(repo)
            return False
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
        subprocess.run([git_path, "-C", repo, "fetch", remote, commit])
    elif commit == 'HEAD':
        subprocess.run([git_path, "-C", repo, "fetch", remote])
        commit = remote + '/HEAD'

    if not (worktree / '.git').exists():
        result = subprocess.run(
                [git_path, "-C", repo, "worktree", "add", "-f", '--detach', worktree, commit],
                capture_output=True, encoding='utf-8'
                )
        if result.returncode != 0:
            print(result.stderr)
            return False

    if recursive:
        if not (worktree / '.git').exists():
            # An earlier step (clone/fetch/worktree add) failed, so there is
            # nothing to recurse into. Report it instead of aborting the whole
            # recursive update with a FileNotFoundError or an AssertionError.
            print("skip recursion, worktree was not created:", worktree)
            return
        orig_wd = pathlib.Path('.').absolute()
        try:
            os.chdir(worktree)
            update_submodules(git_path, recursive, repo_dir=repo_dir, url=url, prompt=prompt)
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
        # A `.git` file appears both for a linked worktree and for a submodule.
        # Its `gitdir:` target is relative to the directory holding the file,
        # not to the current working directory.
        with open(gitdir_path) as file:
            line = file.readline()
        gitdir_path = (path / line.split(' ', 1)[1].rstrip()).resolve()
        # Only a linked worktree has `commondir` pointing at the real git dir;
        # a submodule's gitdir already is one.
        commondir_path = gitdir_path / 'commondir'
        if commondir_path.exists():
            with open(commondir_path) as file:
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
    parser.add_argument('--initial-branch', type=str, default='main')
    parser.add_argument('--cores')
    parser.add_argument('--repo_dir', type=str, default=None,
                         help="override the bare-repos root (else "
                              f"${REPOS_ROOT_ENV}, then config.json's "
                              "repo_dir, then the platform default: "
                              f"{default_repo_dir()} here)")
    parser.add_argument('--worktrees_dir', type=str, default=None,
                         help="the worktrees root used only to sanity-check "
                              "where a bare --worktree lands (else "
                              f"${WORKTREES_ROOT_ENV}, then config.json's "
                              "worktree_dir, then the platform default: "
                              f"{default_worktrees_dir()} here). Does NOT "
                              "change the existing cwd-relative default used "
                              "when --worktree is omitted.")
    parser.add_argument('--platform', type=str, default=None,
                         help=argparse.SUPPRESS)  # test-only: force win32/linux branches without a real OS switch
    args = parser.parse_args()
    print(args)

    file_config = load_config()
    repo_dir = resolve_repo_dir(file_config, cli_value=args.repo_dir, platform=args.platform)
    worktrees_dir = resolve_worktrees_dir(file_config, cli_value=args.worktrees_dir, platform=args.platform)

    config = {}
    git_path = resolve_git_path(file_config, cli_value=args.git_path, platform=args.platform)
    if args.init:
        if args.worktree == None:
            print("--worktree <worktree> is required")
            return 2
        worktree = pathlib.Path(args.worktree).absolute()
        repo_name = worktree.name
        if (repo_dir / repo_name).exists():
            print("repo exists, do not init existing repo")
            return 1
        init_result = subprocess.run(
            [git_path, 'init', '--bare', '-b', args.initial_branch, repo_dir / repo_name]
        )
        if init_result.returncode != 0:
            return init_result.returncode
        worktree_result = subprocess.run(
            [git_path, '-C', repo_dir / repo_name, 'worktree', 'add', '--orphan',
             '-b', args.initial_branch, '-f', worktree]
        )
        return worktree_result.returncode

    config["git_path"] = git_path
    config["url"] = args.url
    if args.worktree == None:
        name = repo_name_from_url(args.url)
        # Deliberately still cwd-relative, exactly as before this change:
        # the standing convention (cd /mnt/worktrees && git clone ...) relies
        # on this. Only report - never silently redirect - if that lands
        # outside the configured worktrees root.
        config["worktree"] = pathlib.Path(name).absolute()
    else:
        config["worktree"] = pathlib.Path(args.worktree).absolute()
    try:
        config["worktree"].relative_to(worktrees_dir)
    except ValueError:
        print(f"note: {config['worktree']} is outside the configured "
              f"worktrees root ({worktrees_dir}); the standing convention is "
              "to cd there first (or pass --worktrees_dir/--worktree "
              "explicitly).")
    config["recursive"] = args.recursive
    config["repo_dir"] = repo_dir
    config['commit'] = args.commit
    config['prompt'] = args.prompt
    config['platform'] = args.platform
    print(config)
    return 0 if fun(**config) is not False else 1
if __name__ == '__main__':
    raise SystemExit(main())
