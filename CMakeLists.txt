cmake_minimum_required(VERSION 3.20)

project(git_repo)

add_executable(git_repo
    git_repo.cpp)

target_compile_features(git_repo PUBLIC cxx_std_20)

target_compile_definitions(git_repo PUBLIC GIT_REPO_PY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/git_repo.py")

add_executable(git_repo_submodule
    git_repo_submodule.cpp)

target_compile_features(git_repo_submodule PUBLIC cxx_std_20)

target_compile_definitions(git_repo_submodule PUBLIC GIT_REPO_SUBMODULE_PY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/git_submodule.py")
