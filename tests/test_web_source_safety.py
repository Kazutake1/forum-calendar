"""No-network checks for redirect prevalidation, bounded downloads and JST."""
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import update_events
import jr_walking_web


class FakeResponse:
    def __init__(self, status=200, location=None, body=b"<title>fixture</title>"):
        self.status_code = status
        self.headers = {"Content-Type": "application/octet-stream"}
        if location is not None:
            self.headers["Location"] = location
        self.body = body
        self.closed = False
        self.encoding = None
        self._content = None
        self._content_consumed = False

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError("HTTP error")

    def iter_content(self, size):
        yield self.body


class WebSourceSafetyTests(unittest.TestCase):
    def check_blocked_redirect(self, module, url):
        first = FakeResponse(302, "https://untrusted.example.com/payload")
        requests = []

        def fake_get(target, **kwargs):
            requests.append((target, kwargs))
            self.assertFalse(kwargs.get("allow_redirects"))
            self.assertTrue(kwargs.get("stream"))
            if len(requests) > 1:
                self.fail("Offsite redirect must never be requested")
            return first

        with patch.object(module.requests, "get", side_effect=fake_get):
            with self.assertRaisesRegex(RuntimeError, "許可"):
                (module.get if module is update_events else module._get)(url)
        self.assertEqual(len(requests), 1)
        self.assertTrue(first.closed)

    def test_city_redirect_not_followed_outside_allowed_hosts(self):
        self.check_blocked_redirect(
            update_events, "https://www.city.inazawa.aichi.jp/ica/source")

    def test_jr_redirect_not_followed_outside_jr_host(self):
        self.check_blocked_redirect(
            jr_walking_web, "https://walking.jr-central.co.jp/course/detail/123")

    def test_city_same_host_redirect_can_succeed_without_auto_follow(self):
        redirect = FakeResponse(302, "/ica/current")
        document = FakeResponse(body=b"city calendar page")
        seen = []
        def fake_get(url, **kwargs):
            seen.append(url)
            return [redirect, document][len(seen) - 1]
        with patch.object(update_events.requests, "get", side_effect=fake_get):
            result = update_events.get("https://www.city.inazawa.aichi.jp/ica/old")
        self.assertEqual(
            seen, ["https://www.city.inazawa.aichi.jp/ica/old",
                   "https://www.city.inazawa.aichi.jp/ica/current"])
        self.assertTrue(redirect.closed)
        self.assertEqual(result._content, b"city calendar page")

    def test_jr_same_host_redirect_can_succeed(self):
        redirect = FakeResponse(307, "/course/detail/999")
        document = FakeResponse(body=b"JR station")
        seen = []
        def fake_get(url, **kwargs):
            seen.append(url)
            return [redirect, document][len(seen) - 1]
        with patch.object(jr_walking_web.requests, "get", side_effect=fake_get):
            result = jr_walking_web._get("https://walking.jr-central.co.jp/course/detail/1")
        self.assertEqual(len(seen), 2)
        self.assertTrue(redirect.closed)
        self.assertEqual(result._content, b"JR station")

    def test_invalid_initial_hosts_are_rejected_without_network(self):
        for module, fn, urls in (
            (update_events, update_events.get, (
                "http://www.city.inazawa.aichi.jp/ica/test",
                "https://evil.example.com/fake",
                "https://user@www.city.inazawa.aichi.jp/ica/test")),
            (jr_walking_web, jr_walking_web._get, (
                "http://walking.jr-central.co.jp/course/detail/1",
                "https://evil.example.com/fake",
                "https://person@walking.jr-central.co.jp/course/detail/1")),
        ):
            with patch.object(module.requests, "get") as fake:
                for url in urls:
                    with self.subTest(url=url), self.assertRaises(RuntimeError):
                        fn(url)
                fake.assert_not_called()

    def test_overlarge_responses_close_connection_before_returning(self):
        for module, fn, url in (
            (update_events, update_events.get,
             "https://www.city.inazawa.aichi.jp/ica/test"),
            (jr_walking_web, jr_walking_web._get,
             "https://walking.jr-central.co.jp/course/detail/test"),
        ):
            huge = FakeResponse(body=b"X" * (module.MAX_DOWNLOAD + 1))
            with self.subTest(module=module.__name__), patch.object(
                    module.requests, "get", return_value=huge):
                with self.assertRaises(RuntimeError):
                    fn(url)
                self.assertTrue(huge.closed)

    def test_jst_date_uses_japanese_calendar_across_utc_midnight(self):
        # 2026-10-25 23:30 UTC -> 2026-10-26 08:30 JST.
        real = datetime(2026, 10, 25, 23, 30, tzinfo=timezone.utc)
        with patch.object(update_events, "datetime", wraps=datetime) as mocked:
            mocked.now.return_value = real.astimezone(update_events.JST)
            self.assertEqual(update_events.jst_today(), date(2026, 10, 26))
            self.assertEqual(
                update_events.infer_year_months(
                    "invalid", "https://www.city.inazawa.aichi.jp/archive.pdf"),
                (2026, [10]))


if __name__ == "__main__":
    unittest.main()
