import json
import sys

from app import run_browser_session_diagnostics


def main():
    test_url = sys.argv[1] if len(sys.argv) > 1 else 'http://xhslink.com/o/A89wBXex9Gv'
    platform = sys.argv[2] if len(sys.argv) > 2 else 'xiaohongshu'
    browser = sys.argv[3] if len(sys.argv) > 3 else None
    profile = sys.argv[4] if len(sys.argv) > 4 else None
    cookie_file = sys.argv[5] if len(sys.argv) > 5 else None
    result = run_browser_session_diagnostics(
        test_url=test_url,
        platform=platform,
        browser_override=browser,
        profile_override=profile,
        cookie_file_override=cookie_file,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('conclusion', {}).get('status') == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
