"""P6-2: the user's own in-app notifications. Every row is re-checked against the access layer when shown (a notification whose alert
or plan left the user's scope disappears). Opening the page marks nothing read by itself; the button posts."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from risk.models import Notification
from risk.notifications import TEXT, visible_notifications


@login_required
def notification_list(request):
    rows = list(visible_notifications(request.user).select_related('alert', 'plan')[:100])
    items = [{'row': n, 'text': TEXT[n.kind],
              'url': 'dashboard:alert_list' if n.kind == Notification.ALERT_NEW else None, 'plan': n.plan_id}
             for n in rows]
    return render(request, 'dashboard/notifications.html', {'items': items})


@login_required
@require_POST
def notification_read(request):
    visible_notifications(request.user).filter(read_at__isnull=True).update(read_at=timezone.now())
    return redirect('dashboard:notifications')
