from django.urls import path
from . import behavior_views, module_info, report_card, operator_page, quickstart, account_views, bulk_views, password_reset, counselor_views, loop_views, plan_views, grade_dashboard, school_views, student360, student_views, teacher_views, views

app_name = 'dashboard'

urlpatterns = [
    path('', views.login_view, name='login'),          # صفحه‌ی ورود (root)
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),  
    path('students/', views.student_list_view, name='student_list'),
    path('students/<int:pk>/', views.student_detail_view, name='student_detail'),
    path('students/<int:pk>/360/', student360.student_360, name='student_360'),
    path('chat/', views.chat_view, name='chat'),
    path('library/', views.library_view, name='library'),
    path('upload-document/', views.upload_document_view, name='upload_document'),
    path('delete-document/', views.delete_document_view, name='delete_document'),
    path('students/add/', views.student_create_view, name='student_add'),

    path('grade/', grade_dashboard.grade_dashboard, name='grade_dashboard'),

    # Student pages (Slice 4b)
    path('modules/<str:key>/', module_info.module_info, name='module_info'),
    path('platform/modules/', operator_page.overview, name='operator_overview'),   # platform operator only (base/platform, not a sellable module)
    path('me/', student_views.home, name='me_home'),
    path('me/assistant/', student_views.assistant, name='me_assistant'),
    path('students/<int:pk>/account/', student_views.create_account, name='student_account'),

    # Referral and Counselor pages (Slice 4a)
    path('students/<int:pk>/refer/', counselor_views.student_refer, name='student_refer'),
    path('students/<int:pk>/behavior/new/', behavior_views.behavior_new, name='behavior_new'),
    path('students/<int:pk>/report-card/', report_card.report_card, name='report_card'),
    path('alerts/', loop_views.alert_list, name='alert_list'),
    path('students/<int:pk>/alert/', loop_views.alert_new, name='alert_new'),
    path('alerts/<int:pk>/review/', loop_views.alert_review, name='alert_review'),
    path('alerts/<int:pk>/reopen/', loop_views.alert_reopen, name='alert_reopen'),
    path('interventions/', plan_views.plan_list, name='plan_list'),
    path('students/<int:pk>/plan/new/', plan_views.plan_new, name='plan_new'),
    path('interventions/<int:pk>/', plan_views.plan_detail, name='plan_detail'),
    path('interventions/<int:pk>/start/', plan_views.plan_start, name='plan_start'),
    path('interventions/<int:pk>/cancel/', plan_views.plan_cancel, name='plan_cancel'),
    path('interventions/<int:pk>/complete/', plan_views.plan_complete, name='plan_complete'),
    path('interventions/<int:pk>/reassign/', plan_views.plan_reassign, name='plan_reassign'),
    path('interventions/<int:pk>/followup/', plan_views.plan_followup, name='plan_followup'),
    path('counselor/', counselor_views.home, name='counselor_home'),
    path('counselor/case/<int:pk>/', counselor_views.case, name='counselor_case'),
    path('counselor/case/<int:pk>/close/', counselor_views.case_close, name='counselor_close'),

    # Subject Teacher pages (Slice 2)
    path('teacher/', teacher_views.home, name='teacher_home'),
    path('teacher/<int:pk>/grades/', teacher_views.grade_sheet, name='teacher_grades'),
    path('teacher/<int:pk>/grades/<int:grade_pk>/delete/', teacher_views.grade_delete, name='teacher_grade_delete'),
    path('teacher/<int:pk>/students/<int:student_pk>/', teacher_views.student_page, name='teacher_student'),

    # Account (every signed-in user): profile and password change
    path('account/', account_views.profile, name='profile'),
    path('account/password/', account_views.password_change, name='password_change'),

    # SchoolAdmin: bulk accounts from Excel and staff roles (before the generic 'school/<kind>/' routes)
    path('school/quickstart/', quickstart.quickstart, name='quickstart'),
    path('school/accounts/', bulk_views.accounts, name='school_accounts'),
    path('school/accounts/template/', bulk_views.accounts_template, name='school_accounts_template'),
    path('school/accounts/preview/', bulk_views.accounts_preview, name='school_accounts_preview'),
    path('school/accounts/confirm/', bulk_views.accounts_confirm, name='school_accounts_confirm'),
    path('school/accounts/cancel/', bulk_views.accounts_cancel, name='school_accounts_cancel'),
    path('school/resets/', password_reset.admin_resets, name='school_resets'),
    path('school/resets/setting/', password_reset.admin_reset_setting, name='school_resets_setting'),
    path('school/resets/<int:pk>/', password_reset.admin_reset, name='school_reset'),
    path('grade/resets/', password_reset.grade_resets, name='grade_resets'),
    path('grade/resets/<int:pk>/', password_reset.grade_reset, name='grade_reset'),
    path('school/staff-roles/', bulk_views.staff_roles, name='school_staff_roles'),
    path('school/staff-roles/<int:pk>/', bulk_views.staff_roles_save, name='school_staff_roles_save'),

    # SchoolAdmin pages (Slice 1)
    path('school/', school_views.home, name='school_home'),
    path('school/years/', school_views.years, name='school_years'),
    path('school/years/<int:pk>/current/', school_views.year_set_current, name='school_year_current'),
    path('school/audit/', school_views.audit_log, name='school_audit'),
    path('school/classes/', school_views.classes, name='school_classes'),
    path('school/classes/new/', school_views.class_edit, name='school_class_new'),
    path('school/classes/<int:pk>/edit/', school_views.class_edit, name='school_class_edit'),
    path('school/<str:kind>/', school_views.staff_list, name='school_staff'),
    path('school/<str:kind>/<int:pk>/', school_views.staff_detail, name='school_staff_detail'),
    path('school/<str:kind>/<int:pk>/active/', school_views.staff_toggle_active, name='school_staff_active'),
    path('school/<str:kind>/<int:pk>/assignments/<int:assignment_pk>/delete/', school_views.assignment_delete,
         name='school_assignment_delete'),

]

# DEMO SCOPE begin — extra routes, registered only when config.settings.demo is active
from django.conf import settings as _demo_settings
if getattr(_demo_settings, 'DEMO_MODE', False):
    from demo_intel import views as demo_views
    urlpatterns += [
        path('demo/school/', demo_views.school_dashboard_page, name='demo_school'),
        path('demo/counselor/', demo_views.counselor_view, name='demo_counselor'),
        path('demo/students/', demo_views.demo_student_list, name='demo_students'),
        path('demo/assistant/', demo_views.assistant_view, name='demo_assistant'),
    ]
# DEMO SCOPE end
