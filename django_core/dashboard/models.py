from django.db import models

# Create your models here.
class Homework(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='homeworks')
    subject = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    due_date = models.DateField()
    completion_rate = models.FloatField(default=0)  # درصد تکمیل
    status = models.CharField(max_length=20, choices=[('pending','در انتظار'),('completed','انجام شده'),('late','دیرکرد')])
    teacher_comment = models.TextField(blank=True)

class TeacherParentCommunication(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='communications')
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='teacher_comms')
    date = models.DateField()
    type = models.CharField(max_length=20, choices=[('meeting','جلسه'),('message','پیام'),('call','تماس')])
    content = models.TextField()