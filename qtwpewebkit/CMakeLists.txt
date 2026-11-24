cmake_minimum_required(VERSION 3.22)
project(qtwpewebkit VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

include(GNUInstallDirs)
find_package(Qt6 REQUIRED COMPONENTS Widgets Network OpenGL OpenGLWidgets WebChannel)
find_package(PkgConfig REQUIRED)
pkg_check_modules(WPE REQUIRED IMPORTED_TARGET wpe-webkit-2.0 wpe-platform-2.0 egl glesv2)

# WebKit's frames handed to the compositor on a subsurface: the protocols' client code
pkg_check_modules(WAYLAND REQUIRED IMPORTED_TARGET wayland-client)
pkg_get_variable(WAYLAND_PROTOCOLS wayland-protocols pkgdatadir)
find_program(WAYLAND_SCANNER wayland-scanner REQUIRED)
foreach(protocol stable/linux-dmabuf/linux-dmabuf-v1 stable/viewporter/viewporter)
    get_filename_component(name ${protocol} NAME)
    set(xml ${WAYLAND_PROTOCOLS}/${protocol}.xml)
    add_custom_command(OUTPUT ${name}-client-protocol.h ${name}-protocol.c
        COMMAND ${WAYLAND_SCANNER} client-header ${xml} ${name}-client-protocol.h
        COMMAND ${WAYLAND_SCANNER} private-code ${xml} ${name}-protocol.c
        DEPENDS ${xml})
    list(APPEND PROTOCOL_SOURCES ${CMAKE_CURRENT_BINARY_DIR}/${name}-client-protocol.h ${CMAKE_CURRENT_BINARY_DIR}/${name}-protocol.c)
endforeach()

# QtWebEngine's API over WebKit, for applications written against QtWebEngine
file(GLOB COMPAT_HEADERS compat/include/*.h)
file(GLOB COMPAT_SOURCES compat/src/*.cpp)

add_library(qtwpewebkit SHARED src/keyboard.cpp src/platform.cpp src/subsurface.cpp src/videoplanes.cpp src/videosubsurface.cpp
    src/wayland.cpp src/webwidget.cpp ${PROTOCOL_SOURCES} ${COMPAT_HEADERS} ${COMPAT_SOURCES})
set_target_properties(qtwpewebkit PROPERTIES VERSION ${PROJECT_VERSION} SOVERSION ${PROJECT_VERSION_MAJOR})
target_include_directories(qtwpewebkit
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/compat/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}/qtwpewebkit>
    PRIVATE compat/src videoplane webprocess ${CMAKE_CURRENT_BINARY_DIR})
# GLib's headers use Qt's keywords as names
target_compile_definitions(qtwpewebkit PRIVATE QT_NO_KEYWORDS)
target_link_libraries(qtwpewebkit PUBLIC Qt6::Widgets Qt6::Network Qt6::OpenGL Qt6::OpenGLWidgets PRIVATE Qt6::WebChannel Qt6::GuiPrivate PkgConfig::WPE PkgConfig::WAYLAND)

# Loaded into each web process to put its requests to the interceptors; found beside libqtwpewebkit
pkg_check_modules(WPE_WEB_PROCESS REQUIRED IMPORTED_TARGET wpe-web-process-extension-2.0 gio-unix-2.0)
set(WEB_PROCESS_EXTENSIONS_DIR qtwpewebkit/web-process-extensions)
add_library(qtwpewebkit-requests MODULE webprocess/requests.cpp)
target_link_libraries(qtwpewebkit-requests PRIVATE PkgConfig::WPE_WEB_PROCESS)
set_target_properties(qtwpewebkit-requests PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/${WEB_PROCESS_EXTENSIONS_DIR})

# Loaded into each web process by GStreamer: its videos' frames go to the UI process's display planes
pkg_check_modules(GST_VIDEO REQUIRED IMPORTED_TARGET gstreamer-video-1.0 gstreamer-allocators-1.0)
add_library(gsttvbvideoplane MODULE videoplane/sink.c)
target_link_libraries(gsttvbvideoplane PRIVATE PkgConfig::GST_VIDEO)

add_executable(qtwpewebkit-demo demo/main.cpp)
target_link_libraries(qtwpewebkit-demo PRIVATE qtwpewebkit PkgConfig::WPE)
target_compile_definitions(qtwpewebkit-demo PRIVATE QT_NO_KEYWORDS)

install(TARGETS qtwpewebkit EXPORT QtWpeWebKitTargets)
install(TARGETS qtwpewebkit-requests DESTINATION ${CMAKE_INSTALL_LIBDIR}/${WEB_PROCESS_EXTENSIONS_DIR})
install(TARGETS qtwpewebkit-demo)
install(TARGETS gsttvbvideoplane DESTINATION ${CMAKE_INSTALL_LIBDIR}/gstreamer-1.0)
install(DIRECTORY compat/include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/qtwpewebkit)
install(FILES src/webwidget.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/qtwpewebkit)
install(EXPORT QtWpeWebKitTargets NAMESPACE QtWpeWebKit:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/QtWpeWebKit)
install(FILES cmake/QtWpeWebKitConfig.cmake DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/QtWpeWebKit)

option(BUILD_TESTING "Build the differential tests in tests/" OFF)
include(CTest)
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
