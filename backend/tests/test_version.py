from app.version import feature_version, version_info, version_label


def test_version_info():
    info = version_info()
    assert info["major"] == 2
    assert info["minor"] == 4
    assert info["build"] == 2
    assert info["feature_version"] == "2.4"
    assert info["label"] == "V2.4-Build 2"
    assert feature_version() == "2.4"
    assert version_label() == "V2.4-Build 2"
