# CMake generated Testfile for 
# Source directory: C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks
# Build directory: C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
if(CTEST_CONFIGURATION_TYPE MATCHES "^([Dd][Ee][Bb][Uu][Gg])$")
  add_test(cap_bench "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/Debug/cap_bench.exe")
  set_tests_properties(cap_bench PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks/CMakeLists.txt;78;add_test;C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ee][Aa][Ss][Ee])$")
  add_test(cap_bench "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/Release/cap_bench.exe")
  set_tests_properties(cap_bench PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks/CMakeLists.txt;78;add_test;C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Mm][Ii][Nn][Ss][Ii][Zz][Ee][Rr][Ee][Ll])$")
  add_test(cap_bench "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/MinSizeRel/cap_bench.exe")
  set_tests_properties(cap_bench PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks/CMakeLists.txt;78;add_test;C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ww][Ii][Tt][Hh][Dd][Ee][Bb][Ii][Nn][Ff][Oo])$")
  add_test(cap_bench "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/RelWithDebInfo/cap_bench.exe")
  set_tests_properties(cap_bench PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks/CMakeLists.txt;78;add_test;C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/benchmarks/CMakeLists.txt;0;")
else()
  add_test(cap_bench NOT_AVAILABLE)
endif()
subdirs("_deps/nanobench-build")
