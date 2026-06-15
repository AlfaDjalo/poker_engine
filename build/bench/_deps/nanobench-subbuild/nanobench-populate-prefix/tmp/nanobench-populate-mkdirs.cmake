# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file LICENSE.rst or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION ${CMAKE_VERSION}) # this file comes with cmake

# If CMAKE_DISABLE_SOURCE_CHANGES is set to true and the source directory is an
# existing directory in our source tree, calling file(MAKE_DIRECTORY) on it
# would cause a fatal error, even though it would be a no-op.
if(NOT EXISTS "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-src")
  file(MAKE_DIRECTORY "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-src")
endif()
file(MAKE_DIRECTORY
  "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-build"
  "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-subbuild/nanobench-populate-prefix"
  "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-subbuild/nanobench-populate-prefix/tmp"
  "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-subbuild/nanobench-populate-prefix/src/nanobench-populate-stamp"
  "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-subbuild/nanobench-populate-prefix/src"
  "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-subbuild/nanobench-populate-prefix/src/nanobench-populate-stamp"
)

set(configSubDirs Debug)
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-subbuild/nanobench-populate-prefix/src/nanobench-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "C:/Users/David/Projects/crazy_asian_poker/poker_engine/build/bench/_deps/nanobench-subbuild/nanobench-populate-prefix/src/nanobench-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
