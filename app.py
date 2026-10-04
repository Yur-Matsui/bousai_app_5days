from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from urllib.parse import urlparse, urljoin
from functools import wraps
import json
import math
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# app.py はプロジェクト直下に置く。
# 実体（templates / static / data）は bousai_app/ 配下にあるので、そこを参照する。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'bousai_app')

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, 'templates'),
    static_folder=os.path.join(APP_DIR, 'static'),
)
app.secret_key = 'your-secret-key-here'

# 管理者認証情報
ADMIN_CREDENTIALS = {
    'admin': '123'
}

# ────────────────────────────────
# 気象警報・注意報設定
PREFECTURE_CODE = "020000"  # 青森県

AREA_NAME = "青森市"
AREA_CODE = "220100"

WARNING_URL = (
    f"https://www.jma.go.jp/bosai/warning/data/r8/{PREFECTURE_CODE}.json"
)

JST = timezone(timedelta(hours=9))

# 警報・注意報のコード一覧
WARNING_CODES = {
    "00": "解除",
    "02": "暴風雪警報",
    "03": "レベル3大雨警報",
    "04": "洪水警報",
    "05": "暴風警報",
    "06": "大雪警報",
    "07": "波浪警報",
    "08": "レベル3高潮警報",
    "09": "レベル3土砂災害警報",
    "10": "レベル2大雨注意報",
    "12": "大雪注意報",
    "13": "風雪注意報",
    "14": "雷注意報",
    "15": "強風注意報",
    "16": "波浪注意報",
    "17": "融雪注意報",
    "18": "洪水注意報",
    "19": "レベル2高潮注意報",
    "20": "濃霧注意報",
    "21": "乾燥注意報",
    "22": "なだれ注意報",
    "23": "低温注意報",
    "24": "霜注意報",
    "25": "着氷注意報",
    "26": "着雪注意報",
    "27": "その他の注意報",
    "29": "レベル2土砂災害注意報",
    "32": "暴風雪特別警報",
    "33": "レベル5大雨特別警報",
    "35": "暴風特別警報",
    "36": "大雪特別警報",
    "37": "波浪特別警報",
    "38": "レベル5高潮特別警報",
    "39": "レベル5土砂災害特別警報",
    "43": "レベル4大雨危険警報",
    "48": "レベル4高潮危険警報",
    "49": "レベル4土砂災害危険警報"
}

# ────────────────────────────────
# サンプルデータの読み込み
DATA_FILE = os.path.join(APP_DIR, 'data', 'shelters.json')
INSTRUCTIONS_FILE = os.path.join(APP_DIR, 'data', 'instructions.json')

def load_json(path, default):
    """JSONファイルを読み込む（存在しない・壊れている場合は default を返す）"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

shelters = load_json(DATA_FILE, [])
instructions = load_json(INSTRUCTIONS_FILE, [])

def save_instructions():
    """指示ボードのデータをファイルに保存する"""
    with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(instructions, f, ensure_ascii=False, indent=2)


def save_shelters():
    """避難所データをファイルに保存する"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(shelters, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
# ────────────────────────────────

# ────────────────────────────────
# 認証関連の設定とヘルパー関数
def is_safe_url(target):
    """リダイレクト先URLが安全かどうかチェック"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def login_required(f):
    """認証が必要なページに付けるデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            # 現在のURLをnextパラメータとしてログイン画面にリダイレクト
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_japan_time():
    """日本時間（JST）の現在時刻を取得する"""
    return datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")


INSTRUCTION_TARGETS = ('住民', '職員', '道路管理課')
INSTRUCTION_DISTRICTS = (
    '片瀬', '鵠沼', '辻堂', '村岡', '藤沢', '明治', '善行',
    '六会', '湘南大庭', '湘南台', '長後', '遠藤', '御所見',
)
INSTRUCTION_PRIORITIES = ('高', '中', '低')
INSTRUCTION_STATUSES = ('未対応', '完了')


def instruction_datetime_key(value):
    """指示日時を並び替え可能な日時へ変換する。旧形式・不正値は最古として扱う。"""
    if not isinstance(value, str) or not value:
        return datetime.min.replace(tzinfo=JST)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y年%m月%d日 %H:%M")
        except ValueError:
            return datetime.min.replace(tzinfo=JST)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def display_instruction_time(value):
    if not value:
        return '未登録'
    parsed = instruction_datetime_key(value)
    if parsed == datetime.min.replace(tzinfo=JST):
        return value
    return parsed.strftime("%Y年%m月%d日 %H:%M")


