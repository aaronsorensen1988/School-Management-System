import pytest

from business_logic.uma.access_control import AccessControl


def test_admin_can_send_emergency_notification():
    assert AccessControl.can_send_emergency_notification("Admin") is True


@pytest.mark.parametrize(
    "role",
    ["Teacher", "Student", "Parent", None],
)
def test_non_admin_cannot_send_emergency_notification(role):
    assert AccessControl.can_send_emergency_notification(role) is False