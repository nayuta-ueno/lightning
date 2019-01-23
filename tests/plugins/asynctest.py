#!/usr/bin/env python3
"""This plugin is used to check that async method calls are working correctly.

The plugin registers a method `callme` with an argument. All calls are
stashed away, and are only resolved on the fifth invocation. All calls
will then return the argument of the fifth call.

"""
from lightning import Plugin

plugin = Plugin()
requests = []


@plugin.method('asyncqueue', sync=False)
def async_queue(request):
    global requests
    requests.append(request)


@plugin.method('asyncflush')
def async_flush(res):
    global requests
    for r in requests:
        r.set_result(res)


plugin.run()
