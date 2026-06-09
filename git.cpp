#include <iostream>
#include <filesystem>
#include <string>
#include <fstream>
#include <regex>
#include <optional>
#include <cstring>

#if WIN32
#include <process.h>
#define GIT_PATH "C:/Program Files/Git/git"
#else
#include <unistd.h>
#define GIT_PATH "/usr/bin/git"
#endif

int main(int argc, char* const argv[]) {
    if (argc != 3 || strcmp(argv[1], "clone") != 0 || argv[2][0] == '-') {
        execv(GIT_PATH, argv);
    }
    else {
        execl("python", GIT_REPO_PY_PATH, argv[2]);
    }
    return 0;
}
