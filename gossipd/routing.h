#ifndef LIGHTNING_GOSSIPD_ROUTING_H
#define LIGHTNING_GOSSIPD_ROUTING_H
#include "config.h"
#include <bitcoin/pubkey.h>
#include <ccan/crypto/siphash24/siphash24.h>
#include <ccan/htable/htable_type.h>
#include <ccan/time/time.h>
#include <common/amount.h>
#include <common/node_id.h>
#include <gossipd/broadcast.h>
#include <gossipd/gossip_constants.h>
#include <gossipd/gossip_store.h>
#include <wire/gen_onion_wire.h>
#include <wire/wire.h>

struct half_chan {
	/* Cached `channel_update` which initialized below (or NULL) */
	const u8 *channel_update;

	/* millisatoshi. */
	u32 base_fee;
	/* millionths */
	u32 proportional_fee;

	/* Delay for HTLC in blocks.*/
	u32 delay;

	/* Timestamp and index into store file */
	struct broadcastable bcast;

	/* Flags as specified by the `channel_update`s, among other
	 * things indicated direction wrt the `channel_id` */
	u8 channel_flags;

	/* Flags as specified by the `channel_update`s, indicates
	 * optional fields.  */
	u8 message_flags;

	/* Minimum and maximum number of msatoshi in an HTLC */
	struct amount_msat htlc_minimum, htlc_maximum;
};

struct chan {
	struct short_channel_id scid;
	u8 *txout_script;

	/*
	 * half[0]->src == nodes[0] half[0]->dst == nodes[1]
	 * half[1]->src == nodes[1] half[1]->dst == nodes[0]
	 */
	struct half_chan half[2];
	/* node[0].id < node[1].id */
	struct node *nodes[2];

	/* NULL if not announced yet (ie. not public). */
	const u8 *channel_announce;

	/* Timestamp and index into store file */
	struct broadcastable bcast;

	/* Disabled locally (due to peer disconnect) */
	bool local_disabled;

	struct amount_sat sat;
};

/* A local channel can exist which isn't announcable. */
static inline bool is_chan_public(const struct chan *chan)
{
	return chan->channel_announce != NULL;
}

/* A channel is only announced once we have a channel_update to send
 * with it. */
static inline bool is_chan_announced(const struct chan *chan)
{
	return chan->bcast.index != 0;
}

static inline bool is_halfchan_defined(const struct half_chan *hc)
{
	return hc->channel_update != NULL;
}

static inline bool is_halfchan_enabled(const struct half_chan *hc)
{
	return is_halfchan_defined(hc) && !(hc->channel_flags & ROUTING_FLAGS_DISABLED);
}

/* Container for per-node channel pointers.  Better cache performance
* than uintmap, and we don't need ordering. */
static inline const struct short_channel_id *chan_map_scid(const struct chan *c)
{
	return &c->scid;
}

static inline size_t hash_scid(const struct short_channel_id *scid)
{
	/* scids cost money to generate, so simple hash works here */
	return (scid->u64 >> 32) ^ (scid->u64 >> 16) ^ scid->u64;
}

static inline bool chan_eq_scid(const struct chan *c,
				const struct short_channel_id *scid)
{
	return short_channel_id_eq(scid, &c->scid);
}
HTABLE_DEFINE_TYPE(struct chan, chan_map_scid, hash_scid, chan_eq_scid, chan_map);

#define NUM_IMMEDIATE_CHANS (sizeof(struct chan_map) / sizeof(struct chan *) - 1)

struct node {
	struct node_id id;

	/* Timestamp and index into store file */
	struct broadcastable bcast;

	/* IP/Hostname and port of this node (may be NULL) */
	struct wireaddr *addresses;

	/* Channels connecting us to other nodes */
	union {
		struct chan_map map;
		struct chan *arr[NUM_IMMEDIATE_CHANS+1];
	} chans;

	/* Temporary data for routefinding. */
	struct {
		/* Total to get to here from target. */
		struct amount_msat total;
		/* Total risk premium of this route. */
		struct amount_msat risk;
		/* Where that came from. */
		struct chan *prev;
	} bfg[ROUTING_MAX_HOPS+1];

