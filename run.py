import argparse
import glob
import hashlib
import json
import logging
import multiprocessing
import os
import shutil
import tarfile
import zipfile
from typing import Dict, List, Optional

from buildbase import (
    Platform,
    WebrtcInfo,
    add_path,
    add_webrtc_build_arguments,
    build_and_install_boost,
    build_webrtc,
    cd,
    cmake_path,
    cmd,
    cmdcap,
    enum_all_files,
    fix_clang_version,
    get_clang_version,
    get_macos_osver,
    get_webrtc_info,
    get_webrtc_platform,
    get_windows_osver,
    git_clone_shallow,
    install_amf,
    install_android_ndk,
    install_android_sdk_cmdline_tools,
    install_blend2d_official,
    install_catch2,
    install_cmake,
    install_cuda_windows,
    install_llvm,
    install_openh264,
    install_rootfs,
    install_vpl,
    install_webrtc,
    install_bazelisk,
    mkdir_p,
    read_version_file,
    rm_rf,
)

logging.basicConfig(level=logging.DEBUG)


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def install_file(src: str, dst: str):
    """
    src から dst へディレクトリまたはファイルをコピーする

    1. dst が存在していたら（ファイルでもディレクトリでも）削除する
    2. dst の親ディレクトリが存在しなかったら作成する
    3. src を dst にコピーする
    """
    # 1. dst が存在していたら削除する
    if os.path.exists(dst):
        if os.path.isdir(dst):
            logging.debug(f"Remove dir: {dst}")
            shutil.rmtree(dst)
        else:
            logging.debug(f"Remove file: {dst}")
            os.remove(dst)

    # 2. dst の親ディレクトリが存在しなかったら作成する
    dst_parent = os.path.dirname(dst)
    if dst_parent and not os.path.exists(dst_parent):
        logging.debug(f"Make dir: {dst_parent}")
        os.makedirs(dst_parent)

    # 3. src を dst にコピーする
    if os.path.isdir(src):
        logging.info(f"Copy dir: {src} -> {dst}")
        shutil.copytree(src, dst)
    else:
        logging.info(f"Copy file: {src} -> {dst}")
        shutil.copy2(src, dst)


def install_deps(
    platform: Platform,
    source_dir: str,
    build_dir: str,
    install_dir: str,
    debug: bool,
):
    with cd(BASE_DIR):
        deps = read_version_file("DEPS")

    install_bazelisk(version=deps["BAZELISK_VERSION"], version_file=os.path.join(install_dir, "bazelisk.version"), install_dir=install_dir, platform="linux-amd64")
    add_path(os.path.join(install_dir, "bazelisk"))


def rsync(src_dir, dst_dir, includes: list[str], build_target):
    rm_rf(dst_dir)
    if build_target in ("windows_x86_64", "windows_arm64"):
        # robocopy の戻り値は特殊なので、check=False にしてうまくエラーハンドリングする
        # https://docs.microsoft.com/ja-jp/troubleshoot/windows-server/backup-and-storage/return-codes-used-robocopy-utility
        r = cmd(
            [
                "robocopy",
                src_dir,
                dst_dir,
                *includes,
                "/S",
                "/NP",
                "/NFL",
                "/NDL",
            ],
            check=False,
        )
        if r.returncode >= 4:
            raise Exception("robocopy failed")
    else:
        mkdir_p(dst_dir)
        cmd(
            [
                "rsync",
                "-amv",
                "--include=*/",
                *[f"--include={pattern}" for pattern in includes],
                "--exclude=*",
                os.path.join(src_dir, "."),
                os.path.join(dst_dir, "."),
            ]
        )


AVAILABLE_TARGETS = [
    "windows_x86_64",
    "macos_x86_64",
    "macos_arm64",
    "ubuntu-24.04_x86_64",
    "ubuntu-24.04_armv8",
    "ios",
    "android",
]