def get_instruction_status(instruction):
    """旧形式の状態を画面上で対応状況に正規化する。"""
    return '完了' if instruction.get('status') == '完了' else '未対応'


def get_public_notices():
    """発信済みの住民向け情報のみを発信日時の新しい順で返す。"""
    return sorted(
        (
            item for item in instructions
            if item.get('target') == '住民' and item.get('published_at')
        ),
        key=lambda item: instruction_datetime_key(item.get('published_at')),
        reverse=True,
    )


def save_instruction_changes(previous):
    """保存に失敗した変更をメモリ上でも取り消し、失敗を呼び出し元へ伝える。"""
    try:
        save_instructions()
    except OSError:
        instructions[:] = previous
        app.logger.exception("指示データの保存に失敗しました")
        raise


def format_report_time(iso_str):
    """気象庁の発表時刻（ISO形式）をJSTの表示用文字列に変換する"""
    if not iso_str:
        return "不明"
    try:
        parsed = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(JST)
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return iso_str


def filter_shelters(district=None):
    """district 指定があれば一致する避難所のみ、なければ全件を返す"""
    return [s for s in shelters if not district or s.get('district') == district]


DISASTER_TYPES = {
    'earthquake': '地震',
    'flood': '洪水・浸水',
    'landslide': '土砂災害',
    'tsunami': '津波',
    'storm_surge': '高潮',
    'large_fire': '大規模火災',
}
SEARCH_RADII = (5, 10, 20, 50)


def valid_coordinates(latitude, longitude):
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def haversine_km(first, second):
    """2点間の球面距離をキロメートルで返す。"""
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    hav = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, hav)))


def shelter_districts():
    return sorted({
        item.get('district').strip()
        for item in shelters
        if isinstance(item.get('district'), str) and item.get('district').strip()
    })


def shelter_equipment_value(shelter, field):
    # pet_friendly は以前の登録画面で利用していた同義のデータ項目。
    if field == 'pets_allowed' and field not in shelter:
        return shelter.get('pet_friendly')
    return shelter.get(field)


def filter_shelter_search(params, all_facilities=False):
    """検索条件を検証し、避難所と画面表示用条件を返す。"""
    conditions = {
        'keyword': params.get('keyword', '').strip(),
        'disaster': params.get('disaster', ''),
        'district': params.get('district', ''),
        'pets': params.get('pets') == 'on',
        'barrier_free': params.get('barrier_free') == 'on',
        'wheelchair': params.get('wheelchair') == 'on',
        'radius': 10,
        'latitude': '',
        'longitude': '',
        'all_facilities': all_facilities,
    }
    error = None
    if conditions['disaster'] and conditions['disaster'] not in DISASTER_TYPES:
        error = '災害の種類が正しくありません。'
    districts = shelter_districts()

    radius_value = params.get('radius', '')
    if radius_value:
        try:
            requested_radius = int(radius_value)
        except (TypeError, ValueError):
            requested_radius = 10
        if requested_radius in SEARCH_RADII:
            conditions['radius'] = requested_radius

    has_lat = params.get('latitude') not in (None, '')
    has_lon = params.get('longitude') not in (None, '')
    origin = None
    if has_lat or has_lon:
        if not has_lat or not has_lon:
            error = '現在地の緯度と経度を両方指定してください。'
        else:
            origin = valid_coordinates(params.get('latitude'), params.get('longitude'))
            if origin is None:
                error = '現在地の座標が正しくありません。位置情報を再取得してください。'
            else:
                conditions['latitude'] = params.get('latitude', '')
                conditions['longitude'] = params.get('longitude', '')

    if all_facilities:
        return list(shelters), conditions, districts, None
    if error:
        return [], conditions, districts, error

    results = []
    for shelter in shelters:
        if conditions['keyword']:
            searchable = ' '.join(
                str(shelter.get(field) or '')
                for field in ('name', 'district', 'address', 'location', 'description')
            ).casefold()
            if conditions['keyword'].casefold() not in searchable:
                continue
        if conditions['district'] and shelter.get('district') != conditions['district']:
            continue
        if conditions['disaster'] and not (
            shelter.get('safety_confirmed') is True
            and isinstance(shelter.get('safe_for'), list)
            and conditions['disaster'] in shelter.get('safe_for')
        ):
            continue
        if conditions['pets'] and shelter_equipment_value(shelter, 'pets_allowed') is not True:
            continue
        if conditions['barrier_free'] and shelter.get('barrier_free') is not True:
            continue
        if conditions['wheelchair'] and shelter.get('wheelchair_accessible') is not True:
            continue

        item = dict(shelter)
        if origin is not None:
            location = valid_coordinates(shelter.get('latitude'), shelter.get('longitude'))
            if location is None:
                continue
            distance = haversine_km(origin, location)
            if distance > conditions['radius']:
                continue
            item['distance_km'] = distance
        results.append(item)

    if origin is not None:
        results.sort(key=lambda item: item['distance_km'])
    return results, conditions, districts, None


