from business_logic.uma.uma_service import UmaService

uma = UmaService()

def get_student_profile(student_id):
    return uma.get_user_profile(student_id)
