import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class InstructionBoardTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.instructions_file = Path(self.temp_dir.name) / "instructions.json"
        self.original_file = app_module.INSTRUCTIONS_FILE
        self.original_instructions = app_module.instructions
        self.original_shelters = app_module.shelters
        app_module.INSTRUCTIONS_FILE = str(self.instructions_file)
        app_module.instructions = []
        app_module.shelters = [
            {"id": 1, "name": "片瀬小学校"},
            {"id": 2, "name": "御所見小学校"},
        ]
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.INSTRUCTIONS_FILE = self.original_file
        app_module.instructions = self.original_instructions
        app_module.shelters = self.original_shelters
        self.temp_dir.cleanup()

    def login(self, client=None):
        client = client or self.client
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["username"] = "admin"
        return client

    def valid_form(self, **overrides):
        data = {
            "target": "住民",
            "district": "片瀬",
            "shelter": "片瀬小学校",
            "priority": "高",
            "content": "避難してください",
            "easy_content": "安全な場所へ にげてください",
        }
        data.update(overrides)
        return data

    def test_board_and_mutating_routes_require_login(self):
        response = self.client.get("/board")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

        response = self.client.post("/instructions/1/status", data={"status": "完了"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(app_module.instructions, [])

        response = self.client.post("/instructions/1/publish")
        self.assertEqual(response.status_code, 302)

    def test_board_registers_resident_instruction_and_persists_server_timestamps(self):
        self.login()
        response = self.client.post("/board", data=self.valid_form())

        self.assertEqual(response.status_code, 302)
        self.assertIn("notice=registered", response.headers["Location"])
        saved = json.loads(self.instructions_file.read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["target"], "住民")
        self.assertEqual(saved[0]["district"], "片瀬")
        self.assertEqual(saved[0]["shelter"], "片瀬小学校")
        self.assertEqual(saved[0]["priority"], "高")
        self.assertEqual(saved[0]["status"], "未対応")
        self.assertEqual(saved[0]["created_at"], saved[0]["updated_at"])
        self.assertIsNone(saved[0]["published_at"])
        self.assertNotEqual(saved[0]["created_at"], "クライアント日時")

    def test_resident_requires_easy_japanese_but_internal_targets_do_not(self):
        self.login()
        response = self.client.post("/board", data=self.valid_form(easy_content="   "))
        self.assertEqual(response.status_code, 400)
        self.assertIn("やさしい日本語", response.get_data(as_text=True))
        self.assertEqual(app_module.instructions, [])

        for target in ("職員", "道路管理課"):
            with self.subTest(target=target):
                response = self.client.post(
                    "/board",
                    data=self.valid_form(target=target, easy_content=""),
                )
                self.assertEqual(response.status_code, 302)
        saved = json.loads(self.instructions_file.read_text(encoding="utf-8"))
        self.assertEqual([item["target"] for item in saved], ["職員", "道路管理課"])

    def test_registration_rejects_invalid_choices_and_blank_content(self):
        self.login()
        invalid_forms = (
            self.valid_form(target="管理者"),
            self.valid_form(district="架空地区"),
            self.valid_form(shelter="未登録の避難所"),
            self.valid_form(priority="最優先"),
            self.valid_form(content="   "),
        )
        for data in invalid_forms:
            with self.subTest(data=data):
                response = self.client.post("/board", data=data)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(app_module.instructions, [])

    def test_status_update_persists_and_rejects_invalid_status_and_id(self):
        self.login()
        self.client.post("/board", data=self.valid_form())
        original_updated_at = app_module.instructions[0]["updated_at"]

        response = self.client.post("/instructions/1/status", data={"status": "完了"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(app_module.instructions[0]["status"], "完了")
        self.assertGreaterEqual(
            app_module.instructions[0]["updated_at"],
            original_updated_at,
        )
        persisted = json.loads(self.instructions_file.read_text(encoding="utf-8"))
        self.assertEqual(persisted[0]["status"], "完了")

        response = self.client.post("/instructions/1/status", data={"status": "解除"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/instructions/999/status", data={"status": "完了"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(app_module.instructions[0]["status"], "完了")

    def test_publish_requires_post_and_is_idempotent(self):
        self.login()
        self.client.post("/board", data=self.valid_form())

        response = self.client.get("/instructions/1/publish")
        self.assertEqual(response.status_code, 200)
        self.assertIn("この内容を発信する", response.get_data(as_text=True))
        self.assertIsNone(app_module.instructions[0]["published_at"])

        response = self.client.post("/instructions/1/publish")
        self.assertEqual(response.status_code, 302)
        published_at = app_module.instructions[0]["published_at"]
        self.assertIsNotNone(published_at)

        response = self.client.get("/instructions/1/publish")
        self.assertIn("発信済みです", response.get_data(as_text=True))
        response = self.client.post("/instructions/1/publish")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(app_module.instructions[0]["published_at"], published_at)
        self.assertEqual(len(app_module.get_public_notices()), 1)
        self.assertEqual(
            json.loads(self.instructions_file.read_text(encoding="utf-8"))[0]["published_at"],
            published_at,
        )

    def test_internal_instruction_cannot_be_published(self):
        self.login()
        self.client.post(
            "/board",
            data=self.valid_form(target="職員", easy_content=""),
        )
        response = self.client.get("/instructions/1/publish")
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(app_module.instructions[0]["published_at"])

    def test_failed_publish_save_is_reported_without_showing_published_state(self):
        self.login()
        self.client.post("/board", data=self.valid_form())
        with patch.object(app_module, "save_instructions", side_effect=OSError("disk full")):
            response = self.client.post("/instructions/1/publish")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 500)
        self.assertIn("発信を保存できませんでした", body)
        self.assertNotIn("発信済みです", body)
        self.assertIsNone(app_module.instructions[0]["published_at"])

    def test_public_home_only_shows_published_resident_notices_as_text(self):
        self.login()
        self.client.post("/board", data=self.valid_form(content="<script>alert(1)</script>"))
        self.client.post("/board", data=self.valid_form(target="職員", easy_content=""))

        body = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("緊急のお知らせ", body)

        self.client.post("/instructions/1/publish")
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("緊急のお知らせ", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("やさしい日本語で表示", body)
        self.assertIn("文字を大きくする", body)
        self.assertIn("安全な場所へ にげてください", body)
        self.assertNotIn("内部向け情報", body)

    def test_old_instruction_defaults_to_unpublished_and_status_displays_safely(self):
        app_module.instructions = [{
            "id": 4,
            "target": "住民",
            "content": "旧形式の指示",
            "status": "解除",
            "created_at": "2026年07月14日 18:38",
        }]
        self.login()

        board = self.client.get("/board").get_data(as_text=True)
        self.assertIn("未対応", board)
        self.assertIn("未発信", board)
        self.assertIn("緊急度", board)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertNotIn("旧形式の指示", self.client.get("/").get_data(as_text=True))

    def test_failed_registration_save_is_reported_and_rolled_back(self):
        self.login()
        with patch.object(app_module, "save_instructions", side_effect=OSError("disk full")):
            response = self.client.post("/board", data=self.valid_form())
        self.assertEqual(response.status_code, 500)
        self.assertIn("指示を保存できませんでした", response.get_data(as_text=True))
        self.assertEqual(app_module.instructions, [])

    def test_broadcast_history_is_newest_first(self):
        app_module.instructions = [
            {
                "id": 1,
                "target": "住民",
                "district": "片瀬",
                "content": "古い発信",
                "published_at": "2026-10-01T09:00:00+09:00",
            },
            {
                "id": 2,
                "target": "住民",
                "district": "鵠沼",
                "content": "新しい発信",
                "published_at": "2026-10-02T09:00:00+09:00",
            },
        ]
        self.login()
        body = self.client.get("/broadcast_history").get_data(as_text=True)
        self.assertLess(body.index("新しい発信"), body.index("古い発信"))

    def test_board_newest_sort_button_orders_instructions_by_created_at(self):
        app_module.instructions = [
            {
                "id": 1,
                "target": "職員",
                "content": "古い指示",
                "created_at": "2026-10-01T09:00:00+09:00",
            },
            {
                "id": 2,
                "target": "職員",
                "content": "新しい指示",
                "created_at": "2026-10-02T09:00:00+09:00",
            },
        ]
        self.login()
        response = self.client.get("/board?sort=newest")
        body = response.get_data(as_text=True)
        self.assertIn("新しい順に並び替え", body)
        self.assertLess(body.index("新しい指示"), body.index("古い指示"))


if __name__ == "__main__":
    unittest.main()
