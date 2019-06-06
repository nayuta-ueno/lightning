#!/usr/bin/env python3

from lightning import Plugin
from hashlib import sha256
from binascii import hexlify, unhexlify

plugin = Plugin()


@plugin.hook("htlc_accepted")
def on_htlc_accepted(onion, htlc, plugin):
    print("Stepan", htlc, onion)

    ss = onion['shared_secret']
    print("Shared_secret", ss)
    preimage = sha256(unhexlify(ss)).hexdigest()

    print("Preimage", preimage)

    res = {"result": "resolve", "payment_key": preimage}
    print(res)
    return res


plugin.run()
