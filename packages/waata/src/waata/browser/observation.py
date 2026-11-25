"""Fixed browser-side reads for a bounded, redacted page observation."""

import re
from typing import get_args

from .models import AriaRole

ROLES = frozenset(get_args(AriaRole))

COLLECT_CONTROLS = """({limit, textLimit, approvedSelectors}) => {
    const controlSelector =
        'a[href], button, input:not([type=hidden]), select, textarea, [role], [contenteditable]';
    const candidates = document.querySelectorAll(controlSelector);
    const elements = [];
    const approved = new Map();
    for (const selector of approvedSelectors) {
        try {
            const matches = document.querySelectorAll(selector);
            if (matches.length === 1) approved.set(matches[0], selector);
        } catch { /* Playwright-only syntax has no DOM selector equivalent. */ }
    }
    const scanLimit = Math.min(candidates.length, Math.max(200, 5 * limit));
    const text = value => value && value.trim().slice(0, textLimit) || null;
    const naturalRole = element => {
        if (element.matches('a[href]')) return 'link';
        if (element.matches('button,input[type=button],input[type=submit],input[type=reset]'))
            return 'button';
        if (element.matches('input[type=checkbox]')) return 'checkbox';
        if (element.matches('input[type=radio]')) return 'radio';
        if (element.matches('input[type=range]')) return 'slider';
        if (element.matches('input[type=number]')) return 'spinbutton';
        if (element.matches('input[type=search]')) return 'searchbox';
        if (element.matches('select'))
            return element.multiple || element.size > 1 ? 'listbox' : 'combobox';
        if (element.matches('input,textarea,[contenteditable=true]')) return 'textbox';
        return null;
    };
    // Keep exact, authorized matches before long lists of repeated controls.
    const priority = [...approved.keys()].filter(element => element.matches(controlSelector));
    const prioritized = new Set(priority);
    for (let index = 0; index < priority.length + scanLimit; index++) {
        const element = index < priority.length ? priority[index] : candidates[index - priority.length];
        if (index >= priority.length && prioritized.has(element)) continue;
        if (element.closest('[inert],[aria-hidden=true]') || !element.getClientRects().length ||
            getComputedStyle(element).visibility !== 'visible') continue;
        if (elements.length === limit) return {elements, truncated: true};
        const labelIds = (element.getAttribute('aria-labelledby') || '').split(/\\s+/);
        const labelled = labelIds.map(id => document.getElementById(id)?.innerText || '').join(' ');
        const labels = Array.from(element.labels || [], label => label.innerText).join(' ');
        const label = text(labelled) || text(element.getAttribute('aria-label')) || text(labels);
        const contents = element.matches('input,textarea,select,[contenteditable]')
            ? null : text(element.innerText);
        elements.push({
            role: text(element.getAttribute('role')) || naturalRole(element),
            name: label || contents,
            text: contents,
            label,
            placeholder: text(element.getAttribute('placeholder')),
            test_id: text(element.getAttribute('data-testid')),
            approved_css: approved.get(element),
            enabled: !element.matches(':disabled') && !element.closest('[aria-disabled=true]'),
        });
    }
    return {elements, truncated: scanLimit < candidates.length};
}"""

_VALUE_NODE = re.compile(r"^(\s*)-\s+(textbox|searchbox|spinbutton|combobox|slider)\b")
_CONTROL_NAME = re.compile(r'^([^"\n]*?)(?:\s+"((?:[^"\\]|\\.)*)")?\s*[:\[].*?$')


def omit_form_values(snapshot: str) -> str:
    """Keep control roles and names while omitting editable values and subtrees."""
    lines: list[str] = []
    skip_below: int | None = None
    for line in snapshot.splitlines():
        indent = len(line) - len(line.lstrip())
        if skip_below is not None and indent > skip_below:
            continue
        skip_below = None
        control = _VALUE_NODE.match(line)
        if control is None:
            lines.append(line)
            continue
        suffix = line[control.end() :]
        name = _CONTROL_NAME.match(suffix)
        if name is None:
            if suffix.strip().startswith('"') and suffix.strip().endswith('"'):
                lines.append(line)
            else:
                lines.append(line[: control.end()])
        else:
            accessible_name = name.group(2)
            lines.append(
                line[: control.end()]
                + (f' "{accessible_name}"' if accessible_name else "")
            )
        skip_below = indent
    return "\n".join(lines)


def suggested_locator(control: dict) -> dict[str, str] | None:
    if control.get("approved_css"):
        return {"strategy": "css", "value": control["approved_css"]}
    if control["test_id"]:
        return {"strategy": "test_id", "value": control["test_id"]}
    if control["label"]:
        return {"strategy": "label", "value": control["label"]}
    if control["role"] in ROLES and control["name"]:
        return {"strategy": "role", "role": control["role"], "name": control["name"]}
    if control["placeholder"]:
        return {"strategy": "placeholder", "value": control["placeholder"]}
    return None