def _get_platform(target: str) -> Platform:
    if target == "windows_x86_64":
        platform = Platform("windows", get_windows_osver(), "x86_64")
    elif target == "macos_x86_64":
        platform = Platform("macos", get_macos_osver(), "x86_64")
    elif target == "macos_arm64":
        platform = Platform("macos", get_macos_osver(), "arm64")
    elif target == "ubuntu-24.04_x86_64":
        platform = Platform("ubuntu", "24.04", "x86_64")
    elif target == "ubuntu-24.04_armv8":
        platform = Platform("ubuntu", "24.04", "armv8")
    elif target == "ios":
        platform = Platform("ios", None, None)
    elif target == "android":
        platform = Platform("android", None, None)
    else:
        raise Exception(f"Unknown target {target}")
    return platform


def _build(
    target: str,
    debug: bool,
):
    platform = _get_platform(target)

    logging.info(f"Build platform: {platform.build.package_name}")
    logging.info(f"Target platform: {platform.target.package_name}")

    configuration = "debug" if debug else "release"
    source_dir = os.path.join(BASE_DIR, "_source", platform.target.package_name, configuration)
    build_dir = os.path.join(BASE_DIR, "_build", platform.target.package_name, configuration)
    install_dir = os.path.join(BASE_DIR, "_install", platform.target.package_name, configuration)
    mkdir_p(source_dir)
    mkdir_p(build_dir)
    mkdir_p(install_dir)

    install_deps(
        platform,
        source_dir,
        build_dir,
        install_dir,
        debug,
    )

    with cd(BASE_DIR):
        deps = read_version_file("DEPS")

    quiche_source_dir = os.path.join(source_dir, "quiche")
    if not os.path.exists(quiche_source_dir):
        logging.info("Cloning quiche...")
        git_clone_shallow(url="https://quiche.googlesource.com/quiche", hash=deps["QUICHE_VERSION"], dir=quiche_source_dir)

    with cd(quiche_source_dir):
        if not debug:
            bazel_args = ["-c", "opt"]
        cmd(["bazelisk", "build", "quiche:moqt", *bazel_args])


def _package(target: str, debug: bool):
    platform = _get_platform(target)
    configuration = "debug" if debug else "release"
    source_dir = os.path.join(BASE_DIR, "_source", platform.target.package_name, configuration)
    package_dir = os.path.join(BASE_DIR, "_package", platform.target.package_name, configuration)
    quiche_source_dir = os.path.join(source_dir, "quiche")
    with cd(quiche_source_dir):
        moqt_package_dir = os.path.join(package_dir, "moqt")
        # ライブラリのコピー
        install_file(os.path.join(quiche_source_dir, "bazel-bin", "quiche", "libmoqt.a"), os.path.join(moqt_package_dir, "lib", "libmoqt.a"))
        # quiche のヘッダのコピー
        rsync(
            src_dir=os.path.join(quiche_source_dir, "quiche"),
            dst_dir=os.path.join(moqt_package_dir, "include", "quiche"),
            includes=[
                "*.h",
            ],
            build_target=platform.build.package_name,
        )
        # abseil のヘッダのコピー
        abseil_dirs = glob.glob(os.path.join(quiche_source_dir, "bazel-quiche", "external", "abseil-cpp*"))
        if len(abseil_dirs) != 1:
            raise Exception("abseil-cpp not found")
        abseil_dir = abseil_dirs[0]
        rsync(
            src_dir=os.path.join(abseil_dir, "absl"),
            dst_dir=os.path.join(moqt_package_dir, "include", "absl"),
            includes=[
                "*.h",
                "*.inc",
            ],
            build_target=platform.build.package_name,
        )


def main():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(dest="command",  help="利用可能なコマンド", required=True)
    bp = subparser.add_parser("build")
    bp.add_argument("target", choices=AVAILABLE_TARGETS)
    bp.add_argument("--debug", action="store_true")
    sp = subparser.add_parser("package")
    sp.add_argument("target", choices=AVAILABLE_TARGETS)
    sp.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    if args.command == "build":
        _build(
            target=args.target,
            debug=args.debug,
        )
    if args.command == "package":
        _package(
            target=args.target,
            debug=args.debug,
        )


if __name__ == "__main__":
    main()
