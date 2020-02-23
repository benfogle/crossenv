##############################################################################
# This is a gross abuse of CMake to download and build artifacts that we will
# use for testing. It's in CMake because plain Makefiles were getting pretty
# nasty, and CMake's ExternalProject fits what we want to do fairly well.
#
# This code isn't terribly well organized, and there's plenty of copy-paste:
# it's really just a record of how the build artifacts were generated, and we
# use git-lfs so that we don't have to rebuild them.
#
# We're also not really making much attempt to be portable: This runs on Linux
# only.
##############################################################################

cmake_minimum_required(VERSION 3.6)
project(crossenv-artifacts NONE)
include(ExternalProject)


##############################################################################
# MUSL-gcc toolchains
#
# Doesn't seem to play nice with out-of-source builds, so we'll do it in
# source. Multiple make invokations to avoid redownloading everything for
# each architecture.
#
# A few customizations are stored in musl-cross-make.mk, and we will also
# adjust the dynamic loader's symlink to be a relative path. This way we
# can run it with qemu.
##############################################################################

set(MUSL_TOOLCHAIN      ${CMAKE_INSTALL_PREFIX}/musl-toolchain)
set(MUSL_TOOLCHAIN_BIN  ${MUSL_TOOLCHAIN}/bin)
ExternalProject_Add(musl-toolchain
    GIT_REPOSITORY      https://github.com/richfelker/musl-cross-make.git
    GIT_TAG             v0.9.8
    GIT_SHALLOW         TRUE
    BUILD_IN_SOURCE     TRUE
    INSTALL_DIR         ${MUSL_TOOLCHAIN}
    PATCH_COMMAND       cp ${CMAKE_CURRENT_SOURCE_DIR}/musl-cross-make.mk
                            <SOURCE_DIR>/config.mak
    CONFIGURE_COMMAND   ""
    BUILD_COMMAND       make -j8 install
                            OUTPUT=<INSTALL_DIR>
                            TARGET=aarch64-linux-musl
    COMMAND             ln -sf libc.so <INSTALL_DIR>/aarch64-linux-musl/lib/ld-musl-aarch64.so.1
    COMMAND             make -j8 install
                            OUTPUT=<INSTALL_DIR>
                            TARGET=arm-linux-musleabihf
                            install
    COMMAND             ln -sf libc.so <INSTALL_DIR>/arm-linux-musleabihf/lib/ld-musl-armhf.so.1
    INSTALL_COMMAND     ""
)


##############################################################################
# Add some things to the musl toolchain sysroot.
#
# The separate zlib-source is a trick we'll use to avoid downloading the
# project multiple times. A blank DOWNLOAD_COMMAND and the correct DEPENDS
# entry in the later zlib-* targets lets us get around CMake's restriction
# against a nonexistant SOURCE_DIR.
##############################################################################

ExternalProject_Add(zlib-source
    URL                 https://www.zlib.net/zlib-1.2.11.tar.gz
    URL_HASH            SHA256=c3e5e9fdd5004dcb542feda5ee4f0ff0744628baf8ed2dd5d66f8ca1197cb1a1
    SOURCE_DIR          zlib-source
    CONFIGURE_COMMAND   ""
    BUILD_COMMAND       ""
    INSTALL_COMMAND     ""
)


ExternalProject_Add(zlib-arm
    SOURCE_DIR          zlib-source
    INSTALL_DIR         ${MUSL_TOOLCHAIN}/arm-linux-musleabihf/usr
    DOWNLOAD_COMMAND    ""
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                            CHOST=arm-linux-musleabihf
                            CFLAGS=-fPIC
                        <SOURCE_DIR>/configure
                            --prefix=<INSTALL_DIR>
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make -j8
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make install
    DEPENDS             musl-toolchain
                        zlib-source
)


ExternalProject_Add(zlib-aarch64
    SOURCE_DIR          zlib-source
    INSTALL_DIR         ${MUSL_TOOLCHAIN}/aarch64-linux-musl/usr
    DOWNLOAD_COMMAND    ""
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                            CHOST=aarch64-linux-musl
                            CFLAGS=-fPIC
                        <SOURCE_DIR>/configure
                            --prefix=<INSTALL_DIR>
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make -j8
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make install
    DEPENDS             musl-toolchain
                        zlib-source
)


# For libuuid
ExternalProject_Add(util-linux-source
    URL                 https://mirrors.edge.kernel.org/pub/linux/utils/util-linux/v2.35/util-linux-2.35.1.tar.xz
    SOURCE_DIR          util-linux-source
    CONFIGURE_COMMAND   ""
    BUILD_COMMAND       ""
    INSTALL_COMMAND     ""
)


