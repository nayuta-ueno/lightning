from collections import OrderedDict
from fixtures import *  # noqa: F401,F403
from lightning import RpcError

import pytest
import subprocess
import time


def test_option_passthrough(node_factory):
    """ Ensure that registering options works.

    First attempts without the plugin and then with the plugin.
    """
    plugin_path = 'contrib/plugins/helloworld.py'

    help_out = subprocess.check_output([
        'lightningd/lightningd',
        '--help'
    ]).decode('utf-8')
    assert('--greeting' not in help_out)

    help_out = subprocess.check_output([
        'lightningd/lightningd',
        '--plugin={}'.format(plugin_path),
        '--help'
    ]).decode('utf-8')
    assert('--greeting' in help_out)

    # Now try to see if it gets accepted, would fail to start if the
    # option didn't exist
    n = node_factory.get_node(options={'plugin': plugin_path, 'greeting': 'Ciao'})
    n.stop()


def test_rpc_passthrough(node_factory):
    """Starting with a plugin exposes its RPC methods.

    First check that the RPC method appears in the help output and
    then try to call it.

    """
    plugin_path = 'contrib/plugins/helloworld.py'
    n = node_factory.get_node(options={'plugin': plugin_path, 'greeting': 'Ciao'})

    # Make sure that the 'hello' command that the helloworld.py plugin
    # has registered is available.
    cmd = [hlp for hlp in n.rpc.help()['help'] if 'hello' in hlp['command']]
    assert(len(cmd) == 1)

    # While we're at it, let's check that helloworld.py is logging
    # correctly via the notifications plugin->lightningd
    assert n.daemon.is_in_log('Plugin helloworld.py initialized')

    # Now try to call it and see what it returns:
    greet = n.rpc.hello(name='World')
    assert(greet == "Ciao World")
    with pytest.raises(RpcError):
        n.rpc.fail()


def test_plugin_dir(node_factory):
    """--plugin-dir works"""
    plugin_dir = 'contrib/plugins'
    node_factory.get_node(options={'plugin-dir': plugin_dir, 'greeting': 'Mars'})


def test_plugin_disable(node_factory):
    """--disable-plugin works"""
    plugin_dir = 'contrib/plugins'
    # We need plugin-dir before disable-plugin!
    n = node_factory.get_node(options=OrderedDict([('plugin-dir', plugin_dir),
                                                   ('disable-plugin',
                                                    '{}/helloworld.py'
                                                    .format(plugin_dir))]))
    with pytest.raises(RpcError):
        n.rpc.hello(name='Sun')

    # Also works by basename.
    n = node_factory.get_node(options=OrderedDict([('plugin-dir', plugin_dir),
                                                   ('disable-plugin',
                                                    'helloworld.py')]))
    with pytest.raises(RpcError):
        n.rpc.hello(name='Sun')


def test_plugin_hook(node_factory, executor):
    """The helloworld plugin registers a htlc_accepted hook.

    The hook will sleep for a few seconds and log a
    message. `lightningd` should wait for the response and only then
    complete the payment.

    """
    l1, l2 = node_factory.line_graph(2, opts={'plugin': 'contrib/plugins/helloworld.py'})
    start_time = time.time()
    f = executor.submit(l1.pay, l2, 100000)
    l2.daemon.wait_for_log(r'on_htlc_accepted called')

    # The hook will sleep for 20 seconds before answering, so `f`
    # should take at least that long.
    f.result()
    end_time = time.time()
    assert(end_time >= start_time + 20)


def test_plugin_notifications(node_factory):
    l1, l2 = node_factory.get_nodes(2, opts={'plugin': 'contrib/plugins/helloworld.py'})

    l1.connect(l2)
    l1.daemon.wait_for_log(r'Received connect event')
    l2.daemon.wait_for_log(r'Received connect event')

    l2.rpc.disconnect(l1.info['id'])
    l1.daemon.wait_for_log(r'Received disconnect event')
    l2.daemon.wait_for_log(r'Received disconnect event')


def test_failing_plugins():
    fail_plugins = [
        'contrib/plugins/fail/failtimeout.py',
        'contrib/plugins/fail/doesnotexist.py',
    ]

    for p in fail_plugins:
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.check_output([
                'lightningd/lightningd',
                '--plugin={}'.format(p),
                '--help',
            ])


