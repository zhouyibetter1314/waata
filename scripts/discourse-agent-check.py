"""Run real Discourse DC01–DC11 scenarios through the public WAATA Python API.

No platform PostgreSQL is required. Raw evidence and a SQLite QA index stay local.
Fixture mutations are restricted to prepare; independent verification never saves
scenario changes. Use --prepared to explicitly exclude login from Agent actions.
"""

import argparse
import asyncio
import json
import re
import sqlite3
import subprocess
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

from dotenv import dotenv_values
from playwright.async_api import async_playwright
from waata.artifacts import ArtifactInput, ArtifactRef
from waata.browser import BrowserLimits, CredentialField, PlaywrightAdapter
from waata.core.model import estimate_request_input_tokens
from waata.llm import OpenAILike
from waata.orchestrator import TestEngine, TestRequest, WAATAError
from waata.orchestrator.config import EngineConfig

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/discourse"
HOME = "http://127.0.0.1:4200"
CONTAINER = "waata-discourse"
LOGIN, PASSWORD, SUBMIT = (
    "#login-account-name",
    "#login-account-password",
    "#login-button",
)
ACTIONS = {"browser.navigate", "browser.click", "browser.fill", "browser.select_option"}
MASKS = (
    "input",
    "textarea",
    "[contenteditable]",
    ".invite-link",
    ".invite-shortkey",
    '[href*="/invites/"]',
)


def config():
    return dotenv_values(ROOT / ".env")


