from setuptools import setup, Extension


def get_pybind_include():
    try:
        import pybind11
        return pybind11.get_include()
    except ImportError as e:
        raise ImportError(
            "pybind11 is required to build the native extension. "
            "Install pybind11 or add it to build-system.requires in pyproject.toml."
        ) from e


ext_modules = [
    Extension(
        'poker_eval',
        ['cpp/bindings/poker_eval_bindings.cpp', 'cpp/evaluator/evaluator.cpp'],
        include_dirs=[get_pybind_include(), 'cpp/evaluator'],
        language='c++',
    ),
]

setup(
    name='poker_eval',
    setup_requires=['pybind11>=2.10'],
    ext_modules=ext_modules,
)