def prepare_shelter_results(results):
    """一覧表示用に、定員と避難者数から空き状況を作成する"""
    prepared = []
    for shelter in results:
        item = dict(shelter)
        capacity = shelter.get('capacity')
        evacuees = shelter.get('current_evacuees')
        item['display_capacity'] = capacity if type(capacity) is int and capacity > 0 else None
        item['display_evacuees'] = evacuees if type(evacuees) is int and evacuees >= 0 else None

        if item['display_capacity'] is None or item['display_evacuees'] is None:
            item['availability_label'] = '未登録'
            item['availability_class'] = 'unknown'
        elif evacuees >= capacity:
            item['availability_label'] = '満員（定員超過）' if evacuees > capacity else '満員'
            item['availability_class'] = 'full'
        else:
            item['availability_label'] = f'空きあり（残り{capacity - evacuees}人）'
            item['availability_class'] = 'available'

        for field in ('pet_friendly', 'barrier_free'):
            value = shelter.get(field)
            if value is True:
                item[f'{field}_label'] = 'あり'
                item[f'{field}_class'] = 'yes'
            elif value is False:
                item[f'{field}_label'] = 'なし'
                item[f'{field}_class'] = 'no'
            else:
                item[f'{field}_label'] = '未登録'
                item[f'{field}_class'] = 'unknown'

        item['search_pets_value'] = shelter_equipment_value(shelter, 'pets_allowed')
        item['search_barrier_free_value'] = shelter.get('barrier_free')
        item['search_wheelchair_value'] = shelter.get('wheelchair_accessible')
        if shelter.get('safety_confirmed') is True and isinstance(shelter.get('safe_for'), list):
            item['safe_for_labels'] = [
                DISASTER_TYPES.get(code, str(code))
                for code in shelter['safe_for']
                if isinstance(code, str)
            ]
        else:
            item['safe_for_labels'] = []
        prepared.append(item)
    return prepared


def parse_area_warnings(warning_data):
    """気象庁の新形式JSONから対象市区町村の最新状態を抽出する"""
    if not isinstance(warning_data, list):
        raise ValueError("気象庁の警報・注意報データが新形式の配列ではありません")

    area_reports = []

    for report in warning_data:
        if not isinstance(report, dict):
            continue

        report_datetime = report.get("reportDatetime")
        if not isinstance(report_datetime, str) or not report_datetime:
            continue

        warning = report.get("warning")
        if not isinstance(warning, dict):
            continue

        class20_items = warning.get("class20Items", [])
        if not isinstance(class20_items, list):
            continue

        area = next(
            (
                item for item in class20_items
                if isinstance(item, dict)
                and str(item.get("areaCode", "")).lstrip("0") == AREA_CODE
            ),
            None
        )
        if area:
            try:
                parsed_datetime = datetime.fromisoformat(
                    report_datetime.replace("Z", "+00:00")
                )
            except ValueError:
                continue
            area_reports.append((parsed_datetime, report_datetime, area))

    if not area_reports:
        raise ValueError(
            f"気象庁のデータに対象地域コード {AREA_CODE} がありません"
        )

    _, latest_report_datetime, latest_area = max(
        area_reports,
        key=lambda entry: entry[0].astimezone(timezone.utc)
        if entry[0].tzinfo
        else entry[0].replace(tzinfo=JST).astimezone(timezone.utc)
    )

    kinds = latest_area.get("kinds", [])
    if not isinstance(kinds, list) or not kinds:
        raise ValueError("最新の気象庁データに警報・注意報一覧がありません")

    warnings = []
    for kind in kinds:
        if not isinstance(kind, dict):
            continue

        status = kind.get("status", "")
        code = kind.get("code", "")
        if status not in ("発表", "継続") or not code:
            continue

        warnings.append({
            "name": WARNING_CODES.get(
                code,
                f"不明な警報・注意報 (コード: {code})"
            ),
            "code": code,
            "status": status
        })

    return warnings, latest_report_datetime


