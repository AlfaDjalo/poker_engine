from setuptools import setup, Extension

class get_pybind_include(object):
    def __str__(self):
        import pybind11
        return pybind11.get_include()

ext_modules = [
    Extension(
        'poker_eval._poker_eval',
        sources=[
            'bindings/poker_eval_bindings.cpp',
            'evaluator/evaluator.cpp',
            'evaluator/evaluate_high.cpp',
            'evaluator/evaluate_holdem.cpp',
            'evaluator/evaluate_omaha.cpp',
            'evaluator/evaluate_make5.cpp',
            'evaluator/evaluate_draw.cpp',
            'evaluator/stub_evaluators.cpp'
        ],
        include_dirs=[get_pybind_include(), 'evaluator'],
        language='c++',
    ),
]

setup(
    name='poker_eval',
    setup_requires=['pybind11>=2.10'],
    install_requires=['pybind11>=2.10'],
    ext_modules=ext_modules,
)
