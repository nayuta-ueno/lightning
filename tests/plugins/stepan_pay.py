#!/usr/bin/env python3

from lightning import Plugin
from hashlib import sha256
from binascii import hexlify, unhexlify

plugin = Plugin()


@plugin.hook("htlc_accepted")
def on_htlc_accepted(onion, htlc, plugin):
    ss = onion['shared_secret']
    preimage = sha256(unhexlify(ss)).hexdigest()
    payment_hash = sha256(unhexlify(preimage)).hexdigest()
    assert payment_hash == htlc['payment_hash']

    return {"result": "resolve", "payment_key": preimage}



plugin.run()
