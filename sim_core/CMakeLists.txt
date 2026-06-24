cmake_minimum_required(VERSION 3.18)
project(alphaforge_sim_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Vendored matching engine (git submodule). We only need its headers.
set(ENGINE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../external/HFTMatchingEngine")
if(NOT EXISTS "${ENGINE_DIR}/defs.h")
    message(FATAL_ERROR
        "HFTMatchingEngine headers not found at ${ENGINE_DIR}. "
        "Run: git submodule update --init --recursive")
endif()

# Locate Python + nanobind (installed in the active venv via `uv sync`).
find_package(Python 3.12 COMPONENTS Interpreter Development.Module REQUIRED)
execute_process(
    COMMAND "${Python_EXECUTABLE}" -c "import nanobind; print(nanobind.cmake_dir())"
    OUTPUT_VARIABLE NB_CMAKE_DIR OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE NB_RESULT)
if(NOT NB_RESULT EQUAL 0)
    message(FATAL_ERROR "nanobind not found. Run: uv pip install nanobind")
endif()
list(APPEND CMAKE_PREFIX_PATH "${NB_CMAKE_DIR}")
find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(alphaforge_sim_native STABLE_ABI NB_STATIC src/bindings.cpp)

target_include_directories(alphaforge_sim_native PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${ENGINE_DIR}")

target_compile_options(alphaforge_sim_native PRIVATE
    $<$<CONFIG:Release>:-O3>
    $<$<CONFIG:Release>:-march=native>
    -Wall -Wextra)