def redact(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    for key, secret in config().items():
        if secret and any(word in key for word in ("PASSWORD", "API_KEY", "LOGIN")):
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(/invites/)[a-z0-9_-]{8,}", r"\1[REDACTED]", text)
    return text if isinstance(value, str) else json.loads(text)


def rails(script, payload=None):
    # Copy only to the disposable target container, not the pinned submodule.
    subprocess.run(
        ["docker", "cp", str(script), f"{CONTAINER}:/tmp/waata-qa.rb"],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "-u",
            "discourse",
            "-w",
            "/src",
            CONTAINER,
            "bin/rails",
            "runner",
            "/tmp/waata-qa.rb",
        ],
        input=json.dumps(payload or {}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(redact(result.stderr[:2000] + result.stderr[-1000:]))
    return json.loads(result.stdout.strip().splitlines()[-1])


def prepare(args):
    env = config()
    tag = datetime.now(UTC).strftime("%m%d%H%M") + "-" + uuid4().hex[:4]
    payload = {"tag": tag, "reset_preferences": not args.keep_preferences}
    for role in ("admin", "member"):
        payload[role] = {
            key: env[f"WAATA_DC_{role.upper()}_{key.upper()}"]
            for key in ("login", "password")
        }
    fixture = rails(ROOT / "scripts/discourse-fixtures.rb", payload)
    LOCAL.mkdir(parents=True, exist_ok=True)
    path = LOCAL / f"fixture-{tag}.json"
    path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    print(path)


def scene(fixture, key):
    f = fixture["scenes"][key]
    url = f["url"]
    post = "#post_1"
    body = post + " .cooked"
    title = "#topic-title h1"
    controls = [
        "#reply-title",
        "textarea.d-editor-input",
        "button.create",
        "#reply-control button.create",
        title,
        body,
    ]
    # Checkpoints are final-state checks. Stage evidence is audited separately.
    if key == "DC01":
        goal = f'Create topic "{f["title"]}" in category WAATA Lab with first post "{f["body"]}". Open {url} first.'
        expected = f"Topic title {f['title']}, category WAATA Lab and exact first post {f['body']} are visible after saving."
        checks = [(title, f["title"]), (body, f["body"])]
    elif key == "DC02":
        text = "I reviewed the local fixture and confirmed that the discussion is ready for testing."
        goal = f'Open {url} and reply once with "{text}". Use the topic Reply, then composer Reply (#reply-control button.create).'
        expected = f'Same topic shows reply "{text}" below first post, authored by Member Fixture.'
        checks = [
            ("#post_2 .cooked", text),
            ("#post_2 .names .full-name", "Member Fixture"),
        ]
    elif key == "DC03":
        goal = f"Open {url}, Like the first administrator post once, then reopen {url}."
        expected = "The first post still has Undo like after reopening."
        checks = [(post + " button.has-like", None)]
    elif key == "DC04":
        goal = f'Open {url}. Change Text Size from Normal to Larger: open .text-size .combo-box then click li.select-kit-row[data-value="larger"]. Save Changes, then reopen {url}. Save as account default, not a device-only override.'
        expected = (
            "Saved Interface Text Size is Larger; html has text-size-larger class."
        )
        checks = [
            (".text-size .combo-box .selected-name", "Larger"),
            ("html.text-size-larger", None),
        ]
        controls += [
            ".text-size .combo-box",
            ".text-size .combo-box .selected-name",
            "html.text-size-larger",
            'li.select-kit-row[data-value="larger"]',
        ]
    elif key == "DC05":
        text = "The local test meeting starts on Friday at ten in the morning."
        goal = f'Open {url}. Edit only my reply (post 2) from "The test meeting starts on Thursday." to "{text}". Save Edit, reopen same topic.'
        expected = f'Same reply has exact text "{text}" and no old Thursday sentence.'
        checks = [("#post_2 .cooked", text)]
    elif key == "DC06":
        goal = f'Open {url}. Click .topic-footer-main-buttons button.bookmark ONCE to bookmark topic "{f["title"]}"; this immediately saves with no reminder. Do not choose a reminder. Open {HOME}/u/waata_member/activity/bookmarks, collect observation of the matching entry BEFORE following it, then click its exact title link table.bookmark-list a.title:has-text("{f["title"]}") back to the topic. Do not substitute direct URL navigation for following the bookmark.'
        expected = (
            f"After following the saved bookmark, target topic title is {f['title']}."
        )
        checks = [(title, f["title"])]
        controls += [
            ".topic-footer-main-buttons button.bookmark",
            f'table.bookmark-list a.title:has-text("{f["title"]}")',
        ]
    elif key == "DC07":
        goal = f"Open {url}. On first post More (#post_1 button.show-more-actions) then post Admin (#post_1 button.show-post-admin-menu), click .fk-d-menu button.wiki (Make Wiki). Reopen topic, open same menu to OBSERVE Remove Wiki using browser.inspect text_equals on .fk-d-menu button.wiki. Leave this menu OPEN when finishing so final checkpoints can inspect it. Do not click Remove Wiki or bookmark. Keep body unchanged."
        expected = f'First post exact body "{f["body"]}"; Wiki indicator visible and menu offers Remove Wiki.'
        checks = [(body, f["body"]), (post + " .post-info.edits button.wiki", None)]
    elif key == "DC08":
        goal = f'Open {url}. Create link invitation "{f["description"]}" with Max uses 1 and no email. Open Edit link options if needed. Close modal and inspect Pending row; never read or expose invite URL.'
        expected = f"Pending row {f['description']} shows 0/1 uses and future expiry."
        checks = [
            (f'table.user-invite-list tbody > tr:has-text("{f["description"]}")', None)
        ]
    elif key == "DC09":
        text = "The shared test guide now includes a local account verification step."
        control = fixture["scenes"]["DC09-control"]["url"]
        goal = f'As member first open {control}, expand More if needed and observe available first-post actions showing no Edit. Keep that observation BEFORE opening {url}. Edit this other user Wiki first post to "{text}", save, reopen.'
        expected = f'Wiki exact body "{text}" persists and Wiki indicator remains.'
        checks = [(body, text), (post + " .post-info.edits button.wiki", None)]
    elif key == "DC10":
        text = (
            "The fixture checklist records the completed handoff for the local project."
        )
        goal = f'Open {url}. Edit Wiki first post body to "{text}", Save Edit (#reply-control button.create). Reopen {url} to reset expanded controls after editing. Click first post More (#post_1 button.show-more-actions) then Admin (#post_1 button.show-post-admin-menu), then .fk-d-menu button.wiki (Remove Wiki). Reopen {url} again and open More then Admin to OBSERVE Make Wiki using browser.inspect text_equals. Leave menu OPEN when finishing so final checkpoints can inspect it. Do not click Make Wiki.'
        expected = f'First post exact body "{text}" persists, Wiki indicator absent, Admin menu offers Make Wiki.'
        checks = [(body, text), (post + " .post-info.edits button.wiki", 0)]
    else:
        goal = f'Open {url}. Edit ONLY invite "{f["description"]}" from Max uses 2 to 1. Save with .create-invite-modal button.save-invite (Update, NOT Copy link), close with .create-invite-modal button.modal-close if still open, observe scoped row showing 0/1 BEFORE removal. Then its More options -> .fk-d-menu button.btn-danger (Remove); confirm removal if prompted, reopen Pending. Never expose invite URL; keep "{f["keep"]}" untouched.'
        expected = f"Pending scoped invitation {f['description']} absent, control {f['keep']} still exists."
        checks = [
            (f'table.user-invite-list tbody > tr:has-text("{f["description"]}")', 0),
            (f'table.user-invite-list tbody > tr:has-text("{f["keep"]}")', None),
        ]
    controls += [s for s, _ in checks]
    if key in {"DC08", "DC11"}:
        controls += [
            '.create-invite-modal input[name="description"]',
            '.create-invite-modal input[name="maxRedemptions"]',
            ".create-invite-modal button.save-invite",
            ".create-invite-modal button.modal-close",
            ".fk-d-menu button.btn-danger",
            f'table.user-invite-list tbody > tr:has-text("{f["description"]}") button.edit-invite',
            f'table.user-invite-list tbody > tr:has-text("{f["description"]}") .fk-d-menu__trigger',
        ]
    controls += [
        f"#post_{n} button.{action}"
        for n in (1, 2)
        for action in (
            "like",
            "has-like",
            "show-more-actions",
            "edit",
            "bookmark",
            "show-post-admin-menu",
        )
    ]
    controls += [
        ".topic-footer-main-buttons .create",
        "button.save",
        ".edit-link-options",
        ".fk-d-menu button.wiki",
    ]
    role = "admin" if key in {"DC07", "DC08", "DC10", "DC11"} else "member"
    return role, goal, expected, list(dict.fromkeys(controls)), checks


async def sign_in(browser, role):
    env = config()
    context = await browser.new_context(
        locale="en-US", viewport={"width": 1440, "height": 1000}
    )
    page = await context.new_page()
    page.set_default_timeout(15000)
    await page.goto(HOME + "/login", wait_until="domcontentloaded", timeout=60000)
    await page.locator(LOGIN).fill(env[f"WAATA_DC_{role.upper()}_LOGIN"])
    await page.locator(PASSWORD).fill(env[f"WAATA_DC_{role.upper()}_PASSWORD"])
    await page.locator(SUBMIT).click()
    await page.locator("#current-user").wait_for(timeout=30000)
    return context, page


async def ready(page):
    """Wait for actual SPA content rather than a fixed post-navigation delay."""
    await page.locator("#current-user").wait_for(timeout=20000)
    if "/t/" in page.url:
        await page.locator("#post_1 .cooked").wait_for(timeout=20000)
    elif "/invited/" in page.url:
        await page.locator("table.user-invite-list, .empty-state").first.wait_for(
            timeout=20000
        )
    elif "/activity/bookmarks" in page.url:
        await page.locator("#bookmark-search, .empty-state").first.wait_for(
            timeout=20000
        )
    elif "/preferences/interface" in page.url:
        await page.locator(".text-size .combo-box").wait_for(timeout=20000)


class PreparedBrowser:
    def __init__(self, browser, state=None):
        self.browser, self.state = browser, state
        self.contexts = []

    async def new_context(self, **kwargs):
        context = await self.browser.new_context(storage_state=self.state, **kwargs)
        self.contexts.append(context)
        return context


class Evidence:
    def __init__(self, path):
        self.path = path

    async def save(self, artifact: ArtifactInput):
        artifact_id = "dc-art-" + uuid4().hex
        meta = artifact.model_dump(exclude={"content"})
        suffix = ".png" if artifact.kind == "screenshot" else ".json"
        content = artifact.content
        if artifact.mime_type == "application/json":
            content = redact(content.decode()).encode()
        (self.path / (artifact_id + suffix)).write_bytes(content)
        return ArtifactRef(**meta, artifact_id=artifact_id, size_bytes=len(content))


class RecordedModel:
    def __init__(self, provider, output):
        self.provider, self.output = provider, output
        self.turns = []

    @property
    def metadata(self):
        return self.provider.metadata

    async def chat(self, messages, **kwargs):
        # Omit invitation tokens before sending observations to the provider.
        messages = tuple(
            replace(message, content=redact(message.content))
            if message.content
            else message
            for message in messages
        )
        # Preserve the full runtime tool set, including observe/inspect. Reading
        # a menu state must never force the Agent to click a mutating control.
        result = await self.provider.chat(messages, **kwargs)
        self.turns.append(
            redact(
                {
                    "content": result.message.content,
                    "calls": [asdict(call) for call in result.message.tool_calls],
                    "usage": asdict(result.usage) if result.usage else None,
                    "estimated_input": estimate_request_input_tokens(
                        messages, kwargs.get("tools", ())
                    ),
                }
            )
        )
        # Persist every successful turn even if the runner later crashes.
        (self.output / "decisions.json").write_text(
            json.dumps(self.turns, indent=2), encoding="utf-8"
        )
        print(
            f"model turn {len(self.turns)}: "
            + ", ".join(call.name for call in result.message.tool_calls),
            flush=True,
        )
        return result


async def verify(browser, fixture, key, output):
    role, _, _, _, checks = scene(fixture, key)
    f = fixture["scenes"][key]
    context, page = await sign_in(browser, role)
    try:
        url = f["url"]
        if key == "DC01":
            await page.goto(HOME + "/latest")
            await page.get_by_role("link", name=f["title"], exact=True).click()
        else:
            await page.goto(url)
        await ready(page)
        actual = []
        for selector, expected in checks:
            loc = page.locator(selector)
            count = await loc.count()
            value = (
                (await loc.inner_text()).strip()
                if isinstance(expected, str) and count == 1
                else count
            )
            wanted = 1 if expected is None else expected
            actual.append(
                {
                    "selector": selector,
                    "expected": wanted,
                    "actual": value,
                    "passed": value == wanted,
                }
            )
        if key == "DC01":
            text = await page.locator("#topic-title").inner_text()
            actual.append(
                {"check": "WAATA Lab category", "passed": "WAATA Lab" in text}
            )
        if key == "DC02":
            author = await page.locator("#post_2 .names").inner_text()
            actual.append(
                {
                    "check": "reply author",
                    "actual": author,
                    "passed": "Member Fixture" in author,
                }
            )
        if key == "DC05":
            actual.append(
                {
                    "check": "old sentence absent",
                    "passed": "Thursday"
                    not in await page.locator("#post_2 .cooked").inner_text(),
                }
            )
        if key in {"DC07", "DC10"}:
            more = page.locator("#post_1 button.show-more-actions")
            if await more.count() and await more.is_visible():
                await more.click()
            await page.locator("#post_1 button.show-post-admin-menu").click()
            menu_text = "Remove Wiki" if key == "DC07" else "Make Wiki"
            menu = page.locator(".fk-d-menu button.wiki")
            await menu.wait_for(state="visible", timeout=7000)
            actual.append(
                {
                    "check": menu_text,
                    "actual": (await menu.inner_text()).strip(),
                    "passed": (await menu.inner_text()).strip() == menu_text,
                }
            )
        if key in {"DC08", "DC11"}:
            if key == "DC08":
                row = page.locator(checks[0][0])
                text = await row.inner_text() if await row.count() else ""
                actual.append(
                    {
                        "check": "0/1 redemption",
                        "passed": bool(re.search(r"0\s*/\s*1", text)),
                        "actual": text,
                    }
                )
        if key == "DC06":
            # Independent final persistence check does not establish Agent ordering.
            await page.goto(HOME + "/u/waata_member/activity/bookmarks")
            link = page.locator(f'table.bookmark-list a.title:has-text("{f["title"]}")')
            await ready(page)
            try:
                await link.wait_for(timeout=7000)
            except Exception:
                pass
            present = await link.count() == 1
            actual.append({"check": "persisted bookmark entry", "passed": present})
            await page.screenshot(
                path=output / "independent-bookmarks.png",
                mask=[page.locator(s) for s in MASKS],
            )
            if present:
                await link.click()
                await page.wait_for_url("**/t/**", timeout=15000)
                await ready(page)
                actual.append(
                    {
                        "check": "bookmark leads to target topic",
                        "passed": f"/{f['topic_id']}" in page.url
                        and (await page.locator("#topic-title h1").inner_text()).strip()
                        == f["title"],
                    }
                )
        await page.screenshot(
            path=output / "independent.png", mask=[page.locator(s) for s in MASKS]
        )
        return {
            "passed": all(c["passed"] for c in actual),
            "checks": actual,
            "url": page.url,
            "fresh_session": True,
        }
    finally:
        await context.close()


def save_index(report, output):
    LOCAL.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LOCAL / "qa.sqlite") as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, scene TEXT, report_json TEXT, report_path TEXT)"
        )
        db.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            (
                report["run_id"],
                report["scene"],
                json.dumps(report),
                str(output / "report.json"),
            ),
        )


