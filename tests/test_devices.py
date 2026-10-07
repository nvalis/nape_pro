from nape_cli import devices


def test_discovery_keeps_interfaces_when_hidapi_omits_usage_metadata(monkeypatch) -> None:
    interfaces = [
        {"vendor_id": 0x3434, "product_id": 0xD026, "usage_page": 0},
        {"vendor_id": 0x3434, "product_id": 0xD026, "usage_page": 0},
    ]
    monkeypatch.setattr(
        devices, "import_module", lambda _: type("Hid", (), {"enumerate": lambda *_: interfaces})()
    )

    assert devices.enumerate_devices() == interfaces


def test_discovery_filters_known_non_mouse_interfaces(monkeypatch) -> None:
    interfaces = [
        {"usage_page": 0x0001, "interface_number": 0},
        {"usage_page": devices.BRIDGE_USAGE_PAGE, "interface_number": 1},
        {"usage_page": devices.NAPE_USAGE_PAGE, "interface_number": 2},
    ]
    monkeypatch.setattr(
        devices, "import_module", lambda _: type("Hid", (), {"enumerate": lambda *_: interfaces})()
    )

    assert devices.enumerate_devices() == interfaces[1:]
