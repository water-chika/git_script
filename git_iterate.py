import subprocess

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
