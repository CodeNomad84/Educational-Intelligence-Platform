# students/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from .models import Student

@shared_task
def send_welcome_email(student_id):
    try:
        student = Student.objects.get(id=student_id)
        send_mail(
            'خوش آمدید',
            f'{student.first_name} عزیز، به پلتفرم مدرسه خوش آمدید!',
            'noreply@school.com',
            [student.phone_number + '@sms_provider.com'],  # نمونه
            fail_silently=True,
        )
        return f"Email sent to {student.first_name}"
    except Student.DoesNotExist:
        return "Student not found"