	/* UTF-8 encoded alias, not zero terminated */
	u8 alias[32];

	/* Color to be used when displaying the name */
	u8 rgb_color[3];

	/* (Global) features */
	u8 *globalfeatures;

	/* Cached `node_announcement` we might forward to new peers (or NULL). */
	const u8 *node_announcement;
};

const struct node_id *node_map_keyof_node(const struct node *n);
size_t node_map_hash_key(const struct node_id *pc);
bool node_map_node_eq(const struct node *n, const struct node_id *pc);
HTABLE_DEFINE_TYPE(struct node, node_map_keyof_node, node_map_hash_key, node_map_node_eq, node_map);

struct pending_node_map;
struct pending_cannouncement;
struct unupdated_channel;

/* Fast versions: if you know n is one end of the channel */
static inline struct node *other_node(const struct node *n,
				      const struct chan *chan)
{
	int idx = (chan->nodes[1] == n);

	assert(chan->nodes[0] == n || chan->nodes[1] == n);
	return chan->nodes[!idx];
}

/* If you know n is one end of the channel, get connection src == n */
static inline struct half_chan *half_chan_from(const struct node *n,
					       struct chan *chan)
{
	int idx = (chan->nodes[1] == n);

	assert(chan->nodes[0] == n || chan->nodes[1] == n);
	return &chan->half[idx];
}

/* If you know n is one end of the channel, get index dst == n */
static inline int half_chan_to(const struct node *n, const struct chan *chan)
{
	int idx = (chan->nodes[1] == n);

	assert(chan->nodes[0] == n || chan->nodes[1] == n);
	return !idx;
}

struct routing_state {
	/* Which chain we're on */
	const struct chainparams *chainparams;

	/* All known nodes. */
	struct node_map *nodes;

	/* node_announcements which are waiting on pending_cannouncement */
	struct pending_node_map *pending_node_map;

	/* FIXME: Make this a htable! */
	/* channel_announcement which are pending short_channel_id lookup */
	struct list_head pending_cannouncement;

	/* Broadcast map, and access to gossip store */
	struct broadcast_state *broadcasts;

	/* Our own ID so we can identify local channels */
	struct node_id local_id;

	/* How old does a channel have to be before we prune it? */
	u32 prune_timeout;

        /* A map of channels indexed by short_channel_ids */
	UINTMAP(struct chan *) chanmap;

        /* A map of channel_announcements indexed by short_channel_ids:
	 * we haven't got a channel_update for these yet. */
	UINTMAP(struct unupdated_channel *) unupdated_chanmap;

	/* Has one of our own channels been announced? */
	bool local_channel_announced;

#if DEVELOPER
	/* Override local time for gossip messages */
	struct timeabs *gossip_time;

	/* Instead of ignoring unknown channels, pretend they're valid
	 * with this many satoshis (if non-zero) */
	struct amount_sat dev_unknown_channel_satoshis;
#endif
};

static inline struct chan *
get_channel(const struct routing_state *rstate,
	    const struct short_channel_id *scid)
{
	return uintmap_get(&rstate->chanmap, scid->u64);
}

struct route_hop {
	struct short_channel_id channel_id;
	int direction;
	struct node_id nodeid;
	struct amount_msat amount;
	u32 delay;
};

struct routing_state *new_routing_state(const tal_t *ctx,
					const struct chainparams *chainparams,
					const struct node_id *local_id,
					u32 prune_timeout,
					const u32 *dev_gossip_time,
					struct amount_sat dev_unknown_channel_satoshis);

/**
 * Add a new bidirectional channel from id1 to id2 with the given
 * short_channel_id and capacity to the local network view. The channel may not
 * already exist, and might create the node entries for the two endpoints, if
 * they do not exist yet.
 */
struct chan *new_chan(struct routing_state *rstate,
		      const struct short_channel_id *scid,
		      const struct node_id *id1,
		      const struct node_id *id2,
		      struct amount_sat sat);

