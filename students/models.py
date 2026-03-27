from django.db import models

class Student(models.Model):
    name = models.CharField(max_length=100)
    usn = models.CharField(max_length=20, unique=True, verbose_name="USN / Roll Number")
    department = models.CharField(max_length=100)
    semester = models.IntegerField()

    def __str__(self):
        return f"{self.name} ({self.usn})"
