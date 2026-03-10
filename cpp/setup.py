from setuptools import setup, Extension
import pybind11

ext_modules = [
    Extension(
        'poker_eval._poker_eval',          # <--- sub‑module path
        sources=[
            'bindings/poker_eval_bindings.cpp',
            'evaluator/evaluator.cpp',
            'evaluator/evaluate_high.cpp',
            'evaluator/evaluate_holdem.cpp',    # <--- add
            'evaluator/evaluate_omaha.cpp',     # <--- add
            'evaluator/evaluate_make5.cpp',     # <--- add
            'evaluator/evaluate_draw.cpp',      # <--- add
            'evaluator/stub_evaluators.cpp'
        ],
        include_dirs=[pybind11.get_include(), 'evaluator'],
        language='c++',
    ),
]

setup(
    name='poker_eval',
    setup_requires=['pybind11>=2.10'],
    install_requires=['pybind11>=2.10'],
    ext_modules=ext_modules,
)

# sources = [
#     "bindings/poker_eval_bindings.cpp",
#     "evaluator/evaluator.cpp",
#     "evaluator/high.cpp",
#     "evaluator/stub_evaluators.cpp",
#     # "evaluator/badugi.cpp",
# ]