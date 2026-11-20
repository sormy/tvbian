include(CMakeFindDependencyMacro)
find_dependency(Qt6 COMPONENTS Widgets Network OpenGL OpenGLWidgets)
include("${CMAKE_CURRENT_LIST_DIR}/QtWpeWebKitTargets.cmake")
