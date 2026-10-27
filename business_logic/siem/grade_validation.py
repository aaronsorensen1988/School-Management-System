"""Grade validation rules. AMG-008 / T2-014. Shanna.

These run before a grade is saved, so the teacher gets a clear message
instead of a crash page or a silently wrong number.

Nick's table (T2-012) already refuses a negative score, but only as a
database error. These checks catch it first with a readable message, plus
the ones the database can't know about:
  - the score has to be a real number (not blank, not text, not "inf")
  - extra credit is allowed, up to a limit, so a typo like 950 instead of
    95 gets caught instead of saved

Who may enter a grade and whether the student is in the class is Sean's
T2-013 (grade_service.py / AccessControl), not this file.
"""

import math

# How far above an assignment's points a score may go, as a percent.
# 120 means a 100 point quiz can take up to 120 points of extra credit.
# This is a team policy call, so it lives in one place and is easy to change.
MAX_PERCENT = 120


class GradeValidationError(ValueError):
    """Raised when a score breaks one of the T2-014 rules."""


def _fmt(number):
    """95.0 -> '95', 92.5 -> '92.5'."""
    return f"{number:g}"


def parse_points(raw):
    """Form text -> (float, None) or (None, error message)."""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None, "Enter the points earned."
    try:
        points = float(text)
    except ValueError:
        return None, "Points must be a number, like 92 or 92.5."
    if math.isnan(points) or math.isinf(points):
        return None, "Points must be a number, like 92 or 92.5."
    return points, None


def check_points(points, points_possible):
    """Error message for the score, or None if it's fine."""
    if points is None or math.isnan(points) or math.isinf(points):
        return "Points must be a number, like 92 or 92.5."
    if points < 0:
        return "Points can't be negative."
    cap = points_possible * MAX_PERCENT / 100
    if points > cap:
        return (
            f"{_fmt(points)} is more than this assignment allows. It's out of "
            f"{_fmt(points_possible)}, and extra credit can go up to "
            f"{_fmt(cap)} ({MAX_PERCENT}%)."
        )
    return None


def validate_points(points, points_possible):
    """Raise GradeValidationError if the score breaks a rule."""
    problem = check_points(points, points_possible)
    if problem:
        raise GradeValidationError(problem)
