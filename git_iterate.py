import subprocess
import argparse
from git_build import git_build

def iterate_commit_tree(func, depth = 1, step = 1, start_commit = 'HEAD'):
    subprocess.run([
        'git', 'reset', '--hard', start_commit
    ])
    func()

    parent_i = 1
    while True:
        out = subprocess.run([
            'git', 'rev-parse', 'HEAD^' + parent_i
        ], capture_output=True, encoding='utf-8')
        if not out:
            break
        iterate_commit_tree(func, depth-1, step, start_commit=out.stdout)
        parent_i = parent_i+1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, default='HEAD')
    parser.add_argument('--depth', type=int, default=1)
    parser.add_argument('--step', type=int, default=1)
    args = parser.parse_args()

    start = args.start
    depth = args.depth
    step = args.step

    iterate_commit_tree(git_build, depth, step, start)

if __name__ == '__main__':
    main()
