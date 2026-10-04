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

                response = client.post("/shelter_register", data={"name": "新しい避難所"})

                self.assertEqual(response.status_code, 200)
                self.assertIn("避難所を登録しました", response.get_data(as_text=True))
                saved = json.loads(temp_file.read_text(encoding="utf-8"))
                self.assertEqual(saved[-1]["name"], "新しい避難所")
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


if __name__ == "__main__":
    unittest.main()