ExternalProject_Add(util-linux-aarch64
    SOURCE_DIR          util-linux-source
    INSTALL_DIR         ${MUSL_TOOLCHAIN}/aarch64-linux-musl/usr
    DOWNLOAD_COMMAND    ""
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        <SOURCE_DIR>/configure
                            --host=aarch64-linux-musl
                            --build=x86_64-linux-gnu
                            --prefix=<INSTALL_DIR>
                            --disable-all-programs
                            --disable-bash-completion
                            --enable-libuuid
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make -j8
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make install
    DEPENDS             musl-toolchain
                        util-linux-source
)


ExternalProject_Add(util-linux-arm
    SOURCE_DIR          util-linux-source
    INSTALL_DIR         ${MUSL_TOOLCHAIN}/arm-linux-musleabihf/usr
    DOWNLOAD_COMMAND    ""
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        <SOURCE_DIR>/configure
                            --host=arm-linux-musleabihf
                            --build=x86_64-linux-gnu
                            --prefix=<INSTALL_DIR>
                            --disable-all-programs
                            --disable-bash-completion
                            --enable-libuuid
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make -j8
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make install
    DEPENDS             musl-toolchain
                        util-linux-source
)


# for ssl
ExternalProject_Add(openssl-source
    URL                 https://www.openssl.org/source/openssl-1.1.1d.tar.gz
    URL_HASH            SHA256=1e3a91bc1f9dfce01af26026f856e064eab4c8ee0a8f457b5ae30b40b8b711f2
    SOURCE_DIR          openssl-source
    CONFIGURE_COMMAND   ""
    BUILD_COMMAND       ""
    INSTALL_COMMAND     ""
)


ExternalProject_Add(openssl-arm
    SOURCE_DIR          openssl-source
    INSTALL_DIR         ${MUSL_TOOLCHAIN}/arm-linux-musleabihf/usr
    DOWNLOAD_COMMAND    ""
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        <SOURCE_DIR>/Configure
                            shared
                            zlib-dynamic
                            --prefix=<INSTALL_DIR>
                            linux-armv4
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make -j8 CROSS_COMPILE=arm-linux-musleabihf-
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make install_sw install_ssldirs
    DEPENDS             musl-toolchain
                        openssl-source
                        zlib-arm
)


ExternalProject_Add(openssl-aarch64
    SOURCE_DIR          openssl-source
    INSTALL_DIR         ${MUSL_TOOLCHAIN}/aarch64-linux-musl/usr
    DOWNLOAD_COMMAND    ""
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        <SOURCE_DIR>/Configure
                            shared
                            zlib-dynamic
                            --prefix=<INSTALL_DIR>
                            linux-aarch64
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make -j8 CROSS_COMPILE=aarch64-linux-musl-
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make install_sw install_ssldirs
    DEPENDS             musl-toolchain
                        openssl-source
                        zlib-aarch64
)


# for ctypes
ExternalProject_Add(libffi-src
    URL                 https://github.com/libffi/libffi/releases/download/v3.3/libffi-3.3.tar.gz
    SOURCE_DIR          libffi-src
    CONFIGURE_COMMAND   ""
    BUILD_COMMAND       ""
    INSTALL_COMMAND     ""
)


ExternalProject_Add(libffi-aarch64
    SOURCE_DIR          libffi-src
    INSTALL_DIR         ${MUSL_TOOLCHAIN}/aarch64-linux-musl/usr
    DOWNLOAD_COMMAND    ""
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        <SOURCE_DIR>/configure
                            --host=aarch64-linux-musl
                            --build=x86_64-linux-gnu
                            --prefix=<INSTALL_DIR>
                            --disable-static
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make -j8
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make install
    DEPENDS             musl-toolchain
                        libffi-src
)


ExternalProject_Add(libffi-arm
    SOURCE_DIR          libffi-src
    INSTALL_DIR         ${MUSL_TOOLCHAIN}/arm-linux-musleabihf/usr
    DOWNLOAD_COMMAND    ""
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        <SOURCE_DIR>/configure
                            --host=arm-linux-musleabihf
                            --build=x86_64-linux-gnu
                            --prefix=<INSTALL_DIR>
                            --disable-static
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make -j8
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env
                            PATH=${MUSL_TOOLCHAIN_BIN}:$ENV{PATH}
                        make install
    DEPENDS             musl-toolchain
                        libffi-src
)



#############################################################################
# A target to group all the prereq stuff together
#############################################################################
add_custom_target(prereqs
    DEPENDS     openssl-aarch64
                openssl-arm
                zlib-aarch64
                zlib-arm
                util-linux-aarch64
                util-linux-arm
                libffi-aarch64
                libffi-arm
                musl-toolchain
)


##############################################################################
# Python! Finally!
#
# We're using the same download/source trick, but grouping the download step
# as part of build-python
##############################################################################

