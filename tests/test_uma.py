from business_logic.uma.uma_service import UmaService

def test_profile():
    uma = UmaService()
    assert uma.get_user_profile("1")["user_id"] == "1"
