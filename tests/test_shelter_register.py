import json
import tempfile
import unittest
from pathlib import Path

import app as app_module


class ShelterRegisterTest(unittest.TestCase):
    def test_shelter_register_post_adds_new_shelter(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_file = Path(tmp_dir) / "shelters.json"
            temp_file.write_text(
                json.dumps([
                    {"id": 1, "name": "御所見小学校"},
                    {"id": 2, "name": "片瀬小学校"}
                ], ensure_ascii=False),
                encoding="utf-8"
            )

            original_data_file = app_module.DATA_FILE
            original_shelters = app_module.shelters.copy()
            try:
                app_module.DATA_FILE = str(temp_file)
                app_module.shelters = json.loads(temp_file.read_text(encoding="utf-8"))

                client = app_module.app.test_client()
                with client.session_transaction() as session:
                    session["logged_in"] = True
                    session["username"] = "admin"

                response = client.post("/shelter_register", data={
                    "name": "新しい避難所",
                    "address": "藤沢市藤沢1-1",
                    "opening_status": "開設中",
                    "capacity": "100",
                    "current_evacuees": "35",
                    "pet_friendly": "yes",
                    "barrier_free": "no",
                })

                self.assertEqual(response.status_code, 200)
                self.assertIn("避難所を登録しました", response.get_data(as_text=True))
                saved = json.loads(temp_file.read_text(encoding="utf-8"))
                self.assertEqual(saved[-1]["name"], "新しい避難所")
                self.assertEqual(saved[-1]["address"], "藤沢市藤沢1-1")
                self.assertEqual(saved[-1]["opening_status"], "開設中")
                self.assertEqual(saved[-1]["capacity"], 100)
                self.assertEqual(saved[-1]["current_evacuees"], 35)
                self.assertIs(saved[-1]["pet_friendly"], True)
                self.assertIs(saved[-1]["barrier_free"], False)
            finally:
                app_module.DATA_FILE = original_data_file
                app_module.shelters = original_shelters

    def test_shelter_register_post_shows_validation_error(self):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["username"] = "admin"

        response = client.post("/shelter_register", data={"name": "   "})

        self.assertEqual(response.status_code, 200)
        self.assertIn("避難所名を入力してください", response.get_data(as_text=True))

    def test_shelter_register_requires_address_and_opening_status(self):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True

        missing_address = client.post("/shelter_register", data={
            "name": "新しい避難所",
            "opening_status": "開設中",
        })
        self.assertIn("住所を入力してください", missing_address.get_data(as_text=True))

        missing_status = client.post("/shelter_register", data={
            "name": "新しい避難所",
            "address": "藤沢市藤沢1-1",
        })
        self.assertIn("開設状況を選択してください", missing_status.get_data(as_text=True))

    def test_shelter_register_validates_capacity_and_evacuee_count(self):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True

        data = {
            "name": "新しい避難所",
            "address": "藤沢市藤沢1-1",
            "opening_status": "開設中",
            "capacity": "0",
            "current_evacuees": "-1",
            "pet_friendly": "yes",
            "barrier_free": "no",
        }
        response = client.post("/shelter_register", data=data)
        self.assertIn("収容人数は1人以上", response.get_data(as_text=True))

        data["capacity"] = "100"
        response = client.post("/shelter_register", data=data)
        self.assertIn("現在の避難者数は0人以上", response.get_data(as_text=True))

        data["current_evacuees"] = "35人"
        response = client.post("/shelter_register", data=data)
        self.assertIn("整数で入力してください", response.get_data(as_text=True))

    def test_search_results_show_registered_fields_in_a_table(self):
        original_shelters = app_module.shelters
        try:
            app_module.shelters = [{
                "id": 1,
                "name": "御所見小学校",
                "address": "藤沢市用田",
                "opening_status": "開設中",
                "capacity": 100,
                "current_evacuees": 35,
                "pet_friendly": True,
                "barrier_free": False,
            }]
            response = app_module.app.test_client().get("/search_results")
            body = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="shelter-result"', body)
            self.assertIn("御所見小学校", body)
            self.assertIn("住所", body)
            self.assertIn("開設状況", body)
            self.assertIn("藤沢市用田", body)
            self.assertIn("開設中", body)
            self.assertIn("収容人数", body)
            self.assertIn("現在の避難者数", body)
            self.assertIn("空きあり（残り65人）", body)
            self.assertIn("availability-available", body)
            self.assertIn("ペット受け入れ", body)
            self.assertIn("バリアフリー設備", body)
            self.assertIn('aria-hidden="true">🐾</span>', body)
            self.assertIn('aria-hidden="true">♿</span>', body)
            self.assertIn("facility-yes", body)
            self.assertIn("facility-no", body)
        finally:
            app_module.shelters = original_shelters

    def test_search_results_mark_full_and_over_capacity_shelters(self):
        original_shelters = app_module.shelters
        try:
            app_module.shelters = [
                {"id": 1, "name": "満員", "capacity": 10, "current_evacuees": 10},
                {"id": 2, "name": "定員超過", "capacity": 10, "current_evacuees": 12},
            ]
            response = app_module.app.test_client().get("/search_results")
            body = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("満員</span>", body)
            self.assertIn("満員（定員超過）", body)
            self.assertEqual(body.count('availability-full">'), 2)
        finally:
            app_module.shelters = original_shelters

    def test_search_results_mark_missing_legacy_fields_as_unregistered(self):
        original_shelters = app_module.shelters
        try:
            app_module.shelters = [
                {"id": 1, "name": "既存の避難所"},
                {"id": 2, "name": "ペット可", "pet_friendly": True, "barrier_free": None},
            ]
            response = app_module.app.test_client().get("/search_results")
            body = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("availability-unknown", body)
            self.assertIn("収容人数", body)
            self.assertIn("現在の避難者数", body)
            self.assertIn("facility-unknown", body)
            self.assertIn("facility-yes", body)
        finally:
            app_module.shelters = original_shelters

    def test_search_results_show_no_matches_message_and_search_again_button(self):
        original_shelters = app_module.shelters
        try:
            app_module.shelters = [{"id": 1, "name": "片瀬小学校", "district": "片瀬"}]
            response = app_module.app.test_client().get("/search_results?district=鵠沼")
            body = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn('role="status"', body)
            self.assertIn("該当する避難所が見つかりません", body)
            self.assertIn("検索条件を変更して、もう一度お試しください。", body)
            self.assertIn('href="/shelter_search">検索条件をクリア</a>', body)
            self.assertNotIn("片瀬小学校", body)
        finally:
            app_module.shelters = original_shelters

    def test_shelter_register_requires_valid_facility_statuses(self):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True

        response = client.post("/shelter_register", data={
            "name": "新しい避難所",
            "address": "藤沢市藤沢1-1",
            "opening_status": "開設中",
            "capacity": "100",
            "current_evacuees": "35",
            "pet_friendly": "maybe",
            "barrier_free": "yes",
        })

        self.assertIn("ペット可とバリアフリーの状況を選択してください", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