ExternalProject_Add(build-python-3.8.1
    INSTALL_DIR         ${CMAKE_INSTALL_PREFIX}/python/3.8.1/build
    DOWNLOAD_DIR        python-download
    SOURCE_DIR          python-source-3.8.1
    URL                 https://www.python.org/ftp/python/3.8.1/Python-3.8.1.tar.xz
    URL_HASH            MD5=b3fb85fd479c0bf950c626ef80cacb57
    CONFIGURE_COMMAND   <SOURCE_DIR>/configure
                            --prefix=<INSTALL_DIR>
    BUILD_COMMAND       make -j8
    INSTALL_COMMAND     make install
)
ExternalProject_Get_Property(build-python-3.8.1 INSTALL_DIR)
set(BUILD_PYTHON_BIN ${INSTALL_DIR}/bin)
set(BUILD_PYTHON_LIB ${INSTALL_DIR}/lib)
set(BUILD_PYTHON_PATH ${MUSL_TOOLCHAIN_BIN}:${BUILD_PYTHON_BIN}:$ENV{PATH})


# set rpath to run from install directory. Prevents a mess of LD_LIBRARY_PATH when
# we're running under emulation.
set(rpaths
    -Wl,-rpath='\$\${ORIGIN}/../../../../musl-toolchain/aarch64-linux-musl/lib'
    -Wl,-rpath='\$\${ORIGIN}/../../../../musl-toolchain/aarch64-linux-musl/usr/lib'
    -Wl,-rpath='\$\${ORIGIN}/../lib'
)
string(REPLACE ";" " " rpaths "${rpaths}") # join ;-list with " "


ExternalProject_Add(host-python-3.8.1-aarch64
    INSTALL_DIR         ${CMAKE_INSTALL_PREFIX}/python/3.8.1/aarch64
    DOWNLOAD_COMMAND    ""
    SOURCE_DIR          python-source-3.8.1
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env PATH=${BUILD_PYTHON_PATH}
                        <SOURCE_DIR>/configure
                            --prefix=<INSTALL_DIR>
                            --enable-shared
                            --host=aarch64-linux-musl
                            --build=x86_64-linux-gnu
                            --without-ensurepip
                            ac_cv_buggy_getaddrinfo=no
                            ac_cv_file__dev_ptmx=yes
                            ac_cv_file__dev_ptc=no
                            CFLAGS=--sysroot=${MUSL_TOOLCHAIN}/aarch64-linux-musl
                            "LDFLAGS=--sysroot=${MUSL_TOOLCHAIN}/aarch64-linux-musl ${rpaths}"
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env PATH=${BUILD_PYTHON_PATH}
                        make -j8
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env PATH=${BUILD_PYTHON_PATH}
                        make install
    DEPENDS             prereqs
                        build-python-3.8.1
)


# set rpath to run from install directory. Prevents a mess of LD_LIBRARY_PATH when
# we're running under emulation.
set(rpaths
    -Wl,-rpath='\$\${ORIGIN}/../../../../musl-toolchain/arm-linux-musleabi/lib'
    -Wl,-rpath='\$\${ORIGIN}/../../../../musl-toolchain/arm-linux-musleabi/usr/lib'
    -Wl,-rpath='\$\${ORIGIN}/../lib'
)
string(REPLACE ";" " " rpaths "${rpaths}") # join ;-list with " "

ExternalProject_Add(host-python-3.8.1-armhf
    INSTALL_DIR         ${CMAKE_INSTALL_PREFIX}/python/3.8.1/armhf
    DOWNLOAD_COMMAND    ""
    SOURCE_DIR          python-source-3.8.1
    CONFIGURE_COMMAND   ${CMAKE_COMMAND} -E env PATH=${BUILD_PYTHON_PATH}
                        <SOURCE_DIR>/configure
                            --prefix=<INSTALL_DIR>
                            --enable-shared
                            --host=arm-linux-musleabihf
                            --build=x86_64-linux-gnu
                            --without-ensurepip
                            ac_cv_buggy_getaddrinfo=no
                            ac_cv_file__dev_ptmx=yes
                            ac_cv_file__dev_ptc=no
                            CFLAGS=--sysroot=${MUSL_TOOLCHAIN}/arm-linux-musleabihf
                            "LDFLAGS=--sysroot=${MUSL_TOOLCHAIN}/arm-linux-musleabihf ${rpaths}"
    BUILD_COMMAND       ${CMAKE_COMMAND} -E env PATH=${BUILD_PYTHON_PATH}
                        make -j8
    INSTALL_COMMAND     ${CMAKE_COMMAND} -E env PATH=${BUILD_PYTHON_PATH}
                        make install
    DEPENDS             prereqs
                        build-python-3.8.1
)