/* Handlers for incoming messages */

/**
 * handle_channel_announcement -- Check channel announcement is valid
 *
 * Returns error message if we should fail channel.  Make *scid non-NULL
 * (for checking) if we extracted a short_channel_id, otherwise ignore.
 */
u8 *handle_channel_announcement(struct routing_state *rstate,
				const u8 *announce TAKES,
				const struct short_channel_id **scid);

/**
 * handle_pending_cannouncement -- handle channel_announce once we've
 * completed short_channel_id lookup.
 */
void handle_pending_cannouncement(struct routing_state *rstate,
				  const struct short_channel_id *scid,
				  const struct amount_sat sat,
				  const u8 *txscript);

/* Iterate through channels in a node */
struct chan *first_chan(const struct node *node, struct chan_map_iter *i);
struct chan *next_chan(const struct node *node, struct chan_map_iter *i);

/* Returns NULL if all OK, otherwise an error for the peer which sent. */
u8 *handle_channel_update(struct routing_state *rstate, const u8 *update TAKES,
			  const char *source);

/* Returns NULL if all OK, otherwise an error for the peer which sent. */
u8 *handle_node_announcement(struct routing_state *rstate, const u8 *node);

/* Get a node: use this instead of node_map_get() */
struct node *get_node(struct routing_state *rstate,
		      const struct node_id *id);

/* Compute a route to a destination, for a given amount and riskfactor. */
struct route_hop *get_route(const tal_t *ctx, struct routing_state *rstate,
			    const struct node_id *source,
			    const struct node_id *destination,
			    const struct amount_msat msat, double riskfactor,
			    u32 final_cltv,
			    double fuzz,
			    u64 seed,
			    const struct short_channel_id_dir *excluded,
			    size_t max_hops);
/* Disable channel(s) based on the given routing failure. */
void routing_failure(struct routing_state *rstate,
		     const struct node_id *erring_node,
		     const struct short_channel_id *erring_channel,
		     int erring_direction,
		     enum onion_type failcode,
		     const u8 *channel_update);

void route_prune(struct routing_state *rstate);

/**
 * Add a channel_announcement to the network view without checking it
 *
 * Directly add the channel to the local network, without checking it first. Use
 * this only for messages from trusted sources. Untrusted sources should use the
 * @see{handle_channel_announcement} entrypoint to check before adding.
 *
 * index is usually 0, in which case it's set by insert_broadcast adding it
 * to the store.
 */
bool routing_add_channel_announcement(struct routing_state *rstate,
				      const u8 *msg TAKES,
				      struct amount_sat sat,
				      u32 index);

/**
 * Add a channel_update without checking for errors
 *
 * Used to actually insert the information in the channel update into the local
 * network view. Only use this for messages that are known to be good. For
 * untrusted source, requiring verification please use
 * @see{handle_channel_update}
 */
bool routing_add_channel_update(struct routing_state *rstate,
				const u8 *update TAKES,
				u32 index);

/**
 * Add a node_announcement to the network view without checking it
 *
 * Directly add the node being announced to the network view, without verifying
 * it. This must be from a trusted source, e.g., gossip_store. For untrusted
 * sources (peers) please use @see{handle_node_announcement}.
 */
bool routing_add_node_announcement(struct routing_state *rstate,
				   const u8 *msg TAKES,
				   u32 index);


/**
 * Add a local channel.
 *
 * Entrypoint to add a local channel that was not learned through gossip. This
 * is the case for private channels or channels that have not yet reached
 * `announce_depth`.
 */
bool handle_local_add_channel(struct routing_state *rstate, const u8 *msg);

#if DEVELOPER
void memleak_remove_routing_tables(struct htable *memtable,
				   const struct routing_state *rstate);
#endif

/**
 * Get the local time.
 *
 * This gets overridden in dev mode so we can use canned (stale) gossip.
 */
struct timeabs gossip_time_now(const struct routing_state *rstate);

#endif /* LIGHTNING_GOSSIPD_ROUTING_H */
