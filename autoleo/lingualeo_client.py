from __future__ import annotations

import time
from typing import TYPE_CHECKING
from typing import Any

from .models import Verification, WordAction, WordEntry, WordResult, WordSet

if TYPE_CHECKING:
    from playwright.sync_api import Page


DEFAULT_CDP_URL = "http://127.0.0.1:9223"
DEFAULT_DICTIONARY_URL = "https://lingualeo.com/ru/dictionary"


ATTR_LIST = {
    "association": "as",
    "combinedTranslation": "trc",
    "created": "cd",
    "id": "id",
    "learningStatus": "ls",
    "listWordSets": "listWordSets",
    "origin": "wo",
    "picture": "pic",
    "progress": "pi",
    "pronunciation": "pron",
    "relatedWords": "rw",
    "speechPartId": "pid",
    "trainings": "trainings",
    "transcription": "scr",
    "translations": "trs",
    "wordLemmaId": "lid",
    "wordLemmaValue": "lwd",
    "wordSets": "ws",
    "wordType": "wt",
    "wordValue": "wd",
}


class LingualeoClient:
    def __init__(
        self,
        cdp_url: str = DEFAULT_CDP_URL,
        word_set_id: int | None = None,
        word_set_name: str | None = None,
        dictionary_url: str | None = None,
        pause_seconds: float = 0.2,
    ) -> None:
        self.cdp_url = cdp_url
        self.word_set_id = word_set_id
        self.word_set_name = word_set_name or ""
        self.dictionary_url = dictionary_url or (
            self._dictionary_url_for(word_set_id) if word_set_id is not None else DEFAULT_DICTIONARY_URL
        )
        self.pause_seconds = pause_seconds
        self._playwright = None
        self._browser = None
        self._page: Page | None = None

    def __enter__(self) -> "LingualeoClient":
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install -r requirements.txt"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)
        self._page = self._select_page()
        self._page.goto(self.dictionary_url, wait_until="domcontentloaded", timeout=30_000)
        self._assert_authorized()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("LingualeoClient is not connected.")
        return self._page

    def process_entry(self, entry: WordEntry) -> WordResult:
        try:
            before = self.find_exact_word(entry.word)
            existed = before is not None

            if before is not None and self._word_matches(before, entry):
                self._reset_learning_status(self._word_id(before))
                final_word = self._verify_with_refresh(entry, self._word_id(before))
                return WordResult(
                    entry=entry,
                    action=WordAction.ALREADY_OK,
                    word_id=self._word_id(final_word),
                    verification=self._build_verification(final_word, entry),
                    raw_word=final_word,
                )

            word_id = self._word_id(before) if before is not None else None
            add_response = self._add_translation(entry, word_id=word_id)
            added_word = self._word_from_set_words(add_response)
            word_id = word_id or self._word_id(added_word)

            translations = list((added_word or {}).get("translations") or [])
            target_translation = self._find_target_translation(translations, entry.definition)
            disabled_count = 0

            if target_translation is not None and word_id is not None:
                self._make_translation_main(word_id, target_translation["id"])

            kept_target = False
            for translation in translations:
                translation_id = translation.get("id")
                translation_text = translation.get("tr")
                is_target = translation_text == entry.definition
                if is_target and not kept_target and translation_id == (target_translation or {}).get("id"):
                    kept_target = True
                    continue
                if translation_id is not None:
                    self._disable_translation(word_id, translation_id)
                    disabled_count += 1

            if word_id is not None:
                self._reset_learning_status(word_id)

            final_word = self._verify_with_refresh(entry, word_id)

            if final_word is not None and not self._in_word_set(final_word):
                final_word = self._repair_word_set_membership(entry, word_id)

            final_word = self._remove_duplicate_target_translations(entry, final_word)
            verification = self._build_verification(final_word, entry)

            return WordResult(
                entry=entry,
                action=WordAction.UPDATED if existed else WordAction.ADDED,
                word_id=self._word_id(final_word) or word_id,
                disabled_translations=disabled_count,
                verification=verification,
                raw_word=final_word,
            )
        except Exception as exc:
            return WordResult(entry=entry, action=WordAction.FAILED, error=str(exc))

    def find_exact_word(self, word: str) -> dict[str, Any] | None:
        response = self._get_words(search=word)
        words = self._extract_words(response)
        return next((item for item in words if item.get("wordValue") == word), None)

    def get_word_by_id(self, word_id: int) -> dict[str, Any] | None:
        response = self._get_words_by_ids([word_id])
        words = self._extract_words(response)
        return words[0] if words else None

    def refresh_dictionary_page(self) -> None:
        self.page.goto(self.dictionary_url, wait_until="domcontentloaded", timeout=30_000)
        self.page.reload(wait_until="domcontentloaded", timeout=30_000)

    def list_word_sets(self) -> list[WordSet]:
        response = self._get_words(search="")
        raw_sets = response.get("listWordSets") or []
        word_sets: list[WordSet] = []
        seen_ids: set[int] = set()

        for item in raw_sets:
            set_id = item.get("id")
            name = item.get("name")
            if set_id is None or not name or set_id in seen_ids:
                continue
            seen_ids.add(set_id)
            word_sets.append(WordSet(id=int(set_id), name=str(name)))

        return sorted(word_sets, key=lambda item: item.name.casefold())

    def _select_page(self) -> Page:
        pages = [page for context in self._browser.contexts for page in context.pages]
        for page in pages:
            if "lingualeo.com" in page.url:
                return page
        if pages:
            return pages[0]
        return self._browser.contexts[0].new_page()

    @staticmethod
    def _dictionary_url_for(word_set_id: int) -> str:
        return f"https://lingualeo.com/ru/dictionary/vocabulary/{word_set_id}"

    def _assert_authorized(self) -> None:
        response = self._get_words(search="")
        status = response.get("status")
        if status != "ok":
            raise RuntimeError(
                "Lingualeo API did not return status=ok. Open Chrome, log in manually, "
                "then run AutoLeo again."
            )

    def _api_post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        result = self.page.evaluate(
            """
            async ({ endpoint, body }) => {
                const response = await fetch(`https://api.lingualeo.com/${endpoint}`, {
                    method: "POST",
                    credentials: "include",
                    headers: { "content-type": "application/json" },
                    body: JSON.stringify(body),
                });
                const text = await response.text();
                let json;
                try {
                    json = JSON.parse(text);
                } catch {
                    json = { raw: text };
                }
                return { ok: response.ok, status: response.status, json };
            }
            """,
            {"endpoint": endpoint, "body": body},
        )
        if not result["ok"]:
            raise RuntimeError(f"{endpoint} HTTP {result['status']}: {result['json']}")
        json_body = result["json"]
        if json_body.get("status") not in (None, "ok"):
            raise RuntimeError(f"{endpoint} returned status={json_body.get('status')}: {json_body}")
        return json_body

    def _get_words(self, search: str) -> dict[str, Any]:
        body = {
            "apiVersion": "1.0.1",
            "attrList": ATTR_LIST,
            "category": "",
            "dateGroup": "start",
            "mode": "basic",
            "perPage": 30,
            "status": "",
            "offset": None,
            "search": search,
            "training": None,
        }
        if self.word_set_id is not None:
            body["wordSetId"] = self.word_set_id
        return self._api_post("GetWords", body)

    def _get_words_by_ids(self, word_ids: list[int]) -> dict[str, Any]:
        body = {
            "apiVersion": "1.0.1",
            "attrList": ATTR_LIST,
            "mode": "basic",
            "wordIds": word_ids,
        }
        if self.word_set_id is not None:
            body["wordSetId"] = self.word_set_id
        return self._api_post("GetWords", body)

    def _add_translation(self, entry: WordEntry, word_id: int | None) -> dict[str, Any]:
        word_set_id = self._require_word_set_id()
        return self._set_words(
            {
                "apiVersion": "1.0.2",
                "op": "actionWithWords {action: add}",
                "data": [
                    {
                        "action": "add",
                        "mode": "0",
                        "wordIds": [word_id] if word_id is not None else None,
                        "wordSetId": word_set_id,
                        "valueList": {
                            "wordValue": entry.word,
                            "wordSetId": word_set_id,
                            "translation": {"tr": entry.definition},
                        },
                    }
                ],
                "userData": {"nativeLanguage": "lang_id_src"},
            }
        )

    def _set_words(self, body: dict[str, Any]) -> dict[str, Any]:
        response = self._api_post("SetWords", body)
        time.sleep(self.pause_seconds)
        return response

    def _make_translation_main(self, word_id: int, translation_id: int) -> None:
        word_set_id = self._require_word_set_id()
        self._set_words(
            {
                "apiVersion": "1.0.2",
                "op": "new_updateWordAttr",
                "data": [
                    {
                        "action": "update",
                        "mode": "0",
                        "wordIds": [word_id],
                        "wordSetId": word_set_id,
                        "valueList": {
                            "translation": {
                                "id": translation_id,
                                "selected": 1,
                                "main": 1,
                            }
                        },
                    }
                ],
                "userData": {"nativeLanguage": "lang_id_src"},
            }
        )

    def _disable_translation(self, word_id: int | None, translation_id: int) -> None:
        if word_id is None:
            raise RuntimeError("Cannot disable translation without a word id.")
        word_set_id = self._require_word_set_id()
        self._set_words(
            {
                "apiVersion": "1.0.2",
                "op": "new_updateWordAttr",
                "data": [
                    {
                        "action": "update",
                        "mode": "0",
                        "wordIds": [word_id],
                        "wordSetId": word_set_id,
                        "valueList": {
                            "translation": {
                                "id": translation_id,
                                "selected": 0,
                                "tr": "",
                            }
                        },
                    }
                ],
                "userData": {"nativeLanguage": "lang_id_src"},
            }
        )

    def _reset_learning_status(self, word_id: int | None) -> None:
        if word_id is None:
            raise RuntimeError("Cannot reset learning status without a word id.")
        word_set_id = self._require_word_set_id()
        self._set_words(
            {
                "apiVersion": "1.0.2",
                "op": "new_updateWordAttr",
                "data": [
                    {
                        "action": "update",
                        "mode": "learning",
                        "wordSetId": word_set_id,
                        "wordIds": [word_id],
                        "valueList": {"learningStatus": 0},
                    }
                ],
                "userData": {"nativeLanguage": "lang_id_src"},
            }
        )

    def _verify_with_refresh(self, entry: WordEntry, word_id: int | None) -> dict[str, Any] | None:
        final_word = None
        for attempt in range(3):
            final_word = self.get_word_by_id(word_id) if word_id is not None else self.find_exact_word(entry.word)
            if final_word is not None and self._build_verification(final_word, entry).ok:
                return final_word

            if attempt < 2:
                self.page.reload(wait_until="domcontentloaded", timeout=30_000)
                time.sleep(1 + attempt)

        return final_word

    def _repair_word_set_membership(
        self, entry: WordEntry, word_id: int | None
    ) -> dict[str, Any] | None:
        if word_id is None:
            return None

        self._add_translation(entry, word_id=word_id)
        final_word = self.get_word_by_id(word_id)
        return self._remove_duplicate_target_translations(entry, final_word)

    def _remove_duplicate_target_translations(
        self, entry: WordEntry, word: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if word is None:
            return None

        translations = list(word.get("translations") or [])
        matching = [item for item in translations if item.get("tr") == entry.definition]
        if len(matching) <= 1:
            return word

        keep_id = matching[0].get("id")
        if keep_id is not None:
            self._make_translation_main(self._word_id(word), keep_id)

        for translation in matching[1:]:
            translation_id = translation.get("id")
            if translation_id is not None:
                self._disable_translation(self._word_id(word), translation_id)

        self._reset_learning_status(self._word_id(word))
        return self.get_word_by_id(self._word_id(word))

    def _word_matches(self, word: dict[str, Any], entry: WordEntry) -> bool:
        return self._build_verification(word, entry).ok

    def _build_verification(self, word: dict[str, Any] | None, entry: WordEntry) -> Verification:
        if word is None:
            return Verification()

        return Verification(
            exact_word=word.get("wordValue") == entry.word,
            combined_translation=self._has_target_translation(word, entry.definition),
            learning_status=int(word.get("learningStatus") or 0) == 0,
            progress=int(word.get("progress") or 0) == 0,
            word_set=self._in_word_set(word),
        )

    def _in_word_set(self, word: dict[str, Any]) -> bool:
        if self.word_set_id is None:
            return True
        return any(
            item.get("id") == self.word_set_id
            for item in word.get("wordSets") or []
        )

    @staticmethod
    def _has_target_translation(word: dict[str, Any], definition: str) -> bool:
        if word.get("combinedTranslation") == definition:
            return True
        return any(item.get("tr") == definition for item in word.get("translations") or [])

    def _require_word_set_id(self) -> int:
        if self.word_set_id is None:
            raise RuntimeError("Choose a Lingualeo word set before changing words.")
        return self.word_set_id

    @staticmethod
    def _extract_words(response: dict[str, Any]) -> list[dict[str, Any]]:
        words: list[dict[str, Any]] = []
        for group in response.get("data") or []:
            words.extend(group.get("words") or [])
        return words

    @staticmethod
    def _word_from_set_words(response: dict[str, Any]) -> dict[str, Any] | None:
        for item in response.get("data") or []:
            if item.get("word") is not None:
                return item["word"]
        return None

    @staticmethod
    def _find_target_translation(
        translations: list[dict[str, Any]], definition: str
    ) -> dict[str, Any] | None:
        return next((item for item in translations if item.get("tr") == definition), None)

    @staticmethod
    def _word_id(word: dict[str, Any] | None) -> int | None:
        if word is None:
            return None
        return word.get("id") or word.get("wordId")
