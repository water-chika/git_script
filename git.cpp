#include <iostream>
#include <filesystem>
#include <string>
#include <fstream>
#include <regex>
#include <optional>
#include <cstring>

#if WIN32
#include <process.h>
#define GIT_PATH "C:/Program Files/Git/git.exe"
#define PYTHON_PATH "C:/Program Files/Python/python.exe"
#else
#include <unistd.h>
#define GIT_PATH "/usr/bin/git"
#define PYTHON_PATH "/usr/bin/python"
#endif

int main(int argc, char* const argv[]) {
    if (argc == 3 && strcmp(argv[1], "clone") == 0 && argv[2][0] != '-') {
        return execl(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, argv[2], NULL);
    }
    else if (argc == 4 && strcmp(argv[1], "clone") == 0 && argv[2][0] != '-' && argv[3][0] != '-') {
        return execl(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, argv[2], "--worktree", argv[3], NULL);
    }
    else {
        return execv(GIT_PATH, argv);
    }
    return 0;
}
