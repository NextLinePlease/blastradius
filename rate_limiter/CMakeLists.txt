cmake_minimum_required(VERSION 3.14)

project(BlastRadiusRateLimiter)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Locate hiredis headers and library
find_path(HIREDIS_INCLUDE_DIR hiredis/hiredis.h REQUIRED)
find_library(HIREDIS_LIBRARY NAMES hiredis REQUIRED)

# Locate redis++ headers and library
find_path(REDIS_PLUS_PLUS_INCLUDE_DIR sw/redis++/redis++.h REQUIRED)
find_library(REDIS_PLUS_PLUS_LIBRARY NAMES redis++ REQUIRED)

# Build executable
add_executable(rate_limiter main.cpp)

# Include directories
target_include_directories(rate_limiter PRIVATE
    ${HIREDIS_INCLUDE_DIR}
    ${REDIS_PLUS_PLUS_INCLUDE_DIR}
)

# Link libraries
target_link_libraries(rate_limiter PRIVATE
    ${REDIS_PLUS_PLUS_LIBRARY}
    ${HIREDIS_LIBRARY}
    pthread
)