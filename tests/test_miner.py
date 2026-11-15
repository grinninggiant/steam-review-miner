import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from steam_review_miner import extract_requests, fetch_reviews, group_requests, main, render_json, render_report


PAGES = json.loads((Path(__file__).parent / "fixtures/pages.json").read_text())


class Response:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.data


class FetchTests(unittest.TestCase):
    def test_cursor_encoding_dedup_and_repeat_termination(self):
        urls = []
        pauses = []

        def open_page(url, timeout):
            urls.append(url)
            return Response({"response": PAGES[len(urls) - 1]})

        fetched, reviews = fetch_reviews(413150, "english", 500, opener=open_page, pause=pauses.append)
        self.assertEqual(fetched, 4)
        self.assertEqual([r["recommendationid"] for r in reviews], ["11", "12", "13"])
        self.assertEqual(len(urls), 2)
        self.assertEqual(pauses, [1])
        queries = [json.loads(parse_qs(urlsplit(url).query)["input_json"][0]) for url in urls]
        self.assertTrue(urls[0].startswith("https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/?"))
        self.assertEqual(queries[1]["cursor"], "page+two/==")
        self.assertNotIn("page+two", urls[1])  # cursor is URL-encoded inside input_json
        self.assertEqual(queries[0], {"appid": 413150, "filter": 1, "num_per_page": 100, "cursor": "*",
                                      "languages": ["english"], "purchase_type": 1})

    def test_empty_page_stops_without_another_request(self):
        calls = []

        def open_page(url, timeout):
            calls.append(url)
            return Response({"response": {"cursor": "next", "reviews": []}})

        self.assertEqual(fetch_reviews(1, opener=open_page, pause=lambda _: None), (0, []))
        self.assertEqual(len(calls), 1)

    def test_missing_response_envelope_is_an_error(self):
        with self.assertRaises(ValueError):
            fetch_reviews(1, opener=lambda url, timeout: Response({}), pause=lambda _: None)


class ReportTests(unittest.TestCase):
    def test_sentence_extraction_and_inventory_cluster(self):
        reviews = [r for page in PAGES for r in page["reviews"]]
        requests = extract_requests(reviews)
        self.assertEqual(len(requests), 4)
        self.assertNotIn("Nice art", " ".join(requests))
        self.assertNotIn("Very fun", " ".join(requests))
        clusters = group_requests(requests)
        self.assertTrue(any("inventory" in key and len(items) == 3 for key, items in clusters.items()))
        self.assertTrue(any("kayıt" in key for key in clusters))

    def test_need_is_not_treated_as_explicit_needs_request(self):
        reviews = [{"review": "You need to relax. The game needs inventory sorting. I wish it had co-op."}]
        self.assertEqual(extract_requests(reviews), ["The game needs inventory sorting.", "I wish it had co-op."])

    def test_cluster_uses_request_clause_not_review_preamble(self):
        groups = group_requests(["Good characterization, but I wish there was more disability representation."])
        self.assertIn("disability", groups)

    def test_generic_adjective_does_not_merge_unrelated_requests(self):
        groups = group_requests([
            "I wish fishing was better.",
            "I wish the husband was better.",
        ])
        self.assertEqual(set(groups), {"fishing", "husband"})

    def test_report_has_counts_short_escaped_quotes_and_no_review_dump(self):
        requests = ["I wish <b>inventory</b> had more slots " + "x" * 160]
        report = render_report(413150, 2, 1, group_requests(requests))
        self.assertIn("413150", report)
        self.assertIn("Çekilen yorum: 2", report)
        self.assertIn("Tekil yorum: 1", report)
        self.assertIn("Örnek sayısı: 1", report)
        self.assertNotIn("<b>", report)
        self.assertTrue(all(len(line.removeprefix("> ")) <= 140 for line in report.splitlines() if line.startswith("> ")))

    def test_quote_keeps_apostrophes_readable(self):
        report = render_report(1, 1, 1, {"inventory": ["I wish it's easier."]})
        self.assertIn("> I wish it's easier.", report)

    def test_cli_writes_report_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            with patch("steam_review_miner.fetch_reviews", return_value=(4, PAGES[0]["reviews"])) as fetch:
                main(["413150", "--lang", "turkish", "--limit", "2", "--out", str(output)])
            fetch.assert_called_once_with(413150, "turkish", 2)
            self.assertIn("## inventory slots", output.read_text(encoding="utf-8"))

    def test_json_has_same_aggregates_short_quotes_and_no_review_dump(self):
        groups = {"inventory slots": ["I wish <b>more</b> slots " + "x" * 160, "b", "c", "d"], "co-op": ["e"]}
        data = json.loads(render_json(413150, 6, 5, groups))
        self.assertEqual((data["appid"], data["fetched"], data["unique"]), (413150, 6, 5))
        self.assertEqual([(c["title"], c["count"]) for c in data["clusters"]], [("inventory slots", 4), ("co-op", 1)])
        self.assertEqual(len(data["clusters"][0]["quotes"]), 3)
        self.assertTrue(all(len(q) <= 140 for c in data["clusters"] for q in c["quotes"]))
        self.assertTrue(data["clusters"][0]["quotes"][0].startswith("I wish <b>more</b>"))

    def test_cli_json_format_writes_json_default_out_without_network(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory), \
                contextlib.redirect_stdout(io.StringIO()):
            with patch("steam_review_miner.fetch_reviews", return_value=(4, PAGES[0]["reviews"])):
                main(["413150", "--format", "json"])
            data = json.loads(Path("report.json").read_text(encoding="utf-8"))
            self.assertFalse(Path("report.md").exists())
        self.assertEqual((data["appid"], data["fetched"]), (413150, 4))
        self.assertIn("inventory slots", [c["title"] for c in data["clusters"]])

    def test_cli_rejects_nonpositive_limit(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["413150", "--limit", "0"])


if __name__ == "__main__":
    unittest.main()
