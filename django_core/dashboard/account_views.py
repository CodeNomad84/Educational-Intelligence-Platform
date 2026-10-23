"""Profile page and password change for every signed-in account. A generated initial password (bulk onboarding) is
flagged ``must_change_password``; ``ForcePasswordChangeMiddleware`` sends such accounts here until they chose their own."""
from django import forms
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render

from schools.models import AccountProfile
from students.access import roles_for

from .home import home_url_for


class ChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1') or ''
        if len(password) < 8:   # the project configures no password validators; same minimum as the other account forms
            raise forms.ValidationError('رمز عبور باید دست‌کم ۸ نویسه باشد.')
        if password.isdigit():
            raise forms.ValidationError('رمز عبور نباید فقط عدد باشد.')
        if password == self.user.username:
            raise forms.ValidationError('رمز عبور نباید با نام کاربری یکسان باشد.')
        return password

    def clean(self):
        cleaned = super().clean()
        new, old = cleaned.get('new_password1'), cleaned.get('old_password')
        if new and old and new == old:
            self.add_error('new_password1', 'رمز جدید باید با رمز فعلی فرق داشته باشد.')
        return cleaned


def _page(request, form, forced):
    return render(request, 'dashboard/account/profile.html', {
        'form': form, 'forced': forced, 'roles': sorted(roles_for(request.user))})


@login_required
def profile(request):
    return _page(request, ChangeForm(request.user), False)


@login_required
def password_change(request):
    forced = AccountProfile.objects.filter(user=request.user, must_change_password=True).exists()
    form = ChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        AccountProfile.objects.filter(user=request.user).update(must_change_password=False)
        update_session_auth_hash(request, request.user)   # stay signed in with the new password
        messages.success(request, 'رمز عبور تغییر کرد.')
        return redirect(home_url_for(request.user))
    return _page(request, form, forced)
