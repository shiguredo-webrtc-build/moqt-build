cmake_minimum_required(VERSION 3.16)
project(moqt_test)

# インクルードディレクトリの追加
include_directories(
    ${MOQT_ROOT}/include
    ${MOQT_ROOT}/include/quiche/common/platform/default
)

# 実行ファイルの作成
add_executable(moqt_test main.cpp)

# MOQTライブラリのリンク
if (WIN32)
    target_link_libraries(moqt_test ${MOQT_ROOT}/lib/moqt.lib)
else()
    target_link_libraries(moqt_test
        ${MOQT_ROOT}/lib/libmoqt.a
        pthread
        dl
    )
endif()

# C++20の機能を有効化
target_compile_features(moqt_test PRIVATE cxx_std_20)

if (APPLE)
    target_link_libraries(moqt_test "-framework CoreFoundation")
endif()
