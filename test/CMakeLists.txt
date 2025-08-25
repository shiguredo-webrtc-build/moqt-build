cmake_minimum_required(VERSION 3.16)
project(moqt_test)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# MOQTパッケージのパス
set(MOQT_ROOT "${CMAKE_SOURCE_DIR}/../_package/ubuntu-24.04_x86_64/release/moqt")

# インクルードディレクトリの追加
include_directories(
    ${MOQT_ROOT}/include
    ${MOQT_ROOT}/include/quiche/common/platform/default
)

# 実行ファイルの作成
add_executable(moqt_test main.cpp)

# MOQTライブラリのリンク
target_link_libraries(moqt_test 
    ${MOQT_ROOT}/lib/libmoqt.a
    pthread
    dl
)

# C++20の機能を有効化
target_compile_features(moqt_test PRIVATE cxx_std_20)
