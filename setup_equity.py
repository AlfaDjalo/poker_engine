# setup_equity.py
# Build the cap_equity extension module.
#
# Run from the poker_engine root:
#   pip install pybind11 --break-system-packages
#   pip install -e . --break-system-packages         # builds poker_eval first
#   python setup_equity.py build_ext --inplace       # builds cap_equity
#
# Or add the Extension below to the existing setup.py ext_modules list.
#
# ─────────────────────────────────────────────────────────────────
# RECOMMENDED: merge this into your existing poker_engine/setup.py
# by appending the Extension block below to ext_modules.
# ─────────────────────────────────────────────────────────────────

from setuptools import setup, Extension


def get_pybind_include():
    try:
        import pybind11
        return pybind11.get_include()
    except ImportError as e:
        raise ImportError(
            "pybind11 is required. Run: pip install pybind11"
        ) from e


cap_equity_ext = Extension(
    "cap_equity",
    sources=[
        # New equity calculator sources (add to poker_engine/cpp/equity/)
        "cpp/equity/equity_bindings.cpp",
        "cpp/equity/equity_calc.cpp",
    ],
    include_dirs=[
        get_pybind_include(),
        "cpp/evaluator",    # for existing evaluator headers if needed
        "cpp/equity",       # our new headers
    ],
    extra_compile_args=[
        "-O3",
        "-std=c++17",
        "-march=native",    # enables popcount, etc.
        "-ffast-math",
    ],
    language="c++",
)

setup(
    name="cap_equity",
    version="1.0.0",
    setup_requires=["pybind11>=2.10"],
    ext_modules=[cap_equity_ext],
)