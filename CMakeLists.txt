cmake_minimum_required(VERSION 3.18)
project(cap_poker_extensions CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ─────────────────────────────────────────────────────────────────
# Find Python + pybind11
# ─────────────────────────────────────────────────────────────────

# Use the Python from the active venv (set PYTHON_EXECUTABLE if needed)
find_package(Python COMPONENTS Interpreter Development REQUIRED)

# pybind11 via pip — locate it from Python itself
execute_process(
    COMMAND "${Python_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY
)
find_package(pybind11 CONFIG REQUIRED)

message(STATUS "Python: ${Python_EXECUTABLE}")
message(STATUS "pybind11: ${pybind11_DIR}")

# ─────────────────────────────────────────────────────────────────
# Compiler flags
# ─────────────────────────────────────────────────────────────────

if(MSVC)
    # /O2    = full optimisation
    # /arch:AVX2 = modern CPU instructions (popcount etc.)
    # /GL    = whole-program optimisation
    add_compile_options(/O2 /GL /arch:AVX2 /W3)
    add_link_options(/LTCG)
else()
    add_compile_options(-O3 -march=native -ffast-math -Wall)
endif()

# ─────────────────────────────────────────────────────────────────
# poker_eval  (existing evaluator — include so cap_equity can share
# the evaluator headers; rebuild here so both extensions match)
# ─────────────────────────────────────────────────────────────────

pybind11_add_module(poker_eval
    cpp/bindings/poker_eval_bindings.cpp
    cpp/evaluator/evaluator.cpp
    cpp/evaluator/evaluate_high.cpp
    cpp/evaluator/evaluate_holdem.cpp
    cpp/evaluator/evaluate_omaha.cpp
    cpp/evaluator/evaluate_make5.cpp
    cpp/evaluator/evaluate_draw.cpp
    cpp/evaluator/stub_evaluators.cpp
    cpp/evaluator/evaluate_low.cpp
)

target_include_directories(poker_eval PRIVATE
    cpp/evaluator
)

# ─────────────────────────────────────────────────────────────────
# cap_equity  (new equity calculator)
# ─────────────────────────────────────────────────────────────────

pybind11_add_module(cap_equity
    cpp/equity/equity_bindings.cpp
    cpp/equity/equity_calc.cpp
)

target_include_directories(cap_equity PRIVATE
    cpp/evaluator       # in case equity headers need evaluator types
    cpp/equity
)

# ─────────────────────────────────────────────────────────────────
# Install both .pyd/.so files into the poker_engine root so that
# `import poker_eval` and `import cap_equity` work from there
# ─────────────────────────────────────────────────────────────────

install(TARGETS poker_eval cap_equity
    LIBRARY DESTINATION .
    RUNTIME DESTINATION .   # Windows puts DLLs here
)
