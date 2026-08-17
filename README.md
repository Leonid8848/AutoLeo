# AutoLeo

AutoLeo is a portable Python project with a simple window for adding English word definitions to Lingualeo.

It opens a separate Chrome profile for Lingualeo and connects to it locally. It does not store your Lingualeo login or password.

## What Portable Means Here

This is not an `.exe`.

AutoLeo is a folder you can copy to another Windows computer. On that computer you need:

- Python 3.10 or newer installed;
- internet access on the first run so AutoLeo can install its Python dependency into its own local `.venv` folder;
- Google Chrome installed;
- Lingualeo logged in inside that Chrome profile, or be ready to log in manually on first use.

AutoLeo does not install libraries globally. Everything goes into:

```text
D:\AutoLeo\.venv
```

You normally do not need to touch that folder.

## Chrome Profile

Chrome no longer opens automatically when `Start_AutoLeo.bat` is launched. Use
the `Открыть в Chrome` button in the AutoLeo window when you need it. The button
opens Chrome with remote debugging port `9223` and a separate temporary profile here:

```text
%TEMP%\autoleo-profile
```

If that folder does not exist, Chrome creates a fresh profile. If it already exists,
Chrome reuses the same profile with its cookies, Lingualeo login, and settings.

If Lingualeo asks for login, captcha, or confirmation, do it manually in Chrome, then continue in AutoLeo.

The `Очистить данные браузера` button deletes only this separate profile after
confirmation. Close the AutoLeo Chrome window before clearing it. The next time
you open it, Chrome creates a fresh profile and Lingualeo asks you to sign in again.

## Start AutoLeo

Double-click:

```text
Start_AutoLeo.bat
```

On the first run it will:

1. create `.venv` inside the AutoLeo folder;
2. install the required Python package there;
3. open the AutoLeo window.

After that, the window should open normally.

## Use The Window

1. Click `Открыть в Chrome` and log in to the required Lingualeo account if needed.
2. Click `Загрузить наборы`.
3. AutoLeo will read the available Lingualeo word sets from the current account.
4. Choose the target set from the dropdown.
5. Click `Обзор...`.
6. Choose your `.txt` file with words.
7. Click `Запустить добавление`.
8. Wait for the report in the log area.

The selected set can be any Lingualeo set returned by the account. It is not hardcoded to Oxford 2000.

## TXT Format

One word per line:

```text
sadness — a feeling of being unhappy.
sail — to travel on water in a boat or ship.
to improve — to make something better.
```

Supported separators:

- ` — `
- ` – `
- ` - `
- tab

Blank lines and lines starting with `#` are ignored.

The file can be anywhere: in the AutoLeo folder, on Desktop, in Downloads, etc. The window lets you choose it.

## What AutoLeo Does

For each word, AutoLeo:

1. searches Lingualeo through `GetWords`;
2. filters by exact `wordValue`;
3. adds your English definition to the selected word set;
4. makes your definition the main visible translation;
5. disables old or duplicate translations;
6. resets the word to unlearned;
7. verifies that the word is in the selected set.

Chrome CDP URL by default:

```text
http://127.0.0.1:9223
```

## Command-Line Mode

The GUI is the normal mode, but the old command-line entry point still exists:

```powershell
python AutoLeo.py words.txt --word-set-id 123 --word-set-name "My Word Set"
```

In command-line mode, `--word-set-id` is required. AutoLeo does not assume any
preferred Lingualeo set.

## Project Structure

```text
AutoLeo
├── Start_AutoLeo.bat      # easiest launch
├── AutoLeo_GUI.py         # GUI entry point
├── AutoLeo.py             # command-line entry point
├── requirements.txt
├── README.md
├── autoleo
│   ├── cli.py
│   ├── gui.py
│   ├── lingualeo_client.py
│   ├── models.py
│   └── parser.py
└── examples
    └── words.txt
```

## For AI Agents

Keep this as a Python project. Do not convert it to `.exe` unless the user explicitly asks.

The app intentionally connects to Chrome opened with the `Открыть в Chrome` GUI button at:

```text
http://127.0.0.1:9223
```

Do not automate Lingualeo login. If login, captcha, or confirmation appears, stop and ask the user to handle it manually.

The GUI loads sets dynamically through Lingualeo `GetWords` and uses the returned `listWordSets`. Do not hardcode Oxford 2000 as the only target.

Known-good add/update endpoint:

```http
POST https://api.lingualeo.com/SetWords
```

Use nested `valueList`:

```json
{
  "apiVersion": "1.0.2",
  "op": "actionWithWords {action: add}",
  "data": [
    {
      "action": "add",
      "mode": "0",
      "wordIds": null,
      "wordSetId": 22,
      "valueList": {
        "wordValue": "word",
        "wordSetId": 22,
        "translation": {
          "tr": "English definition"
        }
      }
    }
  ],
  "userData": {
    "nativeLanguage": "lang_id_src"
  }
}
```

For existing words, use `wordIds: [wordId]`, make the new translation main with `new_updateWordAttr`, then reset `learningStatus` to `0`.

When disabling old translations, use:

```json
{
  "id": 123,
  "selected": 0,
  "tr": ""
}
```

Do not use `tr: null`.

Lingualeo search can return substring matches. Always filter by exact `wordValue`.
