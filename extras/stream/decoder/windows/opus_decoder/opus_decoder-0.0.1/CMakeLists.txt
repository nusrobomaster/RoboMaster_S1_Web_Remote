cmake_minimum_required(VERSION 3.4.1)
project (robomaster_video_and_audio_decoder)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_BUILD_TYPE Release)
SET(LIBRARY_OUTPUT_PATH ${CMAKE_SOURCE_DIR}/output)

set(PYBIND11_PYTHON_VERSION 3)
add_subdirectory(pybind11)

# 指定opus的头文件目录和库文件
SET(OPUS_INCLUDE_DIRS "${CMAKE_SOURCE_DIR}/src/opus-share/include")
SET(OPUS_LIBRARIES "${CMAKE_SOURCE_DIR}/src/opus-share/lib/opus.lib")
pybind11_add_module(opus_decoder src/opus_decoder.cpp)
target_link_libraries(opus_decoder PRIVATE ${OPUS_LIBRARIES})
target_include_directories(opus_decoder PRIVATE ${OPUS_INCLUDE_DIRS})
