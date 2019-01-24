#!/usr/bin/env python3
from lightning import Plugin
from threading import Timer

plugin = Plugin()


class Payment(object):
    def __init__(self, plugin, payment_hash, invoice):
        self.payment_hash = payment_hash
        self.parts = []
        self.invoice = invoice
        self.plugin = plugin

    def is_complete(self):
        incoming = sum()
        return incoming >= self.invoice['msatoshi']

    def resolve_all(self):
        for p in self.parts:
            p.htlc_hook.set_result({
                "result": "resolve",
                "payment_key": "00" * 32,
            })
        self.parts = []

    def fail_all(self):
        for p in self.parts:
            p.htlc_hook.set_result({
                "result": "fail",
            })
        self.parts = []

    def timeout(self):
        """The payment has exceeded the allowed time, let's free those HTLCs

        """
        if self.parts == []:
            # Nothing to be done, we already cleared it before.
            return
        self.plugin.log("Failing payment {} ({} parts) due to timeout".format(
            self.payment_hash,
            len(self.parts)
        ))
        self.fail_all()


class PaymentPart(object):
    def __init__(self, htlc, htlc_hook):
        self.htlc_hook = htlc_hook
        self.htlc = htlc


@plugin.method('init')
def init(configuration, options, plugin):
    # This is a dict in which we'll store all the incoming payments
    # indexed by their payment_hash
    plugin.incoming_payments = {}


@plugin.method('mppay')
def mppay():
    pass


@plugin.hook('htlc_accepted', sync=False)
def on_htlc_accepted(htlc, onion, plugin, request):
    h = htlc['payment_hash']

    # Check that we have a matching invoice, otherwise continue
    if h not in plugin.incoming_payments:
        invs = plugin.rpc.listinvoices('h')['invoices']
        if len(invs):
            plugin.log(
                "Could not find an invoice for payment_hash {}".format(h)
            )
            return request.set_result({'result': 'continue'})

        # Now initialize the payment object, so we can assign parts
        inv = invs[0]
        p = Payment(h, inv)
        Timer(300, p.timeout).start()
        plugin.incoming_payments[h] = p

    payment = plugin.incoming_payments[h]
    payment.parts.append(PaymentPart(
        htlc=htlc,
        htlc_hook=request,
    ))

    if payment.is_complete():
        payment.resolve_all()


plugin.run()
