import unittest

import app as app_module


class ShelterSearchTest(unittest.TestCase):
    def setUp(self):
        self.original_shelters = app_module.shelters
        app_module.shelters = [
            {
                "id": 1,
                "name": "御所見小学校",
                "district": "御所見",
                "address": "藤沢市用田",
                "description": "川沿いの避難施設",
                "latitude": 35.4,
                "longitude": 139.4,
                "safety_confirmed": True,
                "safe_for": ["earthquake", "flood"],
                "pets_allowed": True,
                "barrier_free": True,
                "wheelchair_accessible": True,
                "capacity": 100,
                "current_evacuees": 20,
            },
            {
                "id": 2,
                "name": "片瀬小学校",
                "district": "片瀬",
                "address": "藤沢市片瀬",
                "latitude": 35.3,
                "longitude": 139.5,
                "safety_confirmed": False,
                "safe_for": ["earthquake"],
                "pets_allowed": None,
                "barrier_free": False,
                "wheelchair_accessible": False,
            },
            {
                "id": 3,
                "name": "鵠沼会館",
                "district": "鵠沼",
                "address": "藤沢市鵠沼",
                "latitude": "不正座標",
                "longitude": 139.45,
                "safety_confirmed": True,
                "safe_for": ["flood"],
                "pets_allowed": True,
                "barrier_free": True,
                "wheelchair_accessible": False,
            },
            {
                "id": 4,
                "district": "地区未登録",
            },
        ]

    def tearDown(self):
        app_module.shelters = self.original_shelters

    def test_search_page_shows_search_fields_facility_count_and_distinct_districts(self):
        response = app_module.app.test_client().get("/shelter_search")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("避難所検索", body)
        self.assertIn("4施設", body)
        self.assertIn("全施設一覧", body)
        self.assertIn("例：御所見小学校", body)
        self.assertIn("洪水・浸水", body)
        self.assertIn("車いす対応", body)
        self.assertEqual(body.count('value="御所見"'), 1)

    def test_keyword_is_trimmed_case_insensitive_and_searches_description(self):
        response = app_module.app.test_client().get("/search_results?keyword=%20KAWA%20")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("御所見小学校", body)
        self.assertNotIn("片瀬小学校", body)
        self.assertIn('value="KAWA"', body)

    def test_search_conditions_are_combined_and_unknown_safety_is_excluded(self):
        response = app_module.app.test_client().get(
            "/search_results?district=御所見&disaster=flood&pets=on&barrier_free=on&wheelchair=on"
        )
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("御所見小学校", body)
        self.assertNotIn("片瀬小学校", body)
        self.assertIn("洪水・浸水：安全確認済み", body)

        response = app_module.app.test_client().get("/search_results?disaster=earthquake")
        body = response.get_data(as_text=True)
        self.assertIn("御所見小学校", body)
        self.assertNotIn("片瀬小学校", body)

    def test_search_results_show_confirmed_safety_facilities_and_missing_data(self):
        response = app_module.app.test_client().get("/search_results")
        body = response.get_data(as_text=True)
        self.assertIn("検索結果", body)
        self.assertIn("4件", body)
        self.assertIn("安全確認済み：地震、洪水・浸水", body)
        self.assertIn("災害別の安全情報 未確認", body)
        self.assertIn("名称未登録", body)
        self.assertIn("受入可", body)
        self.assertIn("対応なし", body)
        self.assertIn("未確認", body)

    def test_location_search_validates_coordinates_and_sorts_by_distance(self):
        response = app_module.app.test_client().get(
            "/search_results?latitude=35.39&longitude=139.39&radius=10"
        )
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.count("class=\"shelter-result\""), 1)
        self.assertIn("現在地から約", body)
        self.assertNotIn("片瀬小学校", body)
        self.assertNotIn("鵠沼会館", body)

        invalid = app_module.app.test_client().get(
            "/search_results?latitude=91&longitude=0"
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("現在地の座標が正しくありません", invalid.get_data(as_text=True))

        incomplete = app_module.app.test_client().get("/search_results?latitude=35")
        self.assertEqual(incomplete.status_code, 400)
        self.assertIn("緯度と経度を両方", incomplete.get_data(as_text=True))

        no_matches = app_module.app.test_client().get(
            "/search_results?latitude=0&longitude=0&radius=5"
        )
        self.assertIn("座標が未登録の施設は現在地検索に表示できません。", no_matches.get_data(as_text=True))

    def test_invalid_radius_defaults_to_ten_km(self):
        results, conditions, _, error = app_module.filter_shelter_search({
            "radius": "1000",
            "latitude": "35.4",
            "longitude": "139.4",
        })
        self.assertIsNone(error)
        self.assertEqual(conditions["radius"], 10)
        self.assertEqual([item["name"] for item in results], ["御所見小学校"])

    def test_invalid_filter_options_are_rejected(self):
        client = app_module.app.test_client()
        response = client.get("/search_results?disaster=volcano")
        self.assertEqual(response.status_code, 400)
        self.assertIn("災害の種類が正しくありません", response.get_data(as_text=True))

        response = client.get("/search_results?district=架空地区")
        self.assertEqual(response.status_code, 200)
        self.assertIn("該当する避難所が見つかりません", response.get_data(as_text=True))

    def test_all_facilities_ignores_filters_and_has_separate_heading(self):
        response = app_module.app.test_client().get(
            "/all_shelters?keyword=存在しない&disaster=earthquake&pets=on"
        )
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("全施設一覧", body)
        self.assertIn("4件", body)
        self.assertIn("御所見小学校", body)
        self.assertIn("名称未登録", body)
        self.assertNotIn('value="存在しない"', body)

    def test_empty_search_explains_unknown_condition_and_clear_link(self):
        response = app_module.app.test_client().get(
            "/search_results?disaster=tsunami"
        )
        body = response.get_data(as_text=True)
        self.assertIn("該当する避難所が見つかりません", body)
        self.assertIn("未確認の施設は、条件付き検索には含めていません", body)
        self.assertIn("検索条件をクリア", body)

    def test_haversine_distance_is_zero_for_same_point(self):
        self.assertEqual(
            app_module.haversine_km((35.0, 139.0), (35.0, 139.0)),
            0,
        )

    def test_search_page_explains_when_no_shelter_has_district_data(self):
        app_module.shelters = [{"id": 1, "name": "地区情報なし"}]
        body = app_module.app.test_client().get("/shelter_search").get_data(as_text=True)
        self.assertIn("地区情報が登録されていません", body)


if __name__ == "__main__":
    unittest.main()
