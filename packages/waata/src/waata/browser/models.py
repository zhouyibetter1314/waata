"""Strict input models for the C3 browser tools."""

from typing import Annotated, Literal, get_args

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
    "menuitemcheckbox",
    "menuitemradio",
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


class UrlPathStartsWith(ToolArgs):
    condition: Literal["url_path_starts_with"]
    expected: Annotated[str, Field(max_length=4096, pattern=r"^/[^?#]*$")]


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
    UrlEquals | UrlPathStartsWith | TitleEquals | Exists | Visible | Count | TextEquals,
    Field(discriminator="condition"),
]


class InspectArgs(RootModel[InspectCondition]):
    model_config = ConfigDict(frozen=True)


_MODEL_LOCATOR = {
    "type": "object",
    "additionalProperties": False,
    "required": ["strategy"],
    "description": (
        "Copy a locator from the page. Use role and name for strategy role; "
        "use value for other strategies. exact defaults to true for role, "
        "label, text and placeholder; omit it for css and test_id."
    ),
    "properties": {
        "strategy": {
            "type": "string",
            "enum": [
                get_args(variant.model_fields["strategy"].annotation)[0]
                for variant in get_args(get_args(LocatorSpec)[0])
            ],
        },
        "role": {"type": "string", "enum": list(get_args(AriaRole))},
        "name": {"type": "string"},
        "value": {"type": "string"},
        "exact": {"type": "boolean"},
    },
}


def model_tool_schema(model: type[BaseModel]) -> dict:
    """Describe the valid arguments compactly for the model, with strict validation at dispatch."""
    if model is InspectArgs:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["condition"],
            "properties": {
                "condition": {
                    "type": "string",
                    "enum": [
                        get_args(variant.model_fields["condition"].annotation)[0]
                        for variant in get_args(get_args(InspectCondition)[0])
                    ],
                    "description": (
                        "visible/exists: locator only. count/text_equals: locator and "
                        "expected. URL and page title checks: expected only. "
                        "For url_path_starts_with use a path prefix such as /items/."
                    ),
                },
                "locator": _MODEL_LOCATOR,
                "expected": {
                    "anyOf": [{"type": "string"}, {"type": "integer", "minimum": 0}],
                    "description": "Use an integer for count and a string for comparisons.",
                },
                "timeout_ms": {"type": "integer", "minimum": 1},
            },
        }
    schema = model.model_json_schema()
    if "locator" in schema["properties"]:
        schema["properties"]["locator"] = _MODEL_LOCATOR
        schema.pop("$defs")
    return schema


BROWSER_TOOLS = (
    ("browser.observe", "Observe the current page and visible controls.", ObserveArgs),
    ("browser.navigate", "Open an approved URL on the case origin.", NavigateArgs),
    ("browser.click", "Click a single visible control.", ClickArgs),
    (
        "browser.fill",
        "Fill a control with exactly one of value or secret_ref.",
        FillArgs,
    ),
    (
        "browser.select_option",
        "Select one option by value in a native select.",
        SelectOptionArgs,
    ),
    (
        "browser.screenshot",
        "Register a screenshot of the current page or control with sensitive fields redacted.",
        ScreenshotArgs,
    ),
    (
        "browser.inspect",
        "Inspect a deterministic checkpoint on the current page.",
        InspectArgs,
    ),
)
