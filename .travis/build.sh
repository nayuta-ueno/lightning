#!/bin/bash

mkdir -p dependencies/bin || true
PATH=dependencies/bin:$PATH

# Download bitcoind and bitcoin-cli 
if [ ! -f dependencies/bin/bitcoind ]; then
    wget https://bitcoin.org/bin/bitcoin-core-0.17.1/bitcoin-0.17.1-x86_64-linux-gnu.tar.gz
    tar -xzf bitcoin-0.17.1-x86_64-linux-gnu.tar.gz
    mv bitcoin-0.17.1/bin/* dependencies/bin
    rm -rf bitcoin-0.17.1-x86_64-linux-gnu.tar.gz bitcoin-0.17.1
fi

export SLOW_MACHINE=1
export CC="ccache $COMPILER"
./configure
make -j3
make check
make check-source
git clone https://github.com/lightningnetwork/lightning-rfc.git
make check-source BOLTDIR=lightning-rfc
