#!/usr/bin/env python3
"""This plugin is used to check that async method calls are working correctly.

The plugin registers a method `callme` with an argument. All calls are
stashed away, and are only resolved on the fifth invocation. All calls
will then return the argument of the fifth call.

"""
from lightning import Plugin

plugin = Plugin()
requests = []


@plugin.method('callme', sync=False)
def callme(i, request):
    global requests

    requests.append(request)
    if len(requests) < 5:
        return

    for r in requests:
        r.set_result(i)


plugin.run()
