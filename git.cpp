#include <iostream>
#include <filesystem>
#include <string>
#include <fstream>
#include <regex>
#include <optional>
#include <cstring>
#include <cassert>

#if WIN32
#include <process.h>
#define GIT_PATH "C:/Program Files/Git/cmd/git.exe"
std::string process_escape_character(const char* str) {
    std::string res{};
    std::string_view str_view{str};
    bool contain_space = str_view.end() != std::find(str_view.begin(), str_view.end(), ' ');
    if (contain_space) { res.push_back('\"'); }
    while (*str != '\0') {
        res.push_back(*str);
        str++;
    }
    if (contain_space) { res.push_back('\"'); }
    return res;
}
template<typename... Argv>
int exec_l(const char* path, Argv... argv){
    auto args = std::vector<const char*>{argv...};
    std::vector<std::string> processed_args{};
    for (auto& arg : args) {
        processed_args.push_back(
            process_escape_character(arg)
        );
        arg = processed_args.back().data();
    }
    args.push_back(NULL);
    return spawnv(_P_WAIT, path, args.data());
}
int exec_v(const char* path, char* argv[]) {
    std::vector<std::string> processed_args{};
    auto p = argv;
    while (*p != nullptr) {
        auto& arg = *p;
        p++;
        processed_args.push_back(
            process_escape_character(arg)
        );
    }
    std::vector<char*> args(processed_args.size()+1);
    std::transform(processed_args.begin(), processed_args.end(),
        args.begin(),
        [](auto& s) { return s.data(); }
    );
    args.back() = NULL;
    return spawnv(_P_WAIT, path, args.data());
}
template<typename... Argv>
int exec_lp(const char* path, Argv... argv){
    auto args = std::vector<const char*>{argv...};
    std::vector<std::string> processed_args{};
    for (auto& arg : args) {
        processed_args.push_back(
            process_escape_character(arg)
        );
        arg = processed_args.back().data();
    }
    args.push_back(NULL);
    assert(args.size() > 1);
    return spawnvp(_P_WAIT, path, args.data());
}
int exec_vp(const char* path, char* argv[]) {
    std::vector<std::string> processed_args{};
    auto p = argv;
    while (*p != nullptr) {
        auto& arg = *p;
        p++;
        processed_args.push_back(
            process_escape_character(arg)
        );
    }
    std::vector<char*> args(processed_args.size()+1);
    std::transform(processed_args.begin(), processed_args.end(),
        args.begin(),
        [](auto& s) { return s.data(); }
    );
    args.back() = NULL;
    return spawnvp(_P_WAIT, path, args.data());
}
template<typename... Argv>
int fork_exec_lp(const char* path, Argv... argv) {
    auto args = std::vector<const char*>{argv...};
    std::vector<std::string> processed_args{};
    for (auto& arg : args) {
        processed_args.push_back(
            process_escape_character(arg)
        );
        arg = processed_args.back().data();
    }
    args.push_back(NULL);
    return spawnvp(_P_WAIT, path, args.data());
}
#else
#include <unistd.h>
#include <sys/wait.h>
#define GIT_PATH "/usr/bin/git"

template<typename... Argv>
int exec_l(const char* path, Argv... argv){
    return execl(path, argv..., NULL);
}
int exec_v(const char* path, char** argv) {
    return execv(path, argv);
}
template<typename... Argv>
int exec_lp(const char* path, Argv... argv){
    return execlp(path, argv..., NULL);
}
int exec_vp(const char* path, char** argv) {
    return execvp(path, argv);
}
template<typename... Argv>
int fork_exec_lp(const char* path, Argv... argv) {
    pid_t ret = fork();
    if (ret == 0) {
        exec_lp(path, argv...);
        exit(-1); // This should not be called.
    }
    else {
        if (ret == -1) {
            std::cerr << "fork failed" << std::endl;
            return -1;
        }
        else {
            int wstatus = 0;
            wait(&wstatus);
            return wstatus;
        }
    }
}
#endif

int main(int argc, char* argv[]) {
    if (argc == 3 && strcmp(argv[1], "clone") == 0 && argv[2][0] != '-') {
        return exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, argv[2]);
    }
    else if (argc == 4 && strcmp(argv[1], "clone") == 0 && argv[2][0] != '-' && argv[3][0] != '-') {
        return exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, argv[2], "--worktree", argv[3]);
    }
    else if (argc == 4 && strcmp(argv[1], "submodule") == 0 &&
            strcmp(argv[2], "add") == 0 &&
            argv[3][0] != '-') {
        auto ret = fork_exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, argv[3]);
        return exec_lp(GIT_PATH, GIT_PATH, "submodule", "add", argv[3]);
    }
    else if (argc == 3 && strcmp(argv[1], "init") == 0 && argv[2][0] != '-') {
        return exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, "--init", "--worktree", argv[2]);
    }
    else if (argc == 5 && strcmp(argv[1], "submodule") == 0 &&
            strcmp(argv[2], "update") == 0 &&
            strcmp(argv[3], "--init") == 0 &&
            strcmp(argv[4], "--recursive") == 0) {
        return exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_SUBMODULE_PY_PATH, ".");
    }
    else {
        return exec_vp(GIT_PATH, argv);
    }
    return 0;
}
