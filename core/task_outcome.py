"""Shared vocabulary, not another task engine or a source of authority."""


def execution_outcome(status, verification=None, cleanup=None):
    verification = dict(verification or {'status': 'NOT VERIFIED'})
    # A UI text match is a scoped observation, NEVER whole-task acceptance.
    return {'execution_status': str(status), 'evidence_status': verification.get('status', 'NOT VERIFIED'),
            'evidence_scope': verification.get('scope', ''), 'goal_accepted': False,
            'acceptance_basis': 'Separate explicit acceptance required; model/process completion is insufficient',
            'cleanup_status': (cleanup or {}).get('status', 'not_started')}


def stop_summary(reason, verification=None):
    """Short human-facing result; the exact technical reason stays in evidence."""
    value = str(reason).lower()
    if 'foreground' in value or 'user takeover' in value:
        return 'Pencere odağı değiştiği için bilgisayar kontrolü güvenle durduruldu.'
    if 'permission' in value:
        return 'İzin reddedildi veya süresi doldu; görev durduruldu.'
    if value == 'cancelled': return 'Görev durduruldu; yeni işlem yapılmayacak.'
    if value == 'completed':
        return 'Ajan yürütmesi tamamlandı; bu, tüm hedefin doğrulandığı anlamına gelmez.'
    if value == 'expired': return 'Görev süresi doldu; kontrol bırakıldı.'
    return 'Görev tamamlanamadı; kontrol bırakıldı. Ayrıntılar hata kaydında.'


def cleanup_step(report, name, action):
    """Attempt every release independently; do not hide or short-circuit errors."""
    try:
        action()
        report['steps'].append({'name': name, 'status': 'completed'})
    except Exception as exc:
        report['steps'].append({'name': name, 'status': 'failed', 'error': str(exc)})
