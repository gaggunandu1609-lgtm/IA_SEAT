from django.db import models

class Teacher(models.Model):
    faculty_id = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name="Faculty ID")
    name = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    
    # Internal usage for tracking assigned workload
    workload = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.name} - {self.department}"
