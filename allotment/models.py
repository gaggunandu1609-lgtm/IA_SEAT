from django.db import models
from students.models import Student
from rooms.models import Room
from exams.models import Exam
from teachers.models import Teacher

class SeatAllotment(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    bench_number = models.IntegerField()
    
    # 3 students per bench
    student_1 = models.ForeignKey(Student, related_name="seat_1", on_delete=models.SET_NULL, null=True, blank=True)
    student_2 = models.ForeignKey(Student, related_name="seat_2", on_delete=models.SET_NULL, null=True, blank=True)
    student_3 = models.ForeignKey(Student, related_name="seat_3", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ('exam', 'room', 'bench_number')

    def __str__(self):
        return f"Exam: {self.exam.subject} | Room: {self.room.room_number} | Bench: {self.bench_number}"

class TeacherAllotment(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)

    class Meta:
        pass  # Multiple teachers can be assigned to the same room/session

    def __str__(self):
        return f"Invigilator: {self.teacher.name} | Room: {self.room.room_number} | Exam: {self.exam.subject}"
