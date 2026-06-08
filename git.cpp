#include <iostream>
#include <filesystem>
#include <string>
#include <fstream>
#include <regex>
#include <optional>
#include <cstring>

std::optional<std::filesystem::path> get_next_command(std::string command) {
    auto path = std::getenv("PATH");
    char sep = PATH_SEPERATOR;

    auto first_command = true;
    auto prev_path = path;
    while (*path != '\0') {
        if (*path == sep) {
            auto command_path = std::filesystem::path{prev_path, path-1} / "command";
            if (first_command) {
                first_command = false;
            }
            else if (exists(command_path)) {
                return command_path;
            }
        }
        ++path;
    }
    if (prev_path != path) {
            auto command_path = std::filesystem::path{prev_path, path-1} / "command";
            if (first_command) {
                first_command = false;
            }
            else if (exists(command_path)) {
                return command_path;
            }
    }
    return std::nullopt;
}

int main(int argc, const char* argv[]) {
    std::string cmd = "";

    auto git_path = get_next_command("git");

    if (git_path == std::nullopt) {
        std::cerr << "not found next git";
        return -1;
    }

    if (argc != 3 || strcmp(argv[1], "clone") != 0 || argv[2][0] == '-') {
        cmd = absolute(git_path.value());
        for (int i = 1; i < argc; i++) {
            cmd += " ";
            cmd += argv[i];
        }
    }
    else {
        cmd = "python " GIT_REPO_PY_PATH;
        cmd += " --git_path ";
        cmd += absolute(git_path.value());
        cmd += " ";
        cmd += argv[1];
    }
    system(cmd.c_str());
    return 0;
}
