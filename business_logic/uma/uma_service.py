class UmaService:
    def get_user_profile(self, user_id):
        return {
            "user_id": user_id,
            "name": "Test User",
            "role": "student"
        }
