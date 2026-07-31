from setuptools import setup, Extension, find_packages


class get_pybind_include:
    def __str__(self):
        import pybind11
        return pybind11.get_include()


import sys

_extra_compile_args = (
    ["/std:c++17"]
    if sys.platform == "win32"
    else ["-std=c++17"]
)

ext_modules = [
    Extension(
        "poker_eval",
        sources=[
            "cpp/bindings/poker_eval_bindings.cpp",
            "cpp/evaluator/evaluator.cpp",
            "cpp/evaluator/evaluate_holdem.cpp",
            "cpp/evaluator/evaluate_omaha.cpp",
            "cpp/evaluator/evaluate_make5.cpp",
            "cpp/evaluator/evaluate_draw.cpp",
            "cpp/evaluator/stub_evaluators.cpp",
            "cpp/evaluator/evaluate_low.cpp",
        ],
        include_dirs=[
            get_pybind_include(),
            "cpp/evaluator",
        ],
        language="c++",
        extra_compile_args=_extra_compile_args,
    ),
    Extension(
        "cap_equity",
        sources=[
            "cpp/equity/equity_bindings.cpp",
            "cpp/equity/equity_calc.cpp",
        ],
        include_dirs=[
            get_pybind_include(),
            "cpp/equity",
        ],
        language="c++",
        extra_compile_args=_extra_compile_args,
    ),
]

setup(
    name="poker_engine",
    version="0.1.0",
    packages=find_packages(
        include=["poker_engine", "poker_engine.*"]
    ),
    include_package_data=True,
    ext_modules=ext_modules,
)