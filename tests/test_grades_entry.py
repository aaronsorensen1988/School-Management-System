from fastapi.testclient import TestClient
from api import app
from database.database import SessionLocal
from database.grades import Grade

client = TestClient(app)

def test_get_grade_entry_page():
    response = client.get("/grades/entry")
    assert response.status_code == 200
    assert "Enter Student Grade" in response.text

def test_post_grade_entry_and_update():
    # 1. Test Initial Insertion
    form_data = {
        "student_id": 1,
        "assignment_id": 1,
        "points_earned": 95.0
    }
    response = client.post("/grades/entry", data=form_data)
    assert response.status_code == 200
    
    db = SessionLocal()
    try:
        # Verify it was inserted correctly
        grade = db.query(Grade).filter_by(student_id=1, assignment_id=1).first()
        assert grade is not None
        assert grade.points_earned == 95.0
        
        # 2. Test Updating the Existing Grade
        form_data["points_earned"] = 82.5
        client.post("/grades/entry", data=form_data)
        
        # Verify the database updated the existing row instead of adding a new one
        db.expire_all()  # Clear cache to get fresh DB data
        updated_grade = db.query(Grade).filter_by(student_id=1, assignment_id=1).first()
        assert updated_grade.points_earned == 82.5
        
        # Verify we didn't create duplicate rows
        total_grades = db.query(Grade).filter_by(student_id=1, assignment_id=1).count()
        assert total_grades == 1
    finally:
        db.close()