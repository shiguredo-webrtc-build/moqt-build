import argparse
import glob
import logging
import os
import shutil

from buildbase import (
    Platform,
    add_path,
    apply_patch,
    cd,
    cmake_path,
    cmd,
    cmdcap,
    get_macos_osver,
    get_windows_osver,
    git_clone_shallow,
    install_bazelisk,
    install_cmake,
    install_vswhere,
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

    # Bazelisk
    if platform.build.package_name == "windows_x86_64":
        bazelisk_platform = "windows-amd64"
    elif platform.build.package_name == "windows_arm64":
        bazelisk_platform = "windows-arm64"
    elif platform.build.package_name in ("macos_x86_64", "macos_arm64"):
        bazelisk_platform = "darwin"
    elif platform.build.package_name == "ubuntu-24.04_x86_64":
        bazelisk_platform = "linux-amd64"
    elif platform.build.package_name == "ubuntu-24.04_armv8":
        bazelisk_platform = "linux-arm64"
    else:
        raise Exception(f"Unsupported platform for bazelisk: {platform.build.package_name}")
    install_bazelisk(
        version=deps["BAZELISK_VERSION"],
        version_file=os.path.join(install_dir, "bazelisk.version"),
        install_dir=install_dir,
        platform=bazelisk_platform,
    )
    add_path(os.path.join(install_dir, "bazelisk"))

    # CMake
    install_cmake_args = {
        "version": deps["CMAKE_VERSION"],
        "version_file": os.path.join(install_dir, "cmake.version"),
        "source_dir": source_dir,
        "install_dir": install_dir,
        "platform": "",
        "ext": "tar.gz",
    }
    if platform.build.os == "windows" and platform.build.arch == "x86_64":
        install_cmake_args["platform"] = "windows-x86_64"
        install_cmake_args["ext"] = "zip"
    elif platform.build.os == "macos":
        install_cmake_args["platform"] = "macos-universal"
    elif platform.build.os == "ubuntu" and platform.build.arch == "x86_64":
        install_cmake_args["platform"] = "linux-x86_64"
    elif platform.build.os == "ubuntu" and platform.build.arch == "arm64":
        install_cmake_args["platform"] = "linux-aarch64"
    else:
        raise Exception("Failed to install CMake")
    install_cmake(**install_cmake_args)

    if platform.build.os == "macos":
        add_path(os.path.join(install_dir, "cmake", "CMake.app", "Contents", "bin"))
    else:
        add_path(os.path.join(install_dir, "cmake", "bin"))

    # VSWhere
    if platform.build.os == "windows":
        install_vswhere(
            version=deps["VSWHERE_VERSION"],
            version_file=os.path.join(install_dir, "vswhere.version"),
            install_dir=install_dir,
        )


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
        git_clone_shallow(
            url="https://quiche.googlesource.com/quiche",
            hash=deps["QUICHE_VERSION"],
            dir=quiche_source_dir,
        )
        apply_patch(os.path.join(BASE_DIR, "quiche.patch"), quiche_source_dir, 1)

    with cd(quiche_source_dir):
        bazel_args = []
        # Windows では .bazelrc を無視する
        if platform.build.package_name in ("windows_x86_64", "windows_arm64"):
            bazel_args += ["--noworkspace_rc"]
        bazel_args += ["build", "quiche:moqt"]
        if not debug:
            bazel_args += ["-c", "opt"]
        if platform.build.package_name in ("windows_x86_64", "windows_arm64"):
            # quiche が依存している protobuf や googleurl などのライブラリが MSVC に対応していないので
            # clang-cl を使うようにする
            #
            # https://bazel.build/configure/windows
            # に従って BAZEL_LLVM 環境変数を設定し、clang-cl 用の toolchain を指定する

            vswhere = os.path.join(install_dir, "vswhere", "vswhere.exe")
            msvc_path = cmdcap(
                [
                    vswhere,
                    "-latest",
                    "-products",
                    "*",
                    "-requires",
                    "Microsoft.VisualStudio.Component.VC.Llvm.Clang",
                    "-property",
                    "installationPath",
                ]
            )
            logging.info(f"MSVC Installed Path: {msvc_path}")
            os.environ["BAZEL_LLVM"] = os.path.join(msvc_path, "VC", "Tools", "Llvm", "x64")
            bazel_args += [
                "--extra_toolchains=@local_config_cc//:cc-toolchain-x64_windows-clang-cl",
                "--extra_execution_platforms=//:x64_windows-clang-cl",
                # quiche の .bazelrc で定義されているものと同等のオプションを指定する
                "--cxxopt=/std:c++20",
                "--host_cxxopt=/std:c++20",
                "--cxxopt=/GR-",
                "--host_cxxopt=/GR-",
                "--define=absl=1",
                # Linux 以外では system_icu を使わないようにする
                "--@com_google_googleurl//build_config:system_icu=0",
                # googleurl がちゃんと include してないせいで Windows のビルドが通らないので強制的に include する
                "--cxxopt=/FIstring",
                "--host_cxxopt=/FIstring",
                "--cxxopt=/FIostream",
                "--host_cxxopt=/FIostream",
                # X509_NAME とかのいらないマクロが定義されてビルドが通らないので、WIN32_LEAN_AND_MEAN で不要なヘッダーを除外する
                "--cxxopt=/DWIN32_LEAN_AND_MEAN",
                # wingdi.h の ERROR マクロのせいでビルドが通らないので NOGDI を定義して除外する
                "--cxxopt=/DNOGDI",
            ]

        cmd(["bazelisk", *bazel_args])


def _package(target: str, debug: bool):
    platform = _get_platform(target)
    configuration = "debug" if debug else "release"
    source_dir = os.path.join(BASE_DIR, "_source", platform.target.package_name, configuration)
    package_dir = os.path.join(BASE_DIR, "_package", platform.target.package_name, configuration)
    quiche_source_dir = os.path.join(source_dir, "quiche")
    with cd(quiche_source_dir):
        moqt_package_dir = os.path.join(package_dir, "moqt")
        # ライブラリのコピー
        libname = "moqt.lib" if platform.build.os == "windows" else "libmoqt.a"
        install_file(
            os.path.join(quiche_source_dir, "bazel-bin", "quiche", libname),
            os.path.join(moqt_package_dir, "lib", libname),
        )
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
        abseil_dirs = glob.glob(
            os.path.join(quiche_source_dir, "bazel-quiche", "external", "abseil-cpp*")
        )
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
        # NOTICE, LICENSE, DEPS, VERSION のコピー
        for filename in ("NOTICE", "LICENSE", "DEPS", "VERSION"):
            install_file(os.path.join(BASE_DIR, filename), os.path.join(moqt_package_dir, filename))


def _test(target: str, debug: bool):
    platform = _get_platform(target)
    configuration = "debug" if debug else "release"
    cmake_configuration = "Debug" if debug else "Release"
    source_dir = os.path.join(BASE_DIR, "_source", platform.target.package_name, configuration)
    build_dir = os.path.join(BASE_DIR, "_build", platform.target.package_name, configuration)
    install_dir = os.path.join(BASE_DIR, "_install", platform.target.package_name, configuration)
    package_dir = os.path.join(BASE_DIR, "_package", platform.target.package_name, configuration)

    install_deps(
        platform,
        source_dir,
        build_dir,
        install_dir,
        debug,
    )

    args = [
        f"-DCMAKE_BUILD_TYPE={cmake_configuration}",
        f"-DMOQT_ROOT={cmake_path(os.path.join(package_dir, 'moqt'))}",
    ]
    if platform.build.os == "windows":
        args += ["-T", "ClangCL"]
    cmd(
        [
            "cmake",
            "-B",
            os.path.join(build_dir, "test"),
            "-S",
            os.path.join(BASE_DIR, "test"),
            *args,
        ]
    )
    cmd(["cmake", "--build", os.path.join(build_dir, "test"), "--config", cmake_configuration])
    if platform.build.os == "windows":
        cmd([os.path.join(build_dir, "test", cmake_configuration, "moqt_test.exe")])
    else:
        cmd([os.path.join(build_dir, "test", "moqt_test")])


def _clean(target: str, debug: bool):
    platform = _get_platform(target)
    configuration = "debug" if debug else "release"
    source_dir = os.path.join(BASE_DIR, "_source", platform.target.package_name, configuration)
    build_dir = os.path.join(BASE_DIR, "_build", platform.target.package_name, configuration)
    install_dir = os.path.join(BASE_DIR, "_install", platform.target.package_name, configuration)
    package_dir = os.path.join(BASE_DIR, "_package", platform.target.package_name, configuration)
    add_path(os.path.join(install_dir, "bazelisk"))
    if os.path.exists(os.path.join(source_dir, "quiche")):
        with cd(os.path.join(source_dir, "quiche")):
            cmd(["bazelisk", "clean", "--expunge"], check=False)
    rm_rf(source_dir)
    rm_rf(build_dir)
    rm_rf(install_dir)
    rm_rf(package_dir)


def main():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(dest="command", help="利用可能なコマンド", required=True)
    bp = subparser.add_parser("build")
    bp.add_argument("target", choices=AVAILABLE_TARGETS)
    bp.add_argument("--debug", action="store_true")
    sp = subparser.add_parser("package")
    sp.add_argument("target", choices=AVAILABLE_TARGETS)
    sp.add_argument("--debug", action="store_true")
    tp = subparser.add_parser("test")
    tp.add_argument("target", choices=AVAILABLE_TARGETS)
    tp.add_argument("--debug", action="store_true")
    cp = subparser.add_parser("clean")
    cp.add_argument("target", choices=AVAILABLE_TARGETS)
    cp.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    if args.command == "build":
        _build(
            target=args.target,
            debug=args.debug,
        )
    elif args.command == "package":
        _package(
            target=args.target,
            debug=args.debug,
        )
    elif args.command == "test":
        _test(
            target=args.target,
            debug=args.debug,
        )
    elif args.command == "clean":
        _clean(
            target=args.target,
            debug=args.debug,
        )


if __name__ == "__main__":
    main()