def get_weather_warnings():
    """対象市区町村の警報・注意報を取得する"""
    try:
        # 青森県の新形式（令和8年～）警報・注意報データを取得
        with urllib.request.urlopen(url=WARNING_URL, timeout=10) as res:
            warning_data = json.loads(res.read())

        warnings, report_datetime = parse_area_warnings(warning_data)

        return {
            "area_name": AREA_NAME,
            "warnings": warnings,
            "report_time": format_report_time(report_datetime),
            "last_fetch_time": get_japan_time()
        }

    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        app.logger.exception(
            "青森市の気象警報・注意報取得に失敗しました (URL: %s)",
            WARNING_URL
        )
        return {
            "area_name": AREA_NAME,
            "warnings": [],
            "report_time": "取得失敗",
            "last_fetch_time": get_japan_time(),
            "error": True,
            "error_message": "気象庁のデータを取得できませんでした。時間をおいて再度お試しください。"
        }


# トップページ：templates/index.html を返す（住民向け指示も表示する）
@app.route('/')
def index():
    resident_notices = get_public_notices()
    return render_template(
        'index.html',
        resident_notices=resident_notices,
        display_time=display_instruction_time,
    )

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    # リダイレクト先を取得（デフォルトは避難所登録画面）
    next_url = request.args.get('next') or request.form.get('next')

    # 安全でないURLの場合はデフォルトページにリダイレクト
    if not next_url or not is_safe_url(next_url):
        next_url = url_for('shelter_register')

    if request.method == 'POST':
        password = request.form.get('password', '').strip()

        # 認証チェック
        username = next(
            (name for name, registered_password in ADMIN_CREDENTIALS.items()
             if registered_password == password),
            None
        )
        if username:
            session['logged_in'] = True
            session['username'] = username
            # ログイン成功後は指定されたページにリダイレクト
            return redirect(next_url)
        return render_template('login.html', error=True, message="パスワードが正しくありません。", next=next_url)

    # ログイン済みの場合は指定されたページにリダイレクト
    if session.get('logged_in'):
        return redirect(next_url)

    return render_template('login.html', next=next_url)

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# 避難所登録ページ
@app.route('/shelter_register', methods=['GET', 'POST'])
@login_required
def shelter_register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        address = request.form.get('address', '').strip()
        opening_status = request.form.get('opening_status', '').strip()
        capacity_value = request.form.get('capacity', '').strip()
        evacuees_value = request.form.get('current_evacuees', '').strip()
        pet_friendly_value = request.form.get('pet_friendly', '')
        barrier_free_value = request.form.get('barrier_free', '')
        if not name:
            return render_template('shelter_register.html', error=True, message='避難所名を入力してください。')
        if not address:
            return render_template('shelter_register.html', error=True, message='住所を入力してください。')
        if opening_status not in ('開設中', '未開設'):
            return render_template('shelter_register.html', error=True, message='開設状況を選択してください。')
        facility_values = {'yes': True, 'no': False, 'unknown': None}
        if pet_friendly_value not in facility_values or barrier_free_value not in facility_values:
            return render_template('shelter_register.html', error=True, message='ペット可とバリアフリーの状況を選択してください。')
        try:
            capacity = int(capacity_value)
            current_evacuees = int(evacuees_value)
        except ValueError:
            return render_template('shelter_register.html', error=True, message='収容人数と現在の避難者数は整数で入力してください。')
        if capacity <= 0:
            return render_template('shelter_register.html', error=True, message='収容人数は1人以上で入力してください。')
        if current_evacuees < 0:
            return render_template('shelter_register.html', error=True, message='現在の避難者数は0人以上で入力してください。')

        new_id = max((s.get('id', 0) for s in shelters), default=0) + 1
        shelters.append({
            'id': new_id,
            'name': name,
            'address': address,
            'opening_status': opening_status,
            'capacity': capacity,
            'current_evacuees': current_evacuees,
            'pet_friendly': facility_values[pet_friendly_value],
            'barrier_free': facility_values[barrier_free_value],
        })
        save_shelters()
        return render_template('shelter_register.html', success=True, message='避難所を登録しました。')

    return render_template('shelter_register.html')

