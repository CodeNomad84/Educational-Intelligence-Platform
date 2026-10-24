"""Static quick-start page for the SchoolAdmin (base feature, no module gate, no school or student data on it)."""
from django.shortcuts import render

from students.access import ADMIN

from .decorators import role_required


@role_required(ADMIN)
def quickstart(request):
    return render(request, 'dashboard/quickstart.html')
