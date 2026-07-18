from setuptools import setup, Extension

class get_pybind_include(object):
    def __str__(self):
        import pybind11
        return pybind11.get_include()

_extra_compile_args = ['/std:c++17'] if __import__('sys').platform == 'win32' else ['-std=c++17']

ext_modules = [
    Extension(
        'poker_eval',
        sources=[
            'cpp/bindings/poker_eval_bindings.cpp',
            'cpp/evaluator/evaluator.cpp',
            'cpp/evaluator/evaluate_holdem.cpp',
            'cpp/evaluator/evaluate_omaha.cpp',
            'cpp/evaluator/evaluate_make5.cpp',
            'cpp/evaluator/evaluate_draw.cpp',
            'cpp/evaluator/stub_evaluators.cpp',
            'cpp/evaluator/evaluate_low.cpp',
        ],
        include_dirs=[get_pybind_include(), 'cpp/evaluator'],
        language='c++',
        extra_compile_args=_extra_compile_args,
    ),
    # NOTE: this extension was previously missing entirely, which is why
    # rebuilding via `setup.py build_ext` never picked up changes made to
    # equity_bindings.cpp / equity_calc.cpp / equity_calc.h — there was no
    # ext_modules entry telling setuptools those files belong to a
    # `cap_equity` module in the first place. Whatever `cap_equity` module
    # was being imported at runtime was a stray build artifact from
    # somewhere else (e.g. an old file sitting in site-packages or the
    # working directory), not the current sources.
    #
    # Adjust the `sources`/`include_dirs` paths below to match wherever
    # equity_bindings.cpp, equity_calc.cpp, and equity_calc.h actually
    # live in your repo (assumed here to mirror the poker_eval layout
    # under cpp/equity/ — update if yours differs).
    Extension(
        'cap_equity',
        sources=[
            'cpp/equity/equity_bindings.cpp',
            'cpp/equity/equity_calc.cpp',
        ],
        include_dirs=[get_pybind_include(), 'cpp/equity'],
        language='c++',
        extra_compile_args=_extra_compile_args,
    ),
]

setup(
    name='poker_eval',
    setup_requires=['pybind11>=2.10'],
    install_requires=['pybind11>=2.10'],
    ext_modules=ext_modules,
)