async def preflight(args):
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    output = LOCAL / "preflight"
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for role in ("member", "admin"):
            context, page = await sign_in(browser, role)
            await page.goto(fixture["scenes"]["DC02"]["url"])
            await page.wait_for_timeout(1000)
            (output / f"{role}.txt").write_text(
                redact(await page.locator("body").aria_snapshot()), encoding="utf-8"
            )
            await page.screenshot(
                path=output / f"{role}.png", mask=[page.locator(s) for s in MASKS]
            )
            await context.close()
            print(role + " login and topic read OK", flush=True)
        await browser.close()


async def verify_only(args):
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            independent = await verify(browser, fixture, args.scene, output)
        finally:
            await browser.close()
    data = {
        "verified_at": datetime.now(UTC).isoformat(),
        "scene": args.scene,
        "model_called": False,
        "independent": independent,
    }
    (output / "verification.json").write_text(
        json.dumps(redact(data), indent=2), encoding="utf-8"
    )
    print(json.dumps(redact(data)), flush=True)


async def run(args):
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    key = args.scene
    role, goal, expected, selectors, checks = scene(fixture, key)
    run_id = key.lower() + "-agent-" + uuid4().hex[:10]
    output = LOCAL / "runs" / run_id
    output.mkdir(parents=True)
    env = config()
    events, stages = [], []
    started_at = datetime.now(UTC).isoformat()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        injected_browser = PreparedBrowser(browser)
        if args.prepared:
            context, _ = await sign_in(browser, role)
            injected_browser = PreparedBrowser(browser, await context.storage_state())
            await context.close()
        ref = "dc_" + role
        fields = {
            ref + "_login": CredentialField(
                value=env[f"WAATA_DC_{role.upper()}_LOGIN"],
                locator={"strategy": "css", "value": LOGIN},
            ),
            ref + "_password": CredentialField(
                value=env[f"WAATA_DC_{role.upper()}_PASSWORD"],
                locator={"strategy": "css", "value": PASSWORD},
            ),
        }
        adapter = PlaywrightAdapter(
            browser=injected_browser,
            allowed_origins=[HOME],
            allowed_css_selectors=selectors + [LOGIN, PASSWORD, SUBMIT],
            credential_sets={ref: fields},
            allow_screenshots=True,
            screenshot_mask_selectors=MASKS,
            limits=BrowserLimits(
                default_timeout_ms=15000,
                max_timeout_ms=15000,
                max_observation_chars=18000,
                max_elements=60,
            ),
        )

        async def event(event):
            data = redact(event.model_dump(mode="json"))
            events.append(data)
            with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(data) + "\n")
            if (
                event.type == "tool.completed"
                and event.payload.get("success")
                and event.payload.get("tool") in {"browser.click", "browser.navigate"}
            ):
                await asyncio.sleep(0.6)
                # Read-only stage audit of the Agent's own page. These reads do
                # not issue scenario actions or influence the model's decisions.
                for context in injected_browser.contexts:
                    for page in context.pages:
                        if (
                            event.payload.get("tool") == "browser.navigate"
                            and "/login" not in page.url
                        ):
                            try:
                                await ready(page)
                            except Exception:
                                # A missing ready marker is diagnostic, not a
                                # reason for the evidence callback to kill a Run.
                                pass
                        stage = None
                        f = fixture["scenes"][key]
                        if key == "DC06" and "/activity/bookmarks" in page.url:
                            link = page.locator(
                                f'table.bookmark-list a.title:has-text("{f["title"]}")'
                            )
                            if await link.count() == 1:
                                stage = {
                                    "check": "bookmark listed before follow",
                                    "url": page.url,
                                    "title": f["title"],
                                }
                        if (
                            key == "DC06"
                            and event.payload.get("tool") == "browser.click"
                            and f"/{f['topic_id']}" in page.url
                            and any(
                                s["check"] == "bookmark listed before follow"
                                for s in stages
                            )
                        ):
                            stage = {
                                "check": "bookmark followed to target",
                                "url": page.url,
                                "title": (
                                    await page.locator("#topic-title h1").inner_text()
                                ).strip(),
                            }
                        if (
                            key == "DC09"
                            and str(fixture["scenes"]["DC09-control"]["topic_id"])
                            in page.url
                        ):
                            controls = page.locator("#post_1 button")
                            if await controls.count():
                                stage = {
                                    "check": "ordinary post actions",
                                    "url": page.url,
                                    "edit_visible": await page.locator(
                                        "#post_1 button.edit:visible"
                                    ).count(),
                                    "more_visible": await page.locator(
                                        "#post_1 button.show-more-actions:visible"
                                    ).count(),
                                }
                        if key == "DC11" and "/invited/pending" in page.url:
                            row = page.locator(
                                f'table.user-invite-list tbody > tr:has-text("{f["description"]}")'
                            )
                            if await row.count() == 1:
                                text = await row.inner_text()
                                if re.search(r"0\s*/\s*1", text):
                                    stage = {
                                        "check": "scoped invite 0/1 before removal",
                                        "url": page.url,
                                        "text": text,
                                    }
                        if stage and stage not in stages:
                            stage = redact(stage)
                            stages.append(stage)
                            await page.screenshot(
                                path=output / f"stage-{len(stages)}.png",
                                mask=[page.locator(s) for s in MASKS],
                            )

        async with OpenAILike(
            base_url=env["WAATA_MODEL_BASE_URL"],
            api_key=env["WAATA_MODEL_API_KEY"],
            model=env["WAATA_MODEL_NAME"],
            context_window=65536,
            max_output_tokens=2600,
            timeout=45,
            thinking=False,
        ) as provider:
            model = RecordedModel(provider, output)
            engine = TestEngine(
                llm=model,
                browser=adapter,
                artifact_store=Evidence(output),
                config=EngineConfig(
                    max_test_cases=1,
                    max_checkpoints_per_case=8,
                    max_steps_per_case=27,
                    max_browser_actions_per_run=35,
                    max_model_requests_per_run=30,
                    max_model_tokens_per_run=args.tokens,
                    capture_final_screenshot=True,
                    model_retries=0,
                    timeout_seconds=300,
                    tool_timeout_seconds=12,
                    verification_settle_seconds=0.6,
                ),
            )
            prompt = (
                "Session is already signed in as fixture " + role + ". "
                if args.prepared
                else "Sign in using field-level secret references "
                + ref
                + "_login and "
                + ref
                + "_password. "
            )
            prompt += (
                goal
                + " Use one case. Exact approved CSS locators: "
                + json.dumps(selectors)
                + ". Final expected selector/text pairs: "
                + json.dumps(checks)
                + ". Do not repeat successful actions."
                + " Execute the required mutations before spending turns on final checks. "
                "state.page refreshes automatically. Once all requested actions and "
                "reopening are complete, finish; the runtime evaluates checkpoints. "
                "When using browser.inspect, condition must be at the top level, "
                'for example {"condition":"exists","locator":{"strategy":"css",'
                '"value":"#post_1 .cooked"}}. Never click a control just to inspect it.'
            )
            started = monotonic()
            error = None
            try:
                result = await engine.run(
                    TestRequest(
                        target_url=fixture["scenes"][key]["url"]
                        if args.prepared
                        else HOME + "/login",
                        goal=prompt,
                        expected_behavior=expected,
                        credential_ref=ref,
                    ),
                    run_id=run_id,
                    on_event=event,
                )
            except WAATAError as exc:
                result = exc.partial_result
                error = redact(str(exc))
            seconds = round(monotonic() - started, 2)
            try:
                independent = await verify(browser, fixture, key, output)
            except Exception as exc:
                independent = {"passed": None, "error": redact(str(exc))[:1500]}
            await browser.close()
    report = redact(
        {
            "run_id": run_id,
            "scene": key,
            "fixture": fixture,
            "kind": "live",
            "started_at": started_at,
            "revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "model": env["WAATA_MODEL_NAME"],
            "prepared_login": args.prepared,
            "runner_tool_mode": "full",
            "harness_version": 4,
            "run": result.model_dump(mode="json") if result else None,
            "error": error,
            "seconds": seconds,
            "decisions": model.turns,
            "requests": len(model.turns),
            "paid_tokens": sum(
                (
                    t["usage"]["total_tokens"]
                    or t["usage"]["input_tokens"] + t["usage"]["output_tokens"]
                )
                for t in model.turns
                if t["usage"]
            ),
            "events": events,
            "stages": stages,
            "independent": independent,
            "limits": {
                "actions": 35,
                "tokens": args.tokens,
                "requests": 30,
                "seconds": 300,
            },
            "platform_postgresql": "not configured; C1/Worker/C6 not exercised",
        }
    )
    (output / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    save_index(report, output)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "seconds": seconds,
                "tokens": report["paid_tokens"],
                "verdict": result.verdict if result else None,
                "independent": independent,
                "output": str(output),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare")
    setup.add_argument("--keep-preferences", action="store_true")
    probe = commands.add_parser("preflight")
    probe.add_argument("fixture")
    audit = commands.add_parser("audit")
    audit.add_argument("fixture")
    recheck = commands.add_parser("verify")
    recheck.add_argument("fixture")
    recheck.add_argument("scene", choices=[f"DC{i:02d}" for i in range(1, 12)])
    recheck.add_argument("--output", required=True)
    execute = commands.add_parser("run")
    execute.add_argument("fixture")
    execute.add_argument("scene", choices=[f"DC{i:02d}" for i in range(1, 12)])
    execute.add_argument("--prepared", action="store_true")
    execute.add_argument("--headed", action="store_true")
    execute.add_argument("--tokens", type=int, default=180000)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "preflight":
        asyncio.run(preflight(args))
    elif args.command == "audit":
        fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        data = rails(ROOT / "scripts/discourse-verify.rb", fixture)
        path = LOCAL / ("audit-" + fixture["tag"] + ".json")
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(path)
    elif args.command == "verify":
        asyncio.run(verify_only(args))
    else:
        asyncio.run(run(args))
