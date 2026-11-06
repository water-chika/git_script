# Git wrapper

This repo will build a git wrapper to cache repo in /repos.

## Build

```
cmake -S . -B /builds/git_script
```

## Usage

Add ```/builds/git_script/``` or ```/builds/git_script/Debug``` to env ```PATH``` before actually git path.

Git command will be wrapped because /builds/git_script is before actually git path.

### Bash

Add below statements to ```.bashrc```:

```
export PATH="/builds/git_script:$PATH"
```

### PowerShell+Windows

Run below statements with administrator:

```
$BuildPath = "C:/builds/git_script/Debug"
$Path = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::Machine)
$Path = $BuildPath + ";" + $Path
[System.Environment]::SetEnvironmentVariable("PATH", $Path, [System.EnvironmentVariableTarget]::Machine) 
```

## TODOs

Let LAN peers could clone from LAN before fetching update from remote.

## Windows Path

```
winget install --scope machine --id Microsoft.PowerShell --source winget
New-ItemProperty `
  -Path "HKLM:\SOFTWARE\OpenSSH" `
  -Name DefaultShell `
  -Value (Get-Command pwsh).Source `
  -PropertyType String `
  -Force

Restart-Service sshd
```
