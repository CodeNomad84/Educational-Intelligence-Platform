# Deliberately not registered in the Django admin (C-A, S9; decision pack 0028 P3-10): the admin is for platform operators,
# who see no student data. Students are created, edited and imported on the school pages (dashboard/forms.py StudentForm,
# students/views.py, the bulk import), which apply the school scopes and students/student_school.py.
