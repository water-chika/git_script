# Git wrapper

This repo will build a git wrapper to cache repo in /repos.

## Build

```
cmake -S . -B /builds/git_script
```

## Usage

Add ```/builds/git_script/``` or ```/builds/git_script/Debug``` to env ```PATH``` before actually git path.

Git command will be wrapped because /builds/git_script is before actually git path.

## TODOs

Let LAN peers could clone from LAN before fetching update from remote.

## Windows Path

```
New-ItemProperty `
  -Path "HKLM:\SOFTWARE\OpenSSH" `
  -Name DefaultShell `
  -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -PropertyType String `
  -Force

Restart-Service sshd
```