def test_pay_plugin(node_factory):
    l1, l2 = node_factory.line_graph(2)
    inv = l2.rpc.invoice(123000, 'label', 'description', 3700)

    res = l1.rpc.pay(bolt11=inv['bolt11'])
    assert res['status'] == 'complete'

    with pytest.raises(RpcError, match=r'missing required parameter'):
        l1.rpc.call('pay')


def test_async_rpcmethod(node_factory, executor):
    """This tests the async rpcmethods.

    It works in conjunction with the `asynctest` plugin which stashes
    requests and then resolves all of them on the fifth call.
    """
    l1 = node_factory.get_node(options={'plugin': 'tests/plugins/asynctest.py'})

    results = []
    for i in range(10):
        results.append(executor.submit(l1.rpc.asyncqueue))

    time.sleep(3)

    # None of these should have returned yet
    assert len([r for r in results if r.done()]) == 0

    # This last one triggers the release and all results should be 42,
    # since the last number is returned for all
    l1.rpc.asyncflush(42)

    assert [r.result() for r in results] == [42] * len(results)


def test_htlc_accepted_hook_fail(node_factory):
    """Send payments from l1 to l2, but l2 just declines everything.

    l2 is configured with a plugin that'll hook into htlc_accepted and
    always return failures. The same should also work for forwarded
    htlcs in the second half.

    """
    l1, l2, l3 = node_factory.line_graph(3, opts=[
        {},
        {'plugin': 'tests/plugins/fail_htlcs.py'},
        {}
    ], wait_for_announce=True)

    # This must fail
    inv = l2.rpc.invoice(1000, "lbl", "desc")['bolt11']
    with pytest.raises(RpcError) as excinfo:
        l1.rpc.pay(inv)
    assert excinfo.value.error['data']['failcode'] == 16399
    assert excinfo.value.error['data']['erring_index'] == 1

    # And the invoice must still be unpaid
    inv = l2.rpc.listinvoices("lbl")['invoices']
    assert len(inv) == 1 and inv[0]['status'] == 'unpaid'

    # Now try with forwarded HTLCs: l2 should still fail them
    # This must fail
    inv = l3.rpc.invoice(1000, "lbl", "desc")['bolt11']
    with pytest.raises(RpcError) as excinfo:
        l1.rpc.pay(inv)

    # And the invoice must still be unpaid
    inv = l3.rpc.listinvoices("lbl")['invoices']
    assert len(inv) == 1 and inv[0]['status'] == 'unpaid'


def test_htlc_accepted_hook_resolve(node_factory):
    """l3 creates an invoice, l2 knows the preimage and will shortcircuit.
    """
    l1, l2, l3 = node_factory.line_graph(3, opts=[
        {},
        {'plugin': 'tests/plugins/shortcircuit.py'},
        {}
    ], wait_for_announce=True)

    inv = l3.rpc.invoice(msatoshi=1000, label="lbl", description="desc", preimage="00" * 32)['bolt11']
    l1.rpc.pay(inv)

    # And the invoice must still be unpaid
    inv = l3.rpc.listinvoices("lbl")['invoices']
    assert len(inv) == 1 and inv[0]['status'] == 'unpaid'


def test_multipart_pay_receive(node_factory):
    l1, l2, l3 = node_factory.line_graph(3, opts=[
        {},
        {},
        {'plugin': 'contrib/plugins/mppay.py'},
    ], wait_for_announce=True)

    inv = l3.rpc.invoice(
        msatoshi=100000,
        label='lbl',
        description='desc',
        preimage='00' * 32
    )
    print(inv)
    print(l3.rpc.listinvoices())

    route = l1.rpc.getroute(node_id=l3.info['id'],
                            msatoshi=50000,
                            riskfactor=1)['route']
    l1.rpc.sendpay(route, inv['payment_hash'])

    time.sleep(10)
    # This should complete the payment
    route = l2.rpc.getroute(node_id=l3.info['id'],
                            msatoshi=50000,
                            riskfactor=1)['route']
    l2.rpc.sendpay(route, inv['payment_hash'])

    l1.rpc.waitsendpay(inv['payment_hash'], 10)
    l2.rpc.waitsendpay(inv['payment_hash'], 10)
