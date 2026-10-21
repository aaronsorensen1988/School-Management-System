class AccessControl:
    """Defines role-based access rules for protected school records."""

    @staticmethod
    def can_view_student_record(
        role,
        requester_id,
        student_id,
        assigned_student_ids=None,
        child_ids=None
    ):
        """
        Determines whether a user may view a student's protected record.

        Admins may view any student record.
        Teachers may view records for assigned students.
        Students may view only their own record.
        Parents may view only their own children's records.
        """


        assigned_student_ids = assigned_student_ids or []
        child_ids = child_ids or []

        if role == "Admin":
            return True
        
        if role == "Teacher":
            return student_id in assigned_student_ids
        
        if role == "Student":
            return requester_id == student_id

        if role == "Parent":
            return student_id in child_ids

        return False

    @staticmethod
    def can_manage_students(role):
        """Who can enroll or edit a student. Admins only (T1-013, Nick).

        Teachers read their own students but don't create them, and a
        student editing their own record defeats the point of having one.
        """
        return role == "Admin"

    @staticmethod
    def can_record_attendance(role, requester_id, teacher_id):
        """Teachers may record attendance only for their own assigned sections."""
        return role == "Teacher" and requester_id == teacher_id