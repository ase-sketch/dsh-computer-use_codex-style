from computer_use.browser_security import (
    REASONS, BrowserUseSecurityError, approval_failure, full_cdp_consent, history_consent,
    origin_consent, upload_consent,
)

print('reasons:', len(REASONS))
print('retryable:', sorted(r for r, (_, t) in REASONS.items() if t))
print('origin  :', origin_consent('https://example.com').message)
print('history :', history_consent().message)
print('upload  :', upload_consent('https://example.com').message)
cdp = full_cdp_consent('https://example.com')
print('cdp     :', cdp.message, '| risk:', cdp.risk_level, '| full_cdp:', cdp.full_cdp_access)
e = BrowserUseSecurityError('site_status_blocked', 'blocked.example is not permitted.', '')
print('blocked retryable:', e.retryable, '| name:', e.name)
print('non-retryable wrapper ok:', 'must not attempt to achieve the same outcome via workaround' in str(e))
e2 = BrowserUseSecurityError('site_status_unavailable', 'status check failed', '')
print('unavailable retryable:', e2.retryable)
print('retryable wrapper ok:', 'may retry after the issue is resolved' in str(e2))
print('approval sentence:', approval_failure('read your browsing history', 'user_decision'))
try:
    BrowserUseSecurityError('nope')
except ValueError as exc:
    print('unknown reason rejected:', exc)
