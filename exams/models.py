from django.db import models

class Exam(models.Model):
    date = models.DateField()
    time = models.TimeField()
    subject = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.subject} ({self.date} {self.time})"

class QuestionPaper(models.Model):
    subject = models.CharField(max_length=100)
    paper_code = models.CharField(max_length=20, unique=True)
    semester = models.IntegerField()

    def __str__(self):
        return f"{self.subject} [{self.paper_code}]"
