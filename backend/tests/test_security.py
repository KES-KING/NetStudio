import pytest

from app.security import MissingSecret, Permission, Role, SessionUser, UnavailableSecretStore, has_permission


def test_site_scoped_permission_is_fail_closed():
    user = SessionUser(user_id="u-1", display_name="Engineer", roles={Role.ENGINEER}, site_ids={"LAB / Demo"})
    assert has_permission(user, Permission.INVENTORY_READ, "LAB / Demo")
    assert has_permission(user, Permission.CONFIG_PLAN, "LAB / Demo")
    assert not has_permission(user, Permission.CONFIG_APPLY, "LAB / Demo")
    assert not has_permission(user, Permission.INVENTORY_READ, "OTHER")


def test_unconfigured_secret_store_never_returns_a_value():
    with pytest.raises(MissingSecret):
        UnavailableSecretStore().get("device/demo/password")
