# Frequently asked Questions

## Why is my channel stuck in the `CHANNELD_AWAITING_LOCKIN` state?

There are a couple of scenarios in which a channel may get stuck in the `CHANNELD_AWAITING_LOCKIN` state:

 - The funding transaction hasn't confirmed yet.
 - The peer may not be connected, in which case we wait for the `funding_locked` message from them.
 - The peer has forgotten about the channel, because it took too long to confirm.
 - The peer may be lagging behind the blockchain head, and simply not have seen the funding confirm.


## Why does my payment fail?

### Channel capacity insufficient

## I can't send a payment back (refund)

## What's a Short-Channel ID and how to read it?

A short-channel ID uniquely identifies a channel by the funding transaction's location in the blockchain.
Once the funding transaction confirms on the blockchain we can identify the output that funded the channel, i.e., the funds that are allocated to the channel, by the blockchain height, the position of the transaction in that block, and the position of the output in the transaction.
Those are also the the parts of the short-channel ID, separated by the character `x`.

For example the short-channel ID `569010x2756x1`points to block [569010][block-569010], in which we want the transaction at position [2756][scid-569010x2756], and in that transaciton we point to output [1][scid-569010x2756x1] (notice that all of these indices are 0-based).

In addition sometimes we may append a `/0` or `/1` to the short-channel ID to indicate the _direction_ in that channel.
The direction determines in which direction we are traversing a channel, and is given by lexicographically comparing the node IDs or the channel endpoints.
If we have two endpoints `A` and `B`, and `A` is smaller than `B` in lexicographic order, then `/0` means we traverse the channel from `A` to `B`, whereas `/1` means we traverse from `B` to `A`.

In the example above the endpoints have IDs `02459b759a62bc3ebfe98a320da237944cc4f35456384bd8fdefa7d0340c75f46f` and `03b31e5bbf2cdbe115b485a2b480e70a1ef3951a0dc6df4b1232e0e56f3dce18d6` so going from node `02459...` to `03b31e...` is direction `0`, while the direction from `02459...` to `03b31e...` is `1`.



[scid-569010]: https://blockstream.info/block/00000000000000000006220694c9428c212b06d33595b0e9dd8e698fafe379e5
[scid-569010x2756]:https://blockstream.info/tx/50441d0110c8f95e0d463a7665f7583356ea42f515c262525790152e03edf5f7
[scid-569010x2756x1]:https://blockstream.info/tx/50441d0110c8f95e0d463a7665f7583356ea42f515c262525790152e03edf5f7?output:1
