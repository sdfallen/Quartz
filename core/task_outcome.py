"""Shared vocabulary, not another task engine or a source of authority."""


def execution_outcome(status, verification=None, cleanup=None, *, source_validation=None, participants=None, goal_evaluation=None):
    verification = dict(verification or {'status': 'NOT VERIFIED'})
    # A UI text match is a scoped observation, NEVER whole-task acceptance.
    goal = 'PARTIAL' if status == 'partial' else 'NOT VERIFIED'
    if status in {'failed','cancelled','blocked'} or (source_validation or {}).get('status') == 'FAILED':
        goal = 'FAILED'
    if participants and any(s != 'completed' for s in participants.values()):
        goal = 'PARTIAL' if any(s == 'completed' for s in participants.values()) else 'FAILED'
    from core.task_oracle import trusted_evaluation
    host_goal = trusted_evaluation(goal_evaluation)
    if host_goal and status == 'completed' and goal == 'NOT VERIFIED':
        goal = goal_evaluation.verdict
    return {'execution_status': str(status), 'evidence_status': verification.get('status', 'NOT VERIFIED'),
            'evidence_scope': verification.get('scope', ''), 'goal_accepted': False,
            'goal_verdict':goal, 'completion_kind':'goal_verified' if goal == 'VERIFIED' else 'execution_only',
            'goal_evidence':goal_evaluation.summary() if host_goal else None,
            'participants':dict(participants or {}),
            'acceptance_basis': 'Separate explicit acceptance required; model/process completion is insufficient',
            'cleanup_status': (cleanup or {}).get('status', 'not_started')}


def group_execution_status(states):
    """All requested agents must finish; a surviving response is partial, not verified."""
    values = list(states.values())
    if values and all(v == 'completed' for v in values): return 'completed'
    return 'partial' if any(v == 'completed' for v in values) else 'failed'


def stop_summary(reason, verification=None):
    """Short human-facing result; the exact technical reason stays in evidence."""
    value = str(reason).lower()
    if 'foreground' in value or 'user takeover' in value:
        return 'Pencere odağı değiştiği (odak değişti / kullanıcı müdahalesi) için bilgisayar kontrolü güvenle durduruldu.'
    if 'stalled' in value:
        return 'Ajan aynı işlemi sonuçsuz tekrarladığı için görev durduruldu; hedef tamamlanmış sayılmadı.'
    if 'permission' in value:
        return 'İzin reddedildi veya süresi doldu; görev durduruldu.'
    if value == 'cancelled': return 'Görev durduruldu; yeni işlem yapılmayacak.'
    if value == 'completed':
        check = verification or {}
        if check.get('source') == 'host_request_text' and check.get('status') == 'OBSERVED UI CRITERION VERIFIED':
            texts = ', '.join(f"'{t}'" for t in check.get('expected_text') or [])
            return (f'Görev tamamlandı; istediğin {texts} metni Quartz\'ın kendi gözleminde ekranda görüldü. '
                    'Diğer istekler ve kullanıcı kabulü ayrı.')
        return 'Ajan yürütmesi tamamlandı; bu, tüm hedefin doğrulandığı anlamına gelmez.'
    if value == 'partial':
        return 'Görev kısmen yürütüldü; istenen ajanlardan biri tamamlayamadı. Hedef doğrulanmış sayılmadı.'
    if value == 'expired': return 'Görev süresi doldu; kontrol bırakıldı.'
    return 'Görev tamamlanamadı; kontrol bırakıldı. Ayrıntılar hata kaydında.'


def cleanup_step(report, name, action):
    """Attempt every release independently; do not hide or short-circuit errors."""
    try:
        action()
        report['steps'].append({'name': name, 'status': 'completed'})
    except Exception as exc:
        report['steps'].append({'name': name, 'status': 'failed', 'error': str(exc)})
