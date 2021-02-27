#!/bin/bash

set -ex

INSTALL=$(readlink -f $(dirname $0))
SRC=$INSTALL/src
TOOLCHAIN=$1
BUILD=${2:-$SRC/master-build}

if [[ -n $TOOLCHAIN ]]; then
    TOOLCHAIN_ROOT="-DTOOLCHAIN_ROOT=$TOOLCHAIN"
fi

mkdir -p $BUILD
cd $BUILD
cmake -DCMAKE_INSTALL_PREFIX=$INSTALL $TOOLCHAIN_ROOT $SRC
make all-host-python-master
