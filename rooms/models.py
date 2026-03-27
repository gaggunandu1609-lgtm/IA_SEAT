from django.db import models

class Room(models.Model):
    room_number = models.CharField(max_length=50, unique=True)
    benches = models.IntegerField(help_text="Each bench holds exactly 3 students")

    @property
    def capacity(self):
        return self.benches * 3

    def __str__(self):
        return f"Room {self.room_number} (Capacity: {self.capacity})"
