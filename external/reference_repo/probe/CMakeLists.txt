cmake_minimum_required(VERSION 3.5)
project(n_monitor_probe)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(ASCEND_INCLUDE_CANDIDATES)
set(ASCEND_LIB_CANDIDATES)

if(DEFINED ENV{ASCEND_TOOLKIT_HOME})
    list(APPEND ASCEND_INCLUDE_CANDIDATES
        "$ENV{ASCEND_TOOLKIT_HOME}/include"
        "$ENV{ASCEND_TOOLKIT_HOME}/aarch64-linux/include"
    )
    list(APPEND ASCEND_LIB_CANDIDATES
        "$ENV{ASCEND_TOOLKIT_HOME}/lib64"
        "$ENV{ASCEND_TOOLKIT_HOME}/aarch64-linux/lib64"
    )
endif()

list(APPEND ASCEND_INCLUDE_CANDIDATES
    "/usr/local/Ascend/ascend-toolkit/latest/include"
    "/usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/include"
    "/usr/local/Ascend/cann-8.5.0/include"
    "/usr/local/Ascend/cann-8.5.0/aarch64-linux/include"
)
list(APPEND ASCEND_LIB_CANDIDATES
    "/usr/local/Ascend/ascend-toolkit/latest/lib64"
    "/usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/lib64"
    "/usr/local/Ascend/cann-8.5.0/lib64"
    "/usr/local/Ascend/cann-8.5.0/aarch64-linux/lib64"
)

foreach(candidate IN LISTS ASCEND_INCLUDE_CANDIDATES)
    if(EXISTS "${candidate}")
        include_directories("${candidate}")
    endif()
endforeach()

foreach(candidate IN LISTS ASCEND_LIB_CANDIDATES)
    if(EXISTS "${candidate}")
        link_directories("${candidate}")
    endif()
endforeach()

add_executable(memcpy_benchmark src/memcpy_benchmark.cpp)
target_link_libraries(memcpy_benchmark PRIVATE ascendcl pthread numa)
