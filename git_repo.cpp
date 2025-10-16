#include <iostream>
#include <filesystem>
#include <string>
#include <fstream>
#include <regex>

struct submodule {
    std::filesystem::path path;
    std::string url;
};

std::vector<submodule> parse_submodules(std::filesystem::path submodules_file_path) {
    std::vector<submodule> submodules{};
    auto in = std::ifstream{submodules_file_path};
    auto line = std::string{};

    std::filesystem::path path;
    std::string url;

    int state = 0;
    while (std::getline(in, line)) {
        switch (state){
        case 0:
            if (line.starts_with("[submodule ")) {
               state = 1;
            }
        case 1:
            if (line.starts_with("[submodule ")) {
                submodules.emplace_back(path, url);
            }
            else if (line.starts_with("\tpath = ")) {
                path = line.substr(8);
            }
            else if (line.starts_with("\turl = ")) {
                url = line.substr(7);
            }
            else {
                std::cout << "unknown line : " << line;
            }
        }
    }
    if (state = 1) {
        submodules.emplace_back(path, url);
    }

    return submodules;
}


int main(int argc, const char* argv[]) {
    std::string cmd = "python " GIT_REPO_PY_PATH;

    for (int i = 1; i < argc; i++) {
        cmd += " ";
        cmd += argv[i];
    }
    system(cmd.c_str());
    return 0;
}