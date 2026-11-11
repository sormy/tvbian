# shellcheck shell=bash
# Sourced by every step that compiles: gcc and g++ through ccache, in the work volume or the
# directory CI keeps (CCACHE_DIR). TVB_BUILD_CACHE=0: a clean-room build, no compiler cache.
if [ "${TVB_BUILD_CACHE:-1}" = 1 ]; then
  export CCACHE_DIR=${CCACHE_DIR:-/work/ccache} CCACHE_MAXSIZE=${TVB_BUILD_CCACHE_SIZE:-5G}
  # a tree is extracted fresh each run: its files are new, their contents are not
  export CCACHE_SLOPPINESS=include_file_mtime,include_file_ctime
  # the wrappers' names: cmake and meson otherwise find cc and c++, which have none
  export PATH=/usr/lib/ccache:$PATH CC=gcc CXX=g++
fi
