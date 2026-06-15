# CMake generated Testfile for 
# Source directory: C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak
# Build directory: C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/leak
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
if(CTEST_CONFIGURATION_TYPE MATCHES "^([Dd][Ee][Bb][Uu][Gg])$")
  add_test(cap_leak_test "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/leak/Debug/cap_leak_test.exe")
  set_tests_properties(cap_leak_test PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak/CMakeLists.txt;81;add_test;C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ee][Aa][Ss][Ee])$")
  add_test(cap_leak_test "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/leak/Release/cap_leak_test.exe")
  set_tests_properties(cap_leak_test PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak/CMakeLists.txt;81;add_test;C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Mm][Ii][Nn][Ss][Ii][Zz][Ee][Rr][Ee][Ll])$")
  add_test(cap_leak_test "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/leak/MinSizeRel/cap_leak_test.exe")
  set_tests_properties(cap_leak_test PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak/CMakeLists.txt;81;add_test;C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ww][Ii][Tt][Hh][Dd][Ee][Bb][Ii][Nn][Ff][Oo])$")
  add_test(cap_leak_test "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/leak/RelWithDebInfo/cap_leak_test.exe")
  set_tests_properties(cap_leak_test PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak/CMakeLists.txt;81;add_test;C:/Users/David/Projects/crazy_asian_poker/poker_engine/tests/cpp/leak/CMakeLists.txt;0;")
else()
  add_test(cap_leak_test NOT_AVAILABLE)
endif()
