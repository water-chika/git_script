# Git wrapper

This project builds a `git` shim that keeps one bare repository per remote under
`repo_dir` and creates linked worktrees from it. Put the build directory before
the real Git directory on `PATH`.

## Build and test

```sh
cmake -S . -B /mnt/build/git_script_build
cmake --build /mnt/build/git_script_build
ctest --test-dir /mnt/build/git_script_build --output-on-failure
```

`config.json` is machine-local configuration and is not source code.

## Interception contract

The wrapper intercepts only forms the centralized bare-repository model can
represent faithfully:

| Command | Intercepted forms |
|---|---|
| clone | `clone [--recursive|--recurse-submodules|--no-recurse-submodules] [--] URL [DIRECTORY]` |
| init | `init [-b BRANCH|--initial-branch[=]BRANCH] [--] [DIRECTORY]` |
| submodule add | option-free `submodule add [--] URL [PATH]` |
| submodule update | `submodule update --init [--recursive] [--prompt|--no-prompt] [--] [PATH...]` |

Leading `-C` options are supported, including chained relative `-C` values. The
wrapper resolves them for helpers; final `submodule add` still receives the
original argument vector.

Every unsupported or malformed form is delegated to real Git unchanged. This is
intentional for options that alter repository layout, selected history, object
storage, transport, or checkout policy—for example clone `--bare`, `--mirror`,
`--depth`, `--filter`, `--branch`, and `--reference`; init `--bare` and
`--separate-git-dir`; option-bearing `submodule add`; and update `--remote`,
`--depth`, `--jobs`, `--merge`, or `--rebase`. Semantic Git global options such
as `-c`, `--git-dir`, and `--work-tree` likewise pass through until helpers can
honor them exactly.

Helper failures are returned to the caller. A failed submodule prewarm prevents
the real `submodule add`, and an unavailable real Git exits with status 127.

## Keeping the cached repos fresh: `git_update.py`

The wrapper only fetches a bare repo when a clone/worktree command happens to
touch it, so the caches under `repo_dir` go stale. `git_update.py` fetches all
of them, unattended:

```
python git_update.py                      # fetch every bare repo in repo_dir
python git_update.py --stale-hours 12     # skip ones fetched in the last 12h
python git_update.py --only xgl pal       # just these
python git_update.py --list               # what would be updated
python git_update.py --status             # last successful update per repo
```

`repo_dir` and `git_path` come from `config.json` (override with `--repo-dir` /
`--git-path`). Every fetch runs with credential prompts disabled, writes its
output to `<repo_dir>/git_update_logs/<repo>.log`, and is killed *with its whole
process tree* when `--timeout` (default 1800s) expires — a stalled `git fetch`
otherwise leaves `ssh`/`git-remote-*` grandchildren behind forever. Results are
recorded in `<repo_dir>/git_update_state.json`, which is what `--stale-hours`
and `--status` read; a repo that failed is simply retried on the next run.

### Run it periodically

Windows scheduled task (daily at 03:00 by default):

```
python git_update.py --install-task
python git_update.py --install-task --schedule HOURLY --jobs 8
python git_update.py --uninstall-task
schtasks /Query /TN GitUpdateRepos
```

On Linux, use cron instead:

```
0 3 * * * /usr/bin/python3 /path/to/git_script/git_update.py --log ~/.cache/git_update.log
```