# 避難所検索ページ
@app.route('/shelter_search')
def shelter_search():
    return render_template(
        'shelter_search.html',
        districts=shelter_districts(),
        facility_count=len(shelters),
        disaster_types=DISASTER_TYPES,
        conditions={
            'keyword': '',
            'disaster': '',
            'district': '',
            'pets': False,
            'barrier_free': False,
            'wheelchair': False,
            'radius': 10,
            'latitude': '',
            'longitude': '',
        },
    )

# 全施設一覧ページ
@app.route('/all_shelters')
def all_shelters():
    results, conditions, districts, error = filter_shelter_search(
        {},
        all_facilities=True,
    )
    return render_template(
        'search_results.html',
        results=prepare_shelter_results(results),
        conditions=conditions,
        districts=districts,
        disaster_types=DISASTER_TYPES,
        heading='全施設一覧',
        all_facilities=True,
        error=error,
        no_results_reason='',
    )


# 指示ボード：指示の登録、対応状況の管理、発信履歴の確認を行う
@app.route('/board', methods=['GET', 'POST'])
@login_required
def board():
    form_values = request.form.to_dict() if request.method == 'POST' else {}
    error_message = None
    status_code = 200

    if request.method == 'POST':
        target = request.form.get('target', '')
        district = request.form.get('district', '')
        shelter_name = request.form.get('shelter', '')
        priority = request.form.get('priority', '')
        content = request.form.get('content', '').strip()
        easy_content = request.form.get('easy_content', '').strip()
        shelter_names = {item.get('name') for item in shelters if item.get('name')}

        if target not in INSTRUCTION_TARGETS:
            error_message = '宛先を選択してください。'
        elif district not in INSTRUCTION_DISTRICTS:
            error_message = '対象地区を選択してください。'
        elif shelter_name and shelter_name not in shelter_names:
            error_message = '登録済みの避難先を選択してください。'
        elif priority not in INSTRUCTION_PRIORITIES:
            error_message = '緊急度を選択してください。'
        elif not content:
            error_message = '指示内容を入力してください。'
        elif target == '住民' and not easy_content:
            error_message = '住民向けの指示には、やさしい日本語での内容が必要です。'

        if error_message:
            status_code = 400
        else:
            numeric_ids = [
                item.get('id') for item in instructions
                if type(item.get('id')) is int and item.get('id') >= 0
            ]
            now = datetime.now(JST).isoformat(timespec='microseconds')
            new_instruction = {
                'id': max(numeric_ids, default=0) + 1,
                'target': target,
                'district': district,
                'shelter': shelter_name,
                'priority': priority,
                'content': content,
                'easy_content': easy_content,
                'status': '未対応',
                'created_at': now,
                'updated_at': now,
                'published_at': None,
            }
            previous = [dict(item) for item in instructions]
            instructions.append(new_instruction)
            try:
                save_instruction_changes(previous)
            except OSError:
                error_message = '指示を保存できませんでした。時間をおいて再度お試しください。'
                status_code = 500
            else:
                return redirect(url_for('board', notice='registered', sort='newest'))

    board_instructions = list(instructions)
    if request.args.get('sort') == 'newest':
        board_instructions.sort(
            key=lambda item: instruction_datetime_key(item.get('created_at')),
            reverse=True,
        )
    history = get_public_notices()
    notices = {
        'registered': '指示を登録しました。',
        'updated': '対応状況を更新しました。',
        'published': '住民向け情報を発信しました。',
    }
    return render_template(
        'board.html',
        instructions=board_instructions,
        history=history,
        shelters=sorted(shelters, key=lambda item: item.get('name') or ''),
        targets=INSTRUCTION_TARGETS,
        districts=INSTRUCTION_DISTRICTS,
        priorities=INSTRUCTION_PRIORITIES,
        statuses=INSTRUCTION_STATUSES,
        form_values=form_values,
        error_message=error_message,
        notice=notices.get(request.args.get('notice')),
        current_time=get_japan_time(),
        display_time=display_instruction_time,
        get_status=get_instruction_status,
    ), status_code


