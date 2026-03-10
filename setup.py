from setuptools import setup, Extension
import pybind11

ext_modules = [
    Extension(
        'poker_eval',
        ['cpp/bindings/poker_eval_bindings.cpp', 'cpp/evaluator/evaluator.cpp'],
        include_dirs=[pybind11.get_include(), 'cpp/evaluator'],
        language='c++',
    ),
]

setup(
    name='poker_eval',
    ext_modules=ext_modules,
)