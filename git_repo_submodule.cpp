#include <string>


int main(int argc, const char* argv[]) {
    std::string cmd = "python " GIT_REPO_SUBMODULE_PY_PATH;

    for (int i = 1; i < argc; i++) {
        cmd += " ";
        cmd += argv[i];
    }
    system(cmd.c_str());
    return 0;
}
