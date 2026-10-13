# DEMO SCOPE — whole file.
from django.contrib import admin

from .models import CounselingNote, InterventionRecord, StudentObservation

admin.site.register(StudentObservation)
admin.site.register(CounselingNote)
admin.site.register(InterventionRecord)
