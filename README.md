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
