# Git wrapper

This repo will build a git wrapper to cache repo in /repos.

## Build

```
cmake -S . -B /builds/git_script
```

## Usage

Add ```/builds/git_script/``` or ```/builds/git_script/Debug``` to env ```PATH``` before actually git path.

Git command will be wrapped because /builds/git_script is before actually git path.

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
