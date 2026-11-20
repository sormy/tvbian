# Each test is one source written against QtWebEngine's API, built for QtWebEngine and for qtwpewebkit:
# run.sh runs both and reports where qtwpewebkit behaves differently
find_package(Qt6 REQUIRED COMPONENTS Test WebChannel)
find_package(Qt6 QUIET OPTIONAL_COMPONENTS WebEngineWidgets)

set(DIFFERENTIAL_TESTS navigation javascript content schemes webchannel downloads cookies widget interception)
set(QTWPEWEBKIT_ONLY_TESTS webwidget adblock)

function(add_web_test name backend)
    set(target tst_${name}_${backend})
    add_executable(${target} tst_${name}.cpp common/webtest.h)
    target_include_directories(${target} PRIVATE common)
    target_link_libraries(${target} PRIVATE Qt6::Test Qt6::WebChannel ${ARGN})
endfunction()

foreach(name IN LISTS DIFFERENTIAL_TESTS)
    if(TARGET Qt6::WebEngineWidgets)
        add_web_test(${name} qtwebengine Qt6::WebEngineWidgets)
    endif()
    add_web_test(${name} qtwpewebkit qtwpewebkit)
endforeach()
foreach(name IN LISTS QTWPEWEBKIT_ONLY_TESTS)
    add_web_test(${name} qtwpewebkit qtwpewebkit)
endforeach()

# Served at qrc:/schemes/
foreach(backend IN ITEMS qtwebengine qtwpewebkit)
    if(TARGET tst_schemes_${backend})
        qt_add_resources(tst_schemes_${backend} schemes_resources PREFIX /schemes BASE resources
            FILES resources/page.html resources/page.js)
    endif()
endforeach()

add_test(NAME differential COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/run.sh ${CMAKE_CURRENT_BINARY_DIR})
