#include <algorithm>
#include <cerrno>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#if defined(_WIN32)
#include <process.h>
#else
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace fs = std::filesystem;
using Args = std::vector<std::string>;

static std::vector<char*> raw_args(Args& args) {
    std::vector<char*> raw;
    raw.reserve(args.size() + 1);
    for (auto& arg : args) raw.push_back(arg.data());
    raw.push_back(nullptr);
    return raw;
}

static int replace_process(const char* path, Args args) {
    auto raw = raw_args(args);
#if defined(_WIN32)
    return _spawnv(_P_WAIT, path, raw.data());
#else
    execv(path, raw.data());
    std::cerr << "cannot execute " << path << ": " << std::strerror(errno) << '\n';
    return errno == ENOENT ? 127 : 126;
#endif
}

static int run_child(const char* path, Args args) {
#if defined(_WIN32)
    auto raw = raw_args(args);
    return _spawnv(_P_WAIT, path, raw.data());
#else
    const pid_t child = fork();
    if (child < 0) {
        std::cerr << "fork failed: " << std::strerror(errno) << '\n';
        return 126;
    }
    if (child == 0) {
        auto raw = raw_args(args);
        execv(path, raw.data());
        std::cerr << "cannot execute " << path << ": " << std::strerror(errno) << '\n';
        _exit(errno == ENOENT ? 127 : 126);
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {
        if (errno == EINTR) continue;
        std::cerr << "waitpid failed: " << std::strerror(errno) << '\n';
        return 126;
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return 126;
#endif
}

struct Invocation {
    Args command;
    fs::path directory = fs::current_path();
    bool interceptable = true;
};

static Invocation parse_invocation(int argc, char* argv[]) {
    Invocation invocation;
    int i = 1;
    while (i < argc) {
        const std::string arg = argv[i];
        if (arg == "-C") {
            if (++i >= argc) {
                invocation.interceptable = false;
                return invocation;
            }
            fs::path next = argv[i++];
            invocation.directory = next.is_absolute() ? next : invocation.directory / next;
            invocation.directory = fs::absolute(invocation.directory).lexically_normal();
        } else if (arg.starts_with("-C") && arg.size() > 2) {
            fs::path next = arg.substr(2);
            invocation.directory = next.is_absolute() ? next : invocation.directory / next;
            invocation.directory = fs::absolute(invocation.directory).lexically_normal();
            ++i;
        } else if (!arg.empty() && arg[0] == '-') {
            // Global options can affect repository selection or helper Git calls.
            // Delegate them unchanged until the helper interface models them.
            invocation.interceptable = false;
            return invocation;
        } else {
            break;
        }
    }
    for (; i < argc; ++i) invocation.command.emplace_back(argv[i]);
    return invocation;
}

static fs::path absolute_from(const fs::path& base, const std::string& path) {
    fs::path result = path;
    return (result.is_absolute() ? result : base / result).lexically_normal();
}

static std::string repo_name_from_url(std::string url) {
    while (!url.empty() && (url.back() == '/' || url.back() == '\\')) url.pop_back();
    const auto slash = url.find_last_of("/\\:");
    std::string name = slash == std::string::npos ? url : url.substr(slash + 1);
    if (name.ends_with(".git")) name.resize(name.size() - 4);
    return name;
}

struct ClonePlan {
    std::string url;
    std::optional<std::string> destination;
    bool recursive = false;
};

static std::optional<ClonePlan> parse_clone(const Args& args) {
    ClonePlan plan;
    Args operands;
    bool options = true;
    for (size_t i = 1; i < args.size(); ++i) {
        const auto& arg = args[i];
        if (options && arg == "--") { options = false; continue; }
        if (options && (arg == "--recursive" || arg == "--recurse-submodules")) {
            plan.recursive = true;
        } else if (options && arg == "--no-recurse-submodules") {
            plan.recursive = false;
        } else if (options && !arg.empty() && arg[0] == '-') {
            return std::nullopt;
        } else {
            operands.push_back(arg);
        }
    }
    if (operands.empty() || operands.size() > 2) return std::nullopt;
    plan.url = operands[0];
    if (operands.size() == 2) plan.destination = operands[1];
    return plan;
}

struct InitPlan {
    std::string directory = ".";
    std::string branch = "main";
};

static std::optional<InitPlan> parse_init(const Args& args) {
    InitPlan plan;
    Args operands;
    bool options = true;
    for (size_t i = 1; i < args.size(); ++i) {
        const auto& arg = args[i];
        if (options && arg == "--") { options = false; continue; }
        if (options && (arg == "-b" || arg == "--initial-branch")) {
            if (++i >= args.size()) return std::nullopt;
            plan.branch = args[i];
        } else if (options && arg.starts_with("--initial-branch=")) {
            plan.branch = arg.substr(std::string("--initial-branch=").size());
            if (plan.branch.empty()) return std::nullopt;
        } else if (options && !arg.empty() && arg[0] == '-') {
            return std::nullopt;
        } else {
            operands.push_back(arg);
        }
    }
    if (operands.size() > 1 || plan.branch.empty()) return std::nullopt;
    if (!operands.empty()) plan.directory = operands[0];
    return plan;
}

struct AddPlan { std::string url; std::optional<std::string> path; };
static std::optional<AddPlan> parse_submodule_add(const Args& args) {
    Args operands;
    bool options = true;
    for (size_t i = 2; i < args.size(); ++i) {
        const auto& arg = args[i];
        if (options && arg == "--") { options = false; continue; }
        if (options && !arg.empty() && arg[0] == '-') return std::nullopt;
        operands.push_back(arg);
    }
    if (operands.empty() || operands.size() > 2) return std::nullopt;
    return AddPlan{operands[0], operands.size() == 2 ? std::optional{operands[1]} : std::nullopt};
}

struct UpdatePlan { Args helper_options; Args paths; };
static std::optional<UpdatePlan> parse_submodule_update(const Args& args) {
    UpdatePlan plan;
    bool options = true;
    bool init = false;
    for (size_t i = 2; i < args.size(); ++i) {
        const auto& arg = args[i];
        if (options && arg == "--") { options = false; continue; }
        if (options && arg == "--init") init = true;
        else if (options && (arg == "--recursive" || arg == "--prompt" || arg == "--no-prompt"))
            plan.helper_options.push_back(arg);
        else if (options && !arg.empty() && arg[0] == '-') return std::nullopt;
        else plan.paths.push_back(arg);
    }
    if (!init) return std::nullopt;
    if (plan.paths.empty()) plan.paths.emplace_back(".");
    return plan;
}

int main(int argc, char* argv[]) {
    const auto invocation = parse_invocation(argc, argv);
    if (invocation.interceptable && !invocation.command.empty()) {
        const auto& args = invocation.command;
        if (args[0] == "clone") {
            if (auto plan = parse_clone(args)) {
                const std::string destination = plan->destination.value_or(repo_name_from_url(plan->url));
                Args helper{PYTHON_PATH, GIT_REPO_PY_PATH, "--worktree",
                            absolute_from(invocation.directory, destination).string()};
                if (plan->recursive) helper.emplace_back("--recursive");
                helper.emplace_back("--");
                helper.emplace_back(plan->url);
                return replace_process(PYTHON_PATH, std::move(helper));
            }
        } else if (args[0] == "init") {
            if (auto plan = parse_init(args)) {
                Args helper{PYTHON_PATH, GIT_REPO_PY_PATH, "--init", "--worktree",
                            absolute_from(invocation.directory, plan->directory).string(),
                            "--initial-branch", plan->branch};
                return replace_process(PYTHON_PATH, std::move(helper));
            }
        } else if (args.size() >= 2 && args[0] == "submodule" && args[1] == "add") {
            if (auto plan = parse_submodule_add(args)) {
                const auto destination = plan->path.value_or(repo_name_from_url(plan->url));
                Args helper{PYTHON_PATH, GIT_REPO_PY_PATH, "--worktree",
                            absolute_from(invocation.directory, destination).string(), "--",
                            plan->url};
                const int status = run_child(PYTHON_PATH, std::move(helper));
                if (status != 0) return status;
                Args original;
                original.reserve(argc);
                original.emplace_back(GIT_PATH);
                for (int i = 1; i < argc; ++i) original.emplace_back(argv[i]);
                return replace_process(GIT_PATH, std::move(original));
            }
        } else if (args.size() >= 2 && args[0] == "submodule" && args[1] == "update") {
            if (auto plan = parse_submodule_update(args)) {
                Args helper{PYTHON_PATH, GIT_REPO_SUBMODULE_PY_PATH, "--working-directory",
                            invocation.directory.string()};
                helper.insert(helper.end(), plan->helper_options.begin(), plan->helper_options.end());
                helper.emplace_back("--");
                helper.insert(helper.end(), plan->paths.begin(), plan->paths.end());
                return replace_process(PYTHON_PATH, std::move(helper));
            }
        }
    }

    if (!fs::exists(GIT_PATH)) {
        std::cerr << "path not exist: " << GIT_PATH << '\n';
        return 127;
    }
    Args original;
    original.reserve(argc);
    original.emplace_back(GIT_PATH);
    for (int i = 1; i < argc; ++i) original.emplace_back(argv[i]);
    return replace_process(GIT_PATH, std::move(original));
}
