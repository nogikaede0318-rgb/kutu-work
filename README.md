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

## 別のPCで加減項目をリセットする

対象PCのアプリを最新版に更新してください。**対象PCの `db.sqlite3` は開発環境のファイルで上書きしないでください。**
サーバーを停止し、そのPCのアプリフォルダで次を実行します（Windows / PowerShell）。

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py reset_salary_adjustments --from-month 2026-10
```

表示された対象DBを確認して、次で実行します。

```powershell
.venv\Scripts\python.exe manage.py reset_salary_adjustments --from-month 2026-10 --apply
```

変更前のSQLiteは、DBと同じフォルダの `backups` に自動保存されます。
全スタッフの加減項目を2026年10月以降OFF・0円にし、9月以前は保持します。
加減項目の定義は削除しません。必要な月は個人設定から再設定できます。
完了後にサーバーを起動してください。
macOS / Linuxでは `.venv\Scripts\python.exe` を `.venv/bin/python` に置き換えてください。

## 機能一覧

- 月別シフト表
- スタッフ登録
- シフト登録
- シフト編集
- シフト削除
- SQLiteへのローカル保存