@app.route('/instructions/<int:instruction_id>/status', methods=['POST'])
@login_required
def update_instruction_status(instruction_id):
    requested_status = request.form.get('status', '')
    if requested_status not in INSTRUCTION_STATUSES:
        return '不正な対応状況です。', 400

    instruction = next(
        (item for item in instructions if str(item.get('id')) == str(instruction_id)),
        None,
    )
    if instruction is None:
        return '指示が見つかりません。', 404

    previous = [dict(item) for item in instructions]
    instruction['status'] = requested_status
    instruction['updated_at'] = datetime.now(JST).isoformat(timespec='microseconds')
    try:
        save_instruction_changes(previous)
    except OSError:
        return '対応状況を保存できませんでした。時間をおいて再度お試しください。', 500
    return redirect(url_for('board', notice='updated'))


@app.route('/instructions/<int:instruction_id>/publish', methods=['GET', 'POST'])
@login_required
def publish_instruction(instruction_id):
    instruction = next(
        (
            item for item in instructions
            if str(item.get('id')) == str(instruction_id)
            and item.get('target') == '住民'
        ),
        None,
    )
    if instruction is None:
        return '住民向け指示が見つかりません。', 404

    if request.method == 'POST':
        if instruction.get('published_at'):
            return redirect(url_for('publish_instruction', instruction_id=instruction_id))
        previous = [dict(item) for item in instructions]
        instruction['published_at'] = datetime.now(JST).isoformat(timespec='microseconds')
        instruction['updated_at'] = instruction['published_at']
        try:
            save_instruction_changes(previous)
        except OSError:
            instruction = next(
                item for item in instructions
                if str(item.get('id')) == str(instruction_id)
                and item.get('target') == '住民'
            )
            return render_template(
                'publish_instruction.html',
                instruction=instruction,
                error_message='発信を保存できませんでした。時間をおいて再度お試しください。',
            ), 500
        return redirect(url_for('board', notice='published'))

    return render_template('publish_instruction.html', instruction=instruction)


@app.route('/broadcast_history')
@login_required
def broadcast_history():
    return render_template(
        'broadcast_history.html',
        history=get_public_notices(),
        display_time=display_instruction_time,
    )

# 検索結果ページ：templates/search_results.html を返す
@app.route('/search_results')
def search_results():
    results, conditions, districts, error = filter_shelter_search(request.args)
    has_condition = any((
        conditions['keyword'],
        conditions['disaster'],
        conditions['district'],
        conditions['pets'],
        conditions['barrier_free'],
        conditions['wheelchair'],
        conditions['latitude'],
    ))
    no_results_reason = ''
    if not results and error is None:
        if conditions['latitude']:
            no_results_reason = (
                '指定した範囲内に条件を満たす避難所がありません。'
                '座標が未登録の施設は現在地検索に表示できません。'
            )
        elif conditions['disaster'] or conditions['pets'] or conditions['barrier_free'] or conditions['wheelchair']:
            no_results_reason = (
                '条件を満たす施設がありません。安全性や設備が未確認の施設は、'
                '条件付き検索には含めていません。'
            )
        elif has_condition:
            no_results_reason = 'キーワードや検索条件を変更して、もう一度お試しください。'
        else:
            no_results_reason = '現在、登録されている避難所はありません。'
    return render_template(
        'search_results.html',
        results=prepare_shelter_results(results),
        conditions=conditions,
        districts=districts,
        disaster_types=DISASTER_TYPES,
        heading='検索結果',
        all_facilities=False,
        error=error,
        no_results_reason=no_results_reason,
    ), 400 if error else 200

# JSON API：/shelters?district=地区名
@app.route('/shelters', methods=['GET'])
def get_shelters():
    results = filter_shelters(request.args.get('district'))

    if not results:
        # 見つからなければエラー JSON を返す
        return jsonify({'error': 'No shelters found'}), 404

    # 見つかったらリストを JSON で返す
    return jsonify(results)

# 気象警報・注意報API
@app.route('/api/weather_warnings')
def api_weather_warnings():
    """気象警報・注意報をJSON形式で返すAPI"""
    return jsonify(get_weather_warnings())

if __name__ == '__main__':
    app.run(debug=True, port=5000)
