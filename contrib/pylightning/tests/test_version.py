import lightning


def test_version():
    """Make sure version numbers match"""
    ver = [line.rstrip().split('=', 1)[1] for line in open('contrib/pylightning/setup.py') if 'version=' in line]
    assert ver == ["'{}',".format(lightning.__version__)]
