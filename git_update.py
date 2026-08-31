#!/usr/bin/env python

"""Periodically refresh every bare repo cached under ``repo_dir``.

The git wrapper (``git_repo.py``) keeps one bare repo per project under
``config.json:repo_dir`` and checks worktrees out of it.  Those bare repos are
only fetched when a clone/worktree command happens to touch them, so they go
stale.  This script fetches all of them, unattended.

Typical use::

    python git_update.py                       # fetch every bare repo
    python git_update.py --stale-hours 12      # skip ones fetched recently
    python git_update.py --only xgl pal        # just these
    python git_update.py --install-task        # Windows scheduled task, daily
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time

from git_repo import load_config

STATE_FILE_NAME = 'git_update_state.json'


def log(message, log_file=None):
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = '[{}] {}'.format(stamp, message)
    print(line, flush=True)
    if log_file:
        with open(log_file, 'a', encoding='utf-8') as file:
            file.write(line + '\n')


def is_bare_repo(path):
    return path.is_dir() and (path / 'HEAD').exists() and (path / 'config').exists()


def find_repos(repo_dir):
    return sorted((p for p in repo_dir.iterdir() if is_bare_repo(p)),
                  key=lambda p: p.name.lower())


def non_interactive_env(ssh_command=None):
    """Never let a fetch stop on a credential/host-key prompt."""
    env = dict(os.environ)
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GIT_ASKPASS'] = 'echo'
    env['SSH_ASKPASS'] = 'echo'
    if ssh_command:
        env['GIT_SSH_COMMAND'] = ssh_command
    else:
        env.setdefault('GIT_SSH_COMMAND', 'ssh -o BatchMode=yes')
    env.pop('GIT_DIR', None)
    return env


def load_state(state_file):
    try:
        with open(state_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (OSError, ValueError):
        return {}


def save_state(state_file, state):
    tmp = state_file.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as file:
        json.dump(state, file, indent=2, sort_keys=True)
    tmp.replace(state_file)


def kill_tree(process):
    """Kill a child and everything it spawned.

    A stalled ``git fetch`` has live grandchildren (git-remote-https, ssh) that
    inherit its pipes, so killing git alone leaves them running forever and any
    pipe-reading wait would never return.
    """
    if os.name == 'nt':
        subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(process.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(os.getpgid(process.pid), 9)
        except OSError:
            process.kill()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def run_git(command, timeout, output_file, ssh_command=None):
    """Run git with output going to a real file, never to a pipe.

    Returns (returncode_or_None, text). ``None`` means the timeout fired.
    """
    kwargs = {}
    if os.name != 'nt':
        kwargs['start_new_session'] = True
    with open(output_file, 'w+', encoding='utf-8', errors='replace') as sink:
        process = subprocess.Popen(command, env=non_interactive_env(ssh_command),
                                   stdin=subprocess.DEVNULL, stdout=sink,
                                   stderr=subprocess.STDOUT, **kwargs)
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(process)
            returncode = None
        sink.seek(0)
        return returncode, sink.read()


def fetch_repo(git_path, repo, timeout, gc, out_dir, ssh_command=None):
    """Fetch one bare repo. Returns (name, ok, seconds, message)."""
    start = time.monotonic()
    output_file = out_dir / (repo.name + '.log')
    command = [
        git_path, '--git-dir', str(repo),
        '-c', 'gc.auto=0',
        # No --tags: several repos have two remotes for the same project and
        # the second one then fails the whole fetch with "would clobber
        # existing tag". Default tag auto-following is enough for a cache.
        'fetch', '--all', '--prune', '--verbose',
    ]
    try:
        returncode, text = run_git(command, timeout, output_file, ssh_command)
    except OSError as error:
        return repo.name, False, time.monotonic() - start, str(error)

    elapsed = time.monotonic() - start
    if returncode is None:
        return repo.name, False, elapsed, 'timeout after {}s (killed)'.format(timeout)
    if returncode != 0:
        lines = text.strip().splitlines()
        return repo.name, False, elapsed, lines[-1] if lines else 'exit {}'.format(returncode)

    if gc:
        run_git([git_path, '--git-dir', str(repo), 'gc', '--auto', '--quiet'],
                timeout, output_file, ssh_command)
    return repo.name, True, elapsed, ''


def update_all(args, git_path, repo_dir):
    state_file = repo_dir / STATE_FILE_NAME
    state = load_state(state_file)
    now = time.time()

    repos = find_repos(repo_dir)
    if args.only:
        wanted = {name.lower() for name in args.only}
        repos = [r for r in repos if r.name.lower() in wanted]
    if args.exclude:
        unwanted = {name.lower() for name in args.exclude}
        repos = [r for r in repos if r.name.lower() not in unwanted]
    if args.stale_hours:
        cutoff = now - args.stale_hours * 3600
        repos = [r for r in repos
                 if state.get(r.name, {}).get('last_success', 0) < cutoff]

    if not repos:
        log('nothing to update', args.log)
        return 0

    log('updating {} repo(s) in {} with {} job(s)'.format(len(repos), repo_dir, args.jobs), args.log)
    out_dir = repo_dir / 'git_update_logs'
    out_dir.mkdir(exist_ok=True)
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(fetch_repo, git_path, repo, args.timeout, args.gc,
                               out_dir, args.ssh_command)
                   for repo in repos]
        for future in concurrent.futures.as_completed(futures):
            name, ok, elapsed, message = future.result()
            entry = state.setdefault(name, {})
            entry['last_attempt'] = time.time()
            if ok:
                entry['last_success'] = entry['last_attempt']
                entry.pop('error', None)
                log('ok    {:<28} {:>5.0f}s'.format(name, elapsed), args.log)
            else:
                entry['error'] = message
                failed.append(name)
                log('FAIL  {:<28} {:>5.0f}s  {}'.format(name, elapsed, message), args.log)
            save_state(state_file, state)

    log('done: {} ok, {} failed{}'.format(len(repos) - len(failed), len(failed),
                                          (': ' + ', '.join(sorted(failed))) if failed else ''),
        args.log)
    return 1 if failed else 0


def install_task(args, script):
    """Register a Windows Scheduled Task that runs this script periodically."""
    python = sys.executable
    log_file = args.log or (pathlib.Path(os.environ.get('LOCALAPPDATA', '.')) /
                            'git_update' / 'git_update.log')
    pathlib.Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    command = '"{}" "{}" --jobs {} --timeout {} --log "{}"'.format(
        python, script, args.jobs, args.timeout, log_file)
    create = [
        'schtasks.exe', '/Create', '/F', '/TN', args.task_name,
        '/TR', command, '/SC', args.schedule, '/ST', args.start_time,
    ]
    if args.schedule.upper() == 'HOURLY':
        create = ['schtasks.exe', '/Create', '/F', '/TN', args.task_name,
                  '/TR', command, '/SC', 'HOURLY']
    out = subprocess.run(create, capture_output=True, encoding='utf-8', errors='replace')
    sys.stdout.write(out.stdout or '')
    sys.stderr.write(out.stderr or '')
    if out.returncode == 0:
        print('task "{}" installed; log: {}'.format(args.task_name, log_file))
    return out.returncode


def uninstall_task(args):
    out = subprocess.run(['schtasks.exe', '/Delete', '/F', '/TN', args.task_name],
                         capture_output=True, encoding='utf-8', errors='replace')
    sys.stdout.write(out.stdout or '')
    sys.stderr.write(out.stderr or '')
    return out.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo-dir', type=str, default=None,
                        help='bare repo cache (default: config.json repo_dir)')
    parser.add_argument('--git-path', type=str, default=None,
                        help='real git binary (default: config.json git_path)')
    parser.add_argument('--jobs', type=int, default=4, help='parallel fetches')
    parser.add_argument('--timeout', type=int, default=1800, help='per-repo timeout in seconds')
    parser.add_argument('--stale-hours', type=float, default=0,
                        help='skip repos fetched successfully within this many hours')
    parser.add_argument('--only', nargs='+', default=None, help='only these repo names')
    parser.add_argument('--exclude', nargs='+', default=None, help='skip these repo names')
    parser.add_argument('--gc', action='store_true', default=False,
                        help='run "git gc --auto" after a successful fetch')
    parser.add_argument('--ssh-command', type=str, default=None,
                        help='GIT_SSH_COMMAND to use (e.g. a plink.exe path when the '
                             'system ssh stalls on piped output)')
    parser.add_argument('--log', type=str, default=None, help='append output to this file')
    parser.add_argument('--list', action='store_true', default=False,
                        help='list the repos that would be updated and exit')
    parser.add_argument('--status', action='store_true', default=False,
                        help='print last-update state and exit')
    parser.add_argument('--install-task', action='store_true', default=False,
                        help='register a Windows scheduled task for this script')
    parser.add_argument('--uninstall-task', action='store_true', default=False)
    parser.add_argument('--task-name', type=str, default='GitUpdateRepos')
    parser.add_argument('--schedule', type=str, default='DAILY',
                        help='schtasks /SC value: HOURLY, DAILY, WEEKLY, ...')
    parser.add_argument('--start-time', type=str, default='03:00')
    args = parser.parse_args()

    script = pathlib.Path(os.path.abspath(__file__)).resolve()
    if args.uninstall_task:
        return uninstall_task(args)
    if args.install_task:
        return install_task(args, script)

    file_config = load_config() or {}
    repo_dir = pathlib.Path(args.repo_dir or file_config['repo_dir']).absolute()
    git_path = args.git_path or file_config.get('git_path', 'git')
    if not repo_dir.is_dir():
        log('repo dir {} does not exist'.format(repo_dir), args.log)
        return 2

    if args.status:
        state = load_state(repo_dir / STATE_FILE_NAME)
        for name in sorted(state):
            entry = state[name]
            last = entry.get('last_success')
            when = datetime.datetime.fromtimestamp(last).strftime('%Y-%m-%d %H:%M') if last else 'never'
            print('{:<28} {:<17} {}'.format(name, when, entry.get('error', '')))
        return 0

    if args.list:
        for repo in find_repos(repo_dir):
            print(repo.name)
        return 0

    return update_all(args, git_path, repo_dir)


if __name__ == '__main__':
    sys.exit(main())
