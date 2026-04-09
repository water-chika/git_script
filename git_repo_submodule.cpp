#include <string>
#include <filesystem>
#include <unordered_set>
#include <cstring>

#if _WIN32
constexpr auto sep = ';';
#else
constexpr auto sep = ':';
#endif

auto get_paths() {
    auto env_path = std::getenv("PATH");
    auto paths = std::unordered_set<std::filesystem::path>{};

    uint32_t s = 0;
    while ('\0' != env_path[s]) {
        auto next = strchr(env_path+s, sep);
        paths.emplace(std::string{env_path+s, next});
        s = next - env_path;
    }
    return paths;
}

auto get_all_commands(std::string command) {
    auto command_full_paths = std::unordered_set<std::filesystem::path>{};

    auto paths = get_paths();
    for (auto& path : paths) {
        auto command_full_path = path / command;
        if (exists(command_full_path)) {
            command_full_paths.emplace(command_full_path);
        }
    }
    return command_full_paths;
}

int main(int argc, const char* argv[]) {
    std::string cmd = "python " GIT_REPO_SUBMODULE_PY_PATH;

    for (int i = 1; i < argc; i++) {
        cmd += " ";
        cmd += argv[i];
    }
    system(cmd.c_str());
    return 0;
}
