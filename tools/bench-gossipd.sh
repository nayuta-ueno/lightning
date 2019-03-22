#! /bin/sh
# Needs bitcoind -regtest running.

set -e

DIR=""
TARGETS=""
DEFAULT_TARGETS=" store_load_msec vsz_kb store_rewrite_sec listnodes_sec listchannels_sec routing_sec peer_write_all_sec peer_read_all_sec "

wait_for_start()
{
    i=0
    ID=""
    while [ -z "$ID" ]; do
	ID="$($LCLI1 -H getinfo 2>/dev/null | grep '^id=' | cut -d= -f2)"
	sleep 1
	i=$((i + 1))
	if [ $i = 10 ]; then
	    echo "lightningd didn't start?" >&2
	    cat "$DIR"/log
	    exit 1
	fi
    done
    echo "$ID"
}

for arg; do
    case "$arg" in
	--dir=*)
	    DIR="${arg#*=}"
	    ;;
	--help)
	    echo "Usage: tools/bench-gossipd.sh [--dir=<directory>] [TARGETS]"
	    echo "Default targets:$DEFAULT_TARGETS"
	    exit 0
	    ;;
	-*)
	    echo "Unknown arg $arg" >&2
	    exit 1
	    ;;
	*)
	    TARGETS="$TARGETS $arg"
	    ;;
    esac
done

# Targets must be space-separated for ## trick.
if [ -z "$TARGETS" ]; then
    TARGETS="$DEFAULT_TARGETS"
else
    TARGETS="$TARGETS "
fi

if ! bitcoin-cli -regtest ping >/dev/null 2>&1; then
    bitcoind -regtest > "$DIR"/bitcoind.log &

    while ! bitcoin-cli -regtest ping >/dev/null 2>&1; do sleep 1; done
fi

LIGHTNINGD="./lightningd/lightningd --network=regtest --dev-gossip-time=1550513768 --dev-unknown-channel-satoshis=100000"
LCLI1="./cli/lightning-cli --lightning-dir=$DIR"

if [ -z "$DIR" ]; then
    trap 'rm -rf "$DIR"' 0

    DIR="$(mktemp -d)"
    xzcat ../million-channels-project/data/1M/gossip/xa* | ./devtools/create-gossipstore 100000 > "$DIR"/gossip_store
fi

# shellcheck disable=SC2086
echo $TARGETS | tr ' ' ,

# First, measure load time.
rm -f "$DIR"/log "$DIR"/peer
$LIGHTNINGD --lightning-dir="$DIR" --log-file="$DIR"/log --bind-addr="$DIR"/peer &

rm -f "$DIR"/stats
ID=$(wait_for_start)

while ! grep -q 'gossipd.*: total store load time' "$DIR"/log 2>/dev/null; do
    sleep 1
done
if [ -z "${TARGETS##* store_load_msec *}" ]; then
    grep 'gossipd.*: total store load time' "$DIR"/log | cut -d\  -f7 >> $DIR/stats
fi

# How big is gossipd?
if [ -z "${TARGETS##* vsz_kb *}" ]; then
    ps -o vsz= -p "$(pidof lightning_gossipd)" >> $DIR/stats
fi

# How long does rewriting the store take?
if [ -z "${TARGETS##* store_rewrite_sec *}" ]; then
    /usr/bin/time -o "$DIR"/stats --append -f %e $LCLI1 dev-compact-gossip-store > /dev/null
fi

# Now, how long does listnodes take?
if [ -z "${TARGETS##* listnodes_sec *}" ]; then
    # shellcheck disable=SC2086
    /usr/bin/time -o "$DIR"/stats --append -f %e $LCLI1 listnodes > "$DIR"/listnodes.json
fi

# Now, how long does listchannels take?
if [ -z "${TARGETS##* listchannels_sec *}" ]; then
    # shellcheck disable=SC2086
    /usr/bin/time -o "$DIR"/stats --append -f %e $LCLI1 listchannels > "$DIR"/listchannels.json
fi

# Now, try routing between first and last points.
if [ -z "${TARGETS##* routing_sec *}" ]; then
    echo "$DIV" | tr -d \\n; DIV=","
    # shellcheck disable=SC2046
    # shellcheck disable=SC2005
    echo $(tr '{}' '\n' < "$DIR"/listnodes.json | grep nodeid | cut -d'"' -f4 | sort | head -n2) | while read -r from to; do
	# shellcheck disable=SC2086
	/usr/bin/time --quiet -o "$DIR"/stats --append -f %e $LCLI1 getroute 2>&1 $from 1 1 6 $to > /dev/null || true # FIXME: this shouldn't fail
    done
fi

# Try getting all from the peer.
if [ -z "${TARGETS##* peer_write_all_sec *}" ]; then
    ENTRIES=$(sed -n 's/.*gossipd.*: total store load time: [0-9]* msec (\([0-9]*\) entries, [0-9]* bytes)/\1/p' < "$DIR"/log)

    /usr/bin/time --quiet -o "$DIR"/stats --append -f %e devtools/gossipwith --initial-sync --max-messages=$((ENTRIES - 5)) "$ID"@"$DIR"/peer > /dev/null
fi

if [ -z "${TARGETS##* peer_read_all_sec *}" ]; then
    # shellcheck disable=SC2086
    $LCLI1 stop > /dev/null
    sleep 5
    # In case they specified dir, don't blow away store.
    mv "$DIR"/gossip_store "$DIR"/gossip_store.bak
    rm -f "$DIR"/peer

    $LIGHTNINGD --lightning-dir="$DIR" --log-file="$DIR"/log --bind-addr="$DIR"/peer --log-level=debug &
    ID=$(wait_for_start)

    # FIXME: Measure this better.
    EXPECTED=$(find "$DIR"/gossip_store.bak -printf %s)

    START_TIME=`date +%s`
    # We send a bad msg at the end, so lightningd hangs up
    xzcat ../million-channels-project/data/1M/gossip/xa*.xz | devtools/gossipwith --max-messages=1 --stdin "$ID"@"$DIR"/peer 0011 > /dev/null

    while [ "$(find "$DIR"/gossip_store -printf %s)" -lt "$EXPECTED" ]; do
	sleep 1
	i=$((i + 1))
    done
    END_TIME=`date +%s`

    echo $((END_TIME - START_TIME)) >> "$DIR"/stats
    mv "$DIR"/gossip_store.bak "$DIR"/gossip_store
fi

# CSV format
tr '\n' ',' < "$DIR"/stats | sed 's/,$//'; echo

# shellcheck disable=SC2086
$LCLI1 stop > /dev/null