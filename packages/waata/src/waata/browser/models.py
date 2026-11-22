"""Strict input models for the C3 browser tools."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

NonEmpty = Annotated[str, Field(min_length=1, max_length=4096, pattern=r"\S")]
LocatorText = Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]
PlainText = Annotated[str, Field(max_length=4096)]
PositiveInt = Annotated[int, Field(gt=0)]
AriaRole = Literal[
    "button",
    "checkbox",
    "combobox",
    "heading",
    "link",
    "listbox",
    "menuitem",
    "option",
    "radio",
    "searchbox",
    "slider",
    "spinbutton",
    "switch",
    "tab",
    "textbox",
]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RoleLocator(StrictInput):
    strategy: Literal["role"]
    role: AriaRole
    name: LocatorText
    exact: bool = True


class LabelLocator(StrictInput):
    strategy: Literal["label"]
    value: LocatorText
    exact: bool = True


class TextLocator(StrictInput):
    strategy: Literal["text"]
    value: LocatorText
    exact: bool = True


class PlaceholderLocator(StrictInput):
    strategy: Literal["placeholder"]
    value: LocatorText
    exact: bool = True


class TestIdLocator(StrictInput):
    strategy: Literal["test_id"]
    value: LocatorText


class CssLocator(StrictInput):
    strategy: Literal["css"]
    value: LocatorText


LocatorSpec = Annotated[
    RoleLocator
    | LabelLocator
    | TextLocator
    | PlaceholderLocator
    | TestIdLocator
    | CssLocator,
    Field(discriminator="strategy"),
]


class ToolArgs(StrictInput):
    timeout_ms: PositiveInt | None = None


class ObserveArgs(ToolArgs):
    include_screenshot: bool = False


class NavigateArgs(ToolArgs):
    url: NonEmpty


class ClickArgs(ToolArgs):
    locator: LocatorSpec


class FillArgs(ClickArgs):
    value: PlainText | None = None
    secret_ref: NonEmpty | None = None

    @model_validator(mode="after")
    def one_input(self) -> "FillArgs":
        if (self.value is None) == (self.secret_ref is None):
            raise ValueError("provide either value or secret_ref")
        if {"value", "secret_ref"} <= self.model_fields_set:
            raise ValueError("provide only one of value and secret_ref")
        return self


class SelectOptionArgs(ClickArgs):
    value: PlainText


class ScreenshotArgs(ToolArgs):
    full_page: bool = False
    locator: LocatorSpec | None = None

    @model_validator(mode="after")
    def one_capture_area(self) -> "ScreenshotArgs":
        if self.full_page and self.locator is not None:
            raise ValueError("full_page cannot be combined with an element locator")
        return self


class UrlEquals(ToolArgs):
    condition: Literal["url_equals"]
    expected: PlainText


class TitleEquals(ToolArgs):
    condition: Literal["title_equals"]
    expected: PlainText


class Exists(ClickArgs):
    condition: Literal["exists"]


class Visible(ClickArgs):
    condition: Literal["visible"]


class Count(ClickArgs):
    condition: Literal["count"]
    expected: Annotated[int, Field(ge=0)]


class TextEquals(ClickArgs):
    condition: Literal["text_equals"]
    expected: PlainText


InspectCondition = Annotated[
    UrlEquals | TitleEquals | Exists | Visible | Count | TextEquals,
    Field(discriminator="condition"),
]


class InspectArgs(RootModel[InspectCondition]):
    model_config = ConfigDict(frozen=True)


BROWSER_TOOLS = (
    ("browser.observe", "Observe the current page and visible controls.", ObserveArgs),
    ("browser.navigate", "Open an approved URL on the case origin.", NavigateArgs),
    ("browser.click", "Click a single visible control.", ClickArgs),
    (
        "browser.fill",
        "Fill a control with text or an authorized secret reference.",
        FillArgs,
    ),
    (
        "browser.select_option",
        "Select one option by value in a native select.",
        SelectOptionArgs,
    ),
    (
        "browser.screenshot",
        "Register a masked screenshot of the current page or control.",
        ScreenshotArgs,
    ),
    (
        "browser.inspect",
        "Inspect a deterministic checkpoint on the current page.",
        InspectArgs,
    ),
)
