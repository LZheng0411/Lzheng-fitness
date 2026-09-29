"""Anonymous source-packet checks for report freshness and evidence ranges."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import distill_report as report


class ReportChecks(unittest.TestCase):
    def test_report_requires_content_current_source_and_valid_time(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            packet = root / "packet"
            packet.mkdir()
            transcript = {"source_id": "douyin:123456789", "segments": [
                {"start": 1.0, "end": 3.0, "text": "示例讲解内容"}]}
            raw = json.dumps(transcript, ensure_ascii=False).encode("utf-8")
            (packet / "transcript.json").write_bytes(raw)
            (packet / "manifest.json").write_text(json.dumps({
                "question": "怎样理解示例？", "source": {"source_id": "douyin:123456789",
                "original_url": "https://www.douyin.com/video/123456789"},
                "transcript_sha256": hashlib.sha256(raw).hexdigest(),
            }, ensure_ascii=False), encoding="utf-8")
            (packet / "SOURCE_PACKET.md").write_text("匿名来源包", encoding="utf-8")
            draft = root / "report.md"
            report.init(packet, draft)
            with self.assertRaisesRegex(ValueError, "unfinished"):
                report.validate(packet, draft)
            body = draft.read_text(encoding="utf-8")
            body = body.replace("[待填写]", "具体内容已核对，仍需由 Agent 审查事实与画面。")
            draft.write_text(body, encoding="utf-8")
            report.validate(packet, draft)
            draft.write_text(body.replace("[00:01.000–00:03.000]", "[00:05.000–00:06.000]"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside transcript"):
                report.validate(packet, draft)
            draft.write_text(body, encoding="utf-8")
            (packet / "SOURCE_PACKET.md").write_text("材料已变化", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale"):
                report.validate(packet, draft)


if __name__ == "__main__":
    unittest.main()
