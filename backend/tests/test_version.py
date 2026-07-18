from app.version import feature_version, version_info, version_label


def test_version_info():
    info = version_info()
    assert info["major"] == 2
    assert info["minor"] == 0
    assert info["build"] == 14
    assert info["feature_version"] == "2.0"
    assert info["label"] == "V2.0-Build 14"
    assert feature_version() == "2.0"
    assert version_label() == "V2.0-Build 14"
