# シフト管理表

DjangoとSQLiteで動く、ローカル保存型のシフト管理Webアプリです。

## セットアップ

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

ブラウザで `http://127.0.0.1:8000/` を開くと利用できます。

## 機能

- 月別シフト表
- スタッフ登録
- シフト登録
- シフト編集
- シフト削除
- SQLiteへのローカル保存
