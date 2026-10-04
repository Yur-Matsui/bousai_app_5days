import json
import unittest
from unittest.mock import patch

import app as app_module


class WeatherWarningsTest(unittest.TestCase):
    def test_parse_area_warnings_matches_aomori_city_code(self):
        warning_data = [
            {
                "reportDatetime": "2026-10-04T10:00:00+09:00",
                "warning": {
                    "class20Items": [
                        {
                            "areaCode": "0220100",
                            "kinds": [
                                {"status": "発表", "code": "14"},
                                {"status": "発表警報・注意報はなし", "code": "00"},
                            ],
                        },
                        {
                            "areaCode": "0220200",
                            "kinds": [{"status": "発表", "code": "05"}],
                        },
                    ]
                },
            }
        ]

        warnings, report_time = app_module.parse_area_warnings(warning_data)

        self.assertEqual(app_module.PREFECTURE_CODE, "020000")
        self.assertEqual(app_module.AREA_CODE, "220100")
        self.assertEqual([warning["code"] for warning in warnings], ["14"])
        self.assertEqual(report_time, "2026-10-04T10:00:00+09:00")

    def test_parse_uses_latest_report_instead_of_old_active_warning(self):
        warning_data = [
            {
                "reportDatetime": "2026-10-03T10:00:00+09:00",
                "warning": {
                    "class20Items": [
                        {
                            "areaCode": "0220100",
                            "kinds": [{"status": "発表", "code": "14"}],
                        }
                    ]
                },
            },
            {
                "reportDatetime": "2026-10-04T10:00:00+09:00",
                "warning": {
                    "class20Items": [
                        {
                            "areaCode": "0220100",
                            "kinds": [{"status": "発表警報・注意報はなし"}],
                        }
                    ]
                },
            },
        ]

        warnings, report_time = app_module.parse_area_warnings(warning_data)

        self.assertEqual(warnings, [])
        self.assertEqual(report_time, "2026-10-04T10:00:00+09:00")

    def test_parse_rejects_data_without_aomori_city(self):
        with self.assertRaisesRegex(ValueError, "220100"):
            app_module.parse_area_warnings([
                {
                    "reportDatetime": "2026-10-04T10:00:00+09:00",
                    "warning": {
                        "class20Items": [
                            {
                                "areaCode": "0220200",
                                "kinds": [{"status": "発表警報・注意報はなし"}],
                            }
                        ]
                    },
                }
            ])

    def test_weather_api_uses_aomori_prefecture_data(self):
        warning_data = [
            {
                "reportDatetime": "2026-10-04T10:00:00+09:00",
                "warning": {
                    "class20Items": [
                        {
                            "areaCode": "0220100",
                            "kinds": [{"status": "発表", "code": "14"}],
                        }
                    ]
                },
            }
        ]

        class MockResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(warning_data, ensure_ascii=False).encode("utf-8")

        with patch.object(app_module.urllib.request, "urlopen", return_value=MockResponse()) as urlopen:
            result = app_module.get_weather_warnings()

        urlopen.assert_called_once_with(
            url="https://www.jma.go.jp/bosai/warning/data/r8/020000.json",
            timeout=10,
        )
        self.assertEqual(result["area_name"], "青森市")
        self.assertEqual(result["warnings"][0]["name"], "雷注意報")
        self.assertFalse(result.get("error", False))


if __name__ == "__main__":
    unittest.main()
