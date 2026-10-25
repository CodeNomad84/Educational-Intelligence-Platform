"""Shared fixture for the intervention-loop tests (not a test module). Two schools, every role, synthetic data only."""
from datetime import date, timedelta

from dashboard.test_counselor import Base, make_user
from schools.models import GradeLeadAssignment, TeacherAssignment


class LoopBase(Base):
    def setUp(self):
        super().setUp()
        self.teacher = make_user('teacher', 'Teacher', self.a)
        TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.c7, subject='math')
        self.lead8 = make_user('lead8', 'GradeLead', self.a)
        GradeLeadAssignment.objects.create(user=self.lead8, school=self.a, grade=8, academic_year='1404-1405')
        self.lead_b = make_user('lead-b', 'GradeLead', self.b)
        GradeLeadAssignment.objects.create(user=self.lead_b, school=self.b, grade=7, academic_year='1404-1405')
        self.student_user = make_user('stud', 'Student')
        self.s7.student_user = self.student_user
        self.s7.parent_user = self.parent
        self.s7.save()
        self.today = date.today()
        self.week = self.today + timedelta(days=7)

    def alert(self, student=None, by=None, **extra):
        from risk.services import raise_alert_as
        args = dict(risk_type='academic', severity='yellow', message='Marks dropped')
        args.update(extra)
        return raise_alert_as(by or self.admin, student or self.s7, **args)

    def accepted(self, student=None, **extra):
        from risk.models import Alert
        from risk.services import review_alert
        alert = self.alert(student, **extra)
        review_alert(self.admin, alert, Alert.ACCEPTED)
        alert.refresh_from_db()
        return alert

    def plan(self, by=None, student=None, kind='academic', **extra):
        from interventions.services import create_plan
        args = dict(intervention_type=kind, goal='Raise marks', action_plan='Weekly review',
                    start_date=self.today, due_date=self.week)
        args.update(extra)
        return create_plan(by or self.admin, student or self.s7, **args)
