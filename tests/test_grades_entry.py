from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app


client = TestClient(app)


class DummyActor:
    role = "Teacher"
    user_id = 1


@patch("presentation.grades_routes.current_actor")
def test_get_grade_entry_page(mock_current_actor):
    mock_current_actor.return_value = DummyActor()

    response = client.get("/grades/entry")

    assert response.status_code == 200
    assert "Enter Student Grade" in response.text


@patch("presentation.grades_routes.GradeService.record_grade")
@patch("presentation.grades_routes.current_actor")
def test_post_grade_entry(mock_current_actor, mock_record_grade):
    mock_current_actor.return_value = DummyActor()

    form_data = {
        "student_id": 1,
        "assignment_id": 1,
        "points_earned": 95.0,
    }

    response = client.post(
        "/grades/entry",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/grades/entry"

    mock_record_grade.assert_called_once()

    args = mock_record_grade.call_args.args

    assert args[1].user_id == 1
    assert args[2] == 1
    assert args[3] == 1
    assert args[4] == 95.0


class DummyStudentActor:
    role = "Student"
    user_id = 2


@patch("presentation.grades_routes.current_actor")
def test_non_teacher_cannot_open_grade_entry(mock_current_actor):
    mock_current_actor.return_value = DummyStudentActor()

    response = client.get("/grades/entry")

    assert response.status_code == 403