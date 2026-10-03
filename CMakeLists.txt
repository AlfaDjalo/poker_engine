cmake_minimum_required(VERSION 3.18)

project(cap_poker_extensions LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)


# ------------------------------------------------------------
# Python + pybind11
# ------------------------------------------------------------

find_package(Python COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

message(STATUS "Python executable: ${Python_EXECUTABLE}")
message(STATUS "Python include: ${Python_INCLUDE_DIRS}")


# ------------------------------------------------------------
# Compiler options
# ------------------------------------------------------------

if(MSVC)

    add_compile_options(
        /O2
        /GL
        /arch:AVX2
        /W3
    )

    add_link_options(
        /LTCG
    )

else()

    add_compile_options(
        -O3
        -march=native
        -Wall
    )

endif()


# ------------------------------------------------------------
# poker_eval extension
# ------------------------------------------------------------

pybind11_add_module(
    poker_eval

    cpp/bindings/poker_eval_bindings.cpp

    cpp/evaluator/evaluator.cpp
    cpp/evaluator/evaluate_holdem.cpp
    cpp/evaluator/evaluate_omaha.cpp
    cpp/evaluator/evaluate_make5.cpp
    cpp/evaluator/evaluate_draw.cpp
    cpp/evaluator/stub_evaluators.cpp
    cpp/evaluator/evaluate_low.cpp
    cpp/evaluator/equity_mc.cpp
)


target_include_directories(
    poker_eval PRIVATE

    cpp/evaluator
)


# ------------------------------------------------------------
# cap_equity extension
# ------------------------------------------------------------

pybind11_add_module(
    cap_equity

    cpp/equity/equity_bindings.cpp
    cpp/equity/equity_calc.cpp
)


target_include_directories(
    cap_equity PRIVATE

    cpp/equity
    cpp/evaluator
)


# ------------------------------------------------------------
# Install extensions into Python package
# ------------------------------------------------------------

install(
    TARGETS
        poker_eval
        cap_equity

    LIBRARY DESTINATION poker_engine
    RUNTIME DESTINATION poker_engine
)