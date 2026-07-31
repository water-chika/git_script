# Git wrapper

This repo will build a git wrapper to cache repo in /repos.

## Build

```
cmake -S . -B /builds/git_script
```

## Usage

Add ```/builds/git_script/``` or ```/builds/git_script/Debug``` to env ```PATH``` before actually git path.

Git command will be wrapped because /builds/git_script is before actually git path.
