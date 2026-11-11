"""Evaluate active-device and patch-quota warnings without changing app/runtime state."""
from datetime import datetime, timedelta, timezone


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('missing timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp has no timezone')
    return parsed


def active_devices(metrics, now):
    if not isinstance(metrics, dict) or not isinstance(metrics.get('current'), dict):
        raise ValueError('missing device metrics')
    window = metrics['current']
    count = window.get('unique_users')
    if type(count) is not int or count < 0 or not isinstance(window.get('range'), dict):
        raise ValueError('invalid active-device count')
    start, end = timestamp(window['range'].get('start')), timestamp(window['range'].get('end'))
    as_of = timestamp(metrics.get('as_of'))
    if (not start < end or now - as_of > timedelta(hours=2)
            or now - end > timedelta(hours=2) or max(as_of, end) - now > timedelta(minutes=5)):
        raise ValueError('stale or invalid metric window')
    return count, start.isoformat(), end.isoformat()


def quota_description(usage):
    position = usage.get('position') if isinstance(usage, dict) else None
    if not isinstance(position, dict):
        return 'استهلاك الكوتا غير متاح لهذا الحساب؛ لا يُعتبر صفرًا.', False
    fields = [position.get('installs'), position.get('included_installs'), position.get('remaining_installs')]
    if all(type(value) is int and value >= 0 for value in fields):
        detail = f'الكوتا المشتركة: {fields[0]} تثبيت patch مستخدم، {fields[1]} ضمن الخطة، {fields[2]} متبقٍ حتى الحد.'
    elif (all(type(value) is int and value >= 0 for value in fields[:2])
          and 'remaining_installs' in position and position['remaining_installs'] is None
          and 'install_ceiling' in position and position['install_ceiling'] is None):
        detail = f'الكوتا المشتركة: {fields[0]} تثبيت patch مستخدم، {fields[1]} ضمن الخطة. لا يوجد حد إيقاف محدد؛ هذا لا يعني تثبيتات مجانية بلا حدود.'
    else:
        detail = 'تفاصيل الكوتا المشتركة غير مكتملة؛ لا يمكن حساب تكلفة دقيقة.'
    costly = position.get('at_ceiling') is True or position.get('consuming_overage') is True
    if costly:
        detail += ' الحساب بلغ الحد أو يستهلك تثبيتات إضافية مدفوعة.'
    return detail, costly


def usage_warning(metrics, usage, threshold=400, *, now=None):
    """Return a blocking warning, or empty text; count devices, never sum daily users."""
    now = now or datetime.now(timezone.utc)
    quota, costly = quota_description(usage)
    try:
        users, start, end = active_devices(metrics, now)
        population = f'نحو {users} جهاز نشط في الفترة {start} إلى {end} (تقدير Shorebird؛ ليس إجمالي تنزيلات المتجر).'
        if users <= threshold and not costly:
            return ''
        reason = f'عدد الأجهزة النشطة يتجاوز حد التنبيه {threshold}.' if users > threshold else 'الكوتا تحتاج مراجعة قبل النشر.'
    except (ValueError, TypeError):
        population = 'تعذر التحقق من عدد الأجهزة النشطة ببيانات حديثة؛ لا نفترض أن العدد صفر.'
        reason = f'فحص حد التنبيه {threshold} غير مكتمل.'
    return (f'تنبيه Shorebird: {population} {reason} كل patch يُثبت بنجاح يستهلك من الكوتا المشتركة. '
            f'{quota} توقف قبل النشر: اختر الاستمرار صراحةً أو التخطيط لإصدار متجر بدون Shorebird. '
            'لا يُحذف التطبيق ولا تتغير طريقة بنائه تلقائيًا.')
