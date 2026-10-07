from presentation.controllers.student_controller import get_student_profile

def route_request(path, params):
    if path == "/student/profile":
        return get_student_profile(params.get("id"))
    return {"error": "Route not found"}
