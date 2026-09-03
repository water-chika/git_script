#include <iostream>
#include <filesystem>
#include <string>
#include <fstream>
#include <regex>
#include <optional>
#include <cstring>
#include <cassert>
#include <format>
#include <algorithm>
#include <unordered_set>
#include <vector>

#if WIN32
#include <process.h>
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
    std::vector<std::string> processed_args(args.size());
    std::transform(args.begin(), args.end(),
        processed_args.begin(),
        process_escape_character
    );
    std::transform(processed_args.begin(), processed_args.end(),
        args.begin(),
        [](auto& str) { return str.data(); }
    );
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
    auto args = std::vector<const char*>{ argv... };
    std::vector<std::string> processed_args(args.size());
    std::transform(args.begin(), args.end(),
        processed_args.begin(),
        process_escape_character
    );
    std::transform(processed_args.begin(), processed_args.end(),
        args.begin(),
        [](auto& str) { return str.data(); }
    );
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

// Run a command whose arguments are only known at runtime. `args` must contain
// argv[0]; the NULL terminator is appended here.
int exec_args(const char* path, std::vector<std::string> args) {
    std::vector<char*> raw{};
    raw.reserve(args.size() + 1);
    for (auto& arg : args) {
        raw.push_back(arg.data());
    }
    raw.push_back(nullptr);
    return exec_vp(path, raw.data());
}

// Git's global options are accepted before the subcommand (`git -c k=v
// submodule ...`). Strip them so the subcommand match below is not defeated by
// their presence; the fall-through path still forwards the original argv.
std::vector<std::string> strip_global_options(int argc, char* argv[]) {
    static const std::unordered_set<std::string> takes_value{
        "-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"
    };
    static const std::unordered_set<std::string> standalone{
        "--no-pager", "--paginate", "-p", "-P", "--no-replace-objects",
        "--literal-pathspecs", "--no-optional-locks", "--bare"
    };

    auto args = std::vector<std::string>{};
    int i = 1;
    while (i < argc) {
        auto arg = std::string{argv[i]};
        if (takes_value.contains(arg)) {
            i += 2;
        }
        else if (standalone.contains(arg) || arg.starts_with("--git-dir=") ||
                 arg.starts_with("--work-tree=") || arg.starts_with("--namespace=") ||
                 arg.starts_with("--exec-path=")) {
            i += 1;
        }
        else {
            break;
        }
    }
    for (; i < argc; i++) {
        args.emplace_back(argv[i]);
    }
    return args;
}

int main(int argc, char* argv[]) {
    const auto args = strip_global_options(argc, argv);
    const auto n = args.size();

    if (n == 2 && args[0] == "clone" && args[1][0] != '-') {
        return exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, args[1].c_str());
    }
    else if (n == 3 && args[0] == "clone" && args[1][0] != '-' && args[2][0] != '-') {
        return exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, args[1].c_str(), "--worktree", args[2].c_str());
    }
    else if (n == 3 && args[0] == "submodule" && args[1] == "add" && args[2][0] != '-') {
        fork_exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, args[2].c_str());
        return exec_lp(GIT_PATH, GIT_PATH, "submodule", "add", args[2].c_str());
    }
    else if (n == 2 && args[0] == "init" && args[1][0] != '-') {
        return exec_lp(PYTHON_PATH, PYTHON_PATH, GIT_REPO_PY_PATH, "--init", "--worktree", args[1].c_str());
    }
    // `submodule update --init [--recursive] [<path>...]`: any number of paths,
    // defaulting to the whole worktree. git_submodule.py already accepts a list
    // of submodule paths, so no path has to be handled here specially.
    else if (n >= 3 && args[0] == "submodule" && args[1] == "update" &&
             std::find(args.begin() + 2, args.end(), "--init") != args.end()) {
        auto py_args = std::vector<std::string>{PYTHON_PATH, GIT_REPO_SUBMODULE_PY_PATH};
        auto paths = std::vector<std::string>{};
        bool understood = true;

        for (auto it = args.begin() + 2; it != args.end(); it++) {
            if (*it == "--init") {
                continue;
            }
            else if (*it == "--recursive" || *it == "--no-prompt" || *it == "--prompt") {
                py_args.push_back(*it);
            }
            else if ((*it)[0] == '-') {
                // An option git_submodule.py does not model (--depth, --remote,
                // --jobs, ...). Hand the whole command back to git rather than
                // silently ignoring it.
                understood = false;
                break;
            }
            else {
                paths.push_back(*it);
            }
        }

        if (understood) {
            if (paths.empty()) {
                paths.emplace_back(".");
            }
            py_args.insert(py_args.end(), paths.begin(), paths.end());
            return exec_args(PYTHON_PATH, py_args);
        }
    }

    if (exists(std::filesystem::path(GIT_PATH))) {
        return exec_vp(GIT_PATH, argv);
    }
    std::cerr << std::format("path not exist: {}", GIT_PATH) << std::endl;
    return 0;
}
