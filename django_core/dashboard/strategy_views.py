"""P6-1 strategy library: the SchoolAdmin edits the school's list (add, edit, switch on/off); plan creation picks from the
active entries. Configuration only, no student data. Every row is looked up inside the admin's own school."""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from interventions.models import Strategy
from schools import audit

from .school_views import _render, school_page


class StrategyForm(forms.ModelForm):
    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        same = Strategy.objects.filter(school=self.school, title=title).exclude(pk=self.instance.pk)
        if same.exists():
            raise forms.ValidationError('راهبردی با این عنوان وجود دارد.')
        return title

    def clean_typical_days(self):
        days = self.cleaned_data['typical_days']
        if not 1 <= days <= 365:
            raise forms.ValidationError('عددی بین ۱ تا ۳۶۵ وارد کنید.')
        return days

    class Meta:
        model = Strategy
        fields = ['title', 'intervention_type', 'tier', 'typical_days', 'description']
        widgets = {'title': forms.TextInput(attrs={'class': 'form-control'}),
                   'intervention_type': forms.Select(attrs={'class': 'form-select'}),
                   'tier': forms.Select(attrs={'class': 'form-select'}),
                   'typical_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 365}),
                   'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3})}


@school_page
def strategies(request, school, pk=None):
    instance = get_object_or_404(Strategy, pk=pk, school=school) if pk else None
    form = StrategyForm(request.POST or None, instance=instance, school=school)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.school = school
        obj.save()
        audit.record(request.user, audit.STRATEGY_SAVE, obj, school=school, detail='edited' if instance else 'created')
        messages.success(request, 'ذخیره شد.')
        return redirect('dashboard:school_strategies')
    return _render(request, school, 'strategies.html', form=form, editing=instance,
                   rows=Strategy.objects.filter(school=school).order_by('-is_active', 'tier', 'title'))


@school_page
@require_POST
def strategy_toggle(request, school, pk):
    obj = get_object_or_404(Strategy, pk=pk, school=school)
    obj.is_active = not obj.is_active
    obj.save(update_fields=['is_active'])
    audit.record(request.user, audit.STRATEGY_SAVE, obj, school=school, detail='on' if obj.is_active else 'off')
    return redirect('dashboard:school_strategies')
