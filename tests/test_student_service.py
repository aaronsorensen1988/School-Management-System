"""Unit tests for student enrollment validation. SIEM-004 / T1-018.

Run with:  python -m unittest tests.test_student_service -v
"""

import unittest
from datetime import date

from business_logic.siem.student_service import validate_student

# A fixed "today" so the tests give the same result every day.
TODAY = date(2026, 10, 16)


def valid_form(**overrides):
    form = {
        "student_number": "S10045",
        "first_name": "Maya",
        "last_name": "Lopez",
        "date_of_birth": "2012-04-09",
        "grade_level": "8",
        "home_address": "123 Main St, Denver, CO",
        "guardian_name": "Ana Lopez",
        "guardian_email": "ana.lopez@example.com",
    }
    form.update(overrides)
    return form


class ValidateStudentTests(unittest.TestCase):

    def test_valid_form_has_no_errors(self):
        cleaned, errors = validate_student(valid_form(), today=TODAY)
        self.assertEqual(errors, {})
        self.assertEqual(cleaned["grade_level"], 8)

    def test_values_are_trimmed(self):
        cleaned, errors = validate_student(valid_form(first_name="  Maya  "), today=TODAY)
        self.assertEqual(errors, {})
        self.assertEqual(cleaned["first_name"], "Maya")

    def test_every_field_is_required(self):
        cleaned, errors = validate_student({}, today=TODAY)
        self.assertEqual(len(errors), 8)
        self.assertIn("required", errors["first_name"])

    def test_blank_spaces_count_as_missing(self):
        _, errors = validate_student(valid_form(last_name="   "), today=TODAY)
        self.assertIn("last_name", errors)

    def test_student_id_rejects_symbols(self):
        _, errors = validate_student(valid_form(student_number="S1004;DROP"), today=TODAY)
        self.assertIn("student_number", errors)

    def test_future_birth_date_rejected(self):
        _, errors = validate_student(valid_form(date_of_birth="2030-01-01"), today=TODAY)
        self.assertIn("in the past", errors["date_of_birth"])

    def test_invalid_birth_date_rejected(self):
        _, errors = validate_student(valid_form(date_of_birth="2012-02-30"), today=TODAY)
        self.assertIn("valid date", errors["date_of_birth"])

    def test_age_out_of_range_rejected(self):
        _, errors = validate_student(valid_form(date_of_birth="1990-01-01"), today=TODAY)
        self.assertIn("years old", errors["date_of_birth"])

    def test_grade_must_be_k_through_12(self):
        _, errors = validate_student(valid_form(grade_level="13"), today=TODAY)
        self.assertIn("grade_level", errors)

    def test_kindergarten_is_allowed(self):
        cleaned, errors = validate_student(
            valid_form(grade_level="0", date_of_birth="2021-03-01"), today=TODAY
        )
        self.assertEqual(errors, {})
        self.assertEqual(cleaned["grade_level"], 0)

    def test_bad_guardian_email_rejected(self):
        _, errors = validate_student(valid_form(guardian_email="not-an-email"), today=TODAY)
        self.assertIn("guardian_email", errors)


if __name__ == "__main__":
    unittest.main()
