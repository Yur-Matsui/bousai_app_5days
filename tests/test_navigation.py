import unittest

import app as app_module


class NavigationTest(unittest.TestCase):
    def test_main_navigation_is_available_on_pages(self):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["username"] = "admin"

        for path in ("/", "/shelter_search", "/shelter_register", "/board", "/search_results"):
            with self.subTest(path=path):
                response = client.get(path)
                body = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn('aria-label="メインメニュー"', body)
                self.assertIn('href="/shelter_search"', body)
                self.assertIn('href="/shelter_register"', body)
                self.assertIn('href="/board"', body)
                self.assertIn('<nav class="page-actions" aria-label="ページ移動">', body)
                self.assertIn('class="page-action page-action-primary" href="/shelter_search">避難所検索へ戻る</a>', body)
                self.assertIn('class="page-action" href="/">トップページへ戻る</a>', body)
                self.assertIn("position: fixed;", body)


if __name__ == "__main__":
    unittest.main()
