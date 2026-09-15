from computer_use.browser_checks import (
    ALL_CHECKS, BYPASSED_CHECKS, NO_CONSENT_OPERATIONS, BrowserSecurityPolicy,
    consent_for, denial_text,
)
from computer_use.browser_security import BrowserUseSecurityError

print('checks:', len(ALL_CHECKS))
print('modes:', list(BYPASSED_CHECKS))
print('empty mode bypasses nothing:', BYPASSED_CHECKS[''] == frozenset())
print('local-testing bypasses 10:', len(BYPASSED_CHECKS['disabled-for-local-testing']))
print('gaas bypasses 0:', len(BYPASSED_CHECKS['gaas-browser-environment']))
print('gaas no-consent 4:', len(NO_CONSENT_OPERATIONS['gaas-browser-environment']))

print('--- denial text ---')
print(denial_text('browser-origin-access', origin='https://example.com'))
print(denial_text('check-navigation-url-policy'))
print(denial_text('check-url-site-status', display_url='https://blocked.example'))
print(denial_text('file-upload', origin='https://example.com'))
print(denial_text('full-cdp'))
print(denial_text('raw-cdp-non-http'))
print(denial_text('webmcp-tool-call'))

print('--- consent ---')
print(consent_for('browser-origin-access', origin='https://example.com').message)
print(consent_for('page-asset-download', host='cdn.example').message)
print(consent_for('page-asset-cross-origin-fetch', host='cdn.example').message)
print('nav policy consent is None:', consent_for('check-navigation-url-policy') is None)

print('--- policy gates (empty mode = strictest) ---')
p = BrowserSecurityPolicy()
for label, fn in [
    ('origin', lambda: p.assert_origin_allowed('https://example.com')),
    ('url policy', lambda: p.assert_url_policy('javascript:alert(1)')),
    ('upload', lambda: p.assert_upload_allowed('https://example.com/x')),
    ('download', lambda: p.assert_download_allowed('https://example.com/x')),
    ('full cdp', lambda: p.assert_full_cdp_allowed('https://example.com')),
    ('raw cdp non-http', lambda: p.assert_full_cdp_allowed('about:blank')),
    ('cross-origin asset', lambda: p.assert_page_asset_download_allowed('https://cdn.example/a.png', cross_origin=True)),
]:
    try:
        fn()
        print(f'  {label}: ALLOWED')
    except BrowserUseSecurityError as exc:
        print(f'  {label}: {exc.reason} retryable={exc.retryable}')

p.remember_origin('https://example.com')
p.assert_origin_allowed('https://example.com')
print('  origin after approval: ALLOWED')
print('  same-origin asset: ALLOWED (no exception)')
p.assert_page_asset_download_allowed('https://example.com/a.png', cross_origin=False)

strict = BrowserSecurityPolicy(mode='disabled-for-local-testing')
strict.assert_origin_allowed('https://other.example')
strict.assert_url_policy('javascript:alert(1)')
print('  local-testing mode bypasses origin + url policy: OK')
try:
    BrowserSecurityPolicy(mode='nope')
except ValueError as exc:
    print('  unknown mode rejected:', exc)
