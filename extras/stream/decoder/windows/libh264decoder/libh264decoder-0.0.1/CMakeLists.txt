cmake_minimum_required(VERSION 3.4.1)
project (robomaster_video_and_audio_decoder)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_BUILD_TYPE Release)
SET(LIBRARY_OUTPUT_PATH ${CMAKE_SOURCE_DIR}/output)

set(PYBIND11_PYTHON_VERSION 3)
add_subdirectory(pybind11)

SET(FFMEPG_INCLUDE_DIRS "${CMAKE_SOURCE_DIR}/src/ffmpeg-4.2.2-win64-dev/include")
SET(FFMEPG_LIBRARIES_PATH "${CMAKE_SOURCE_DIR}/src/ffmpeg-4.2.2-win64-dev/lib")
pybind11_add_module(libh264decoder src/h264decoder.cpp)
target_link_libraries(libh264decoder PRIVATE
        ${FFMEPG_LIBRARIES_PATH}/avcodec.lib
        ${FFMEPG_LIBRARIES_PATH}/swscale.lib
        ${FFMEPG_LIBRARIES_PATH}/avutil.lib)
target_include_directories(libh264decoder PRIVATE ${FFMEPG_INCLUDE_DIRS})
