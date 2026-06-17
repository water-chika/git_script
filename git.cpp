#include <iostream>
#include <filesystem>
#include <string>
#include <fstream>
#include <regex>
#include <optional>
#include <cstring>

#if WIN32
#include <process.h>
#define GIT_PATH "C:/Program Files/Git/cmd/git.exe"
template<typename... Argv>
int exec_l(const char* path, Argv... argv){
    return spawnl(_P_WAIT, path, argv..., NULL);
}
int exec_v(const char* path, char* argv[]) {
    return spawnv(_P_WAIT, path, argv);
}
#else
#include <unistd.h>
#define GIT_PATH "/usr/bin/git"

template<typename... Argv>
int exec_l(const char* path, Argv... argv){
    return execl(path, argv..., NULL);
}
int exec_v(const char* path, char** argv) {
    return execv(path, argv);
}
#endif

int main(int argc, char* argv[]) {
    if (argc == 3 && strcmp(argv[1], "clone") == 0 && argv[2][0] != '-') {
        return exec_l(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, argv[2]);
    }
    else if (argc == 4 && strcmp(argv[1], "clone") == 0 && argv[2][0] != '-' && argv[3][0] != '-') {
        return exec_l(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, argv[2], "--worktree", argv[3]);
    }
    else {
        return exec_v(GIT_PATH, argv);
    }
    return 0;
}
