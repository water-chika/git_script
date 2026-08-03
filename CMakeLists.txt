cmake_minimum_required(VERSION 3.20)

project(git_repo)

add_executable(git_repo
    git_repo.cpp)

target_compile_features(git_repo PUBLIC cxx_std_20)

target_compile_definitions(git_repo PUBLIC
	GIT_REPO_PY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/git_repo.py"
	GIT_REPO_SUBMODULE_PY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/git_submodule.py"
)

if (WIN32)
set(GIT_PATH "C:/Program Files/Git/cmd/git.exe" CACHE FILEPATH "original git path")
else()
set(GIT_PATH "/usr/bin/git" CACHE FILEPATH "original git path")
endif()
if (NOT EXISTS "${GIT_PATH}")
message(FATAL_ERROR "not exists original git path: ${GIT_PATH}")
endif()

if (NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/config.json")
file(GENERATE OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/config.json"
    CONTENT
"{
    \"repo_dir\": \"/repos\",
    \"build_dir\": \"/builds\",
    \"git_path\": \"${GIT_PATH}\"
}"
)
endif()

add_executable(git
    git.cpp
)
target_compile_features(git PUBLIC cxx_std_20)

find_program(PYTHON_PATH python)
target_compile_definitions(git PUBLIC
    GIT_REPO_PY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/git_repo.py"
	GIT_REPO_SUBMODULE_PY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/git_submodule.py"
    PYTHON_PATH="${PYTHON_PATH}"
    GIT_PATH="${GIT_PATH}"
)
if (WIN32)
    target_compile_definitions(git PUBLIC PATH_SEPERATOR=';')
else()
    target_compile_definitions(git PUBLIC PATH_SEPERATOR=':')
endif()

add_executable(git_repo_submodule
    git_repo_submodule.cpp)

target_compile_features(git_repo_submodule PUBLIC cxx_std_20)

target_compile_definitions(git_repo_submodule PUBLIC GIT_REPO_SUBMODULE_PY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/git_submodule.py")

add_executable(git_build
    git_build.cpp)

target_compile_features(git_build PUBLIC cxx_std_20)

target_compile_definitions(git_build PUBLIC GIT_BUILD_PY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/git_build.py")
