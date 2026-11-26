"""Fixed browser-side reads for a bounded, redacted page observation."""

import re
from typing import get_args

from .models import AriaRole

ROLES = frozenset(get_args(AriaRole))

COLLECT_CONTROLS = """({limit, textLimit, approvedSelectors = []}) => {
    const controlSelector =
        'a[href], button, summary, input:not([type=hidden]), select, textarea, [role], [contenteditable], [aria-haspopup]';
    const candidates = document.querySelectorAll(controlSelector);
    const elements = [];
    const approved = new Map();
    for (const selector of approvedSelectors) {
        try {
            const matches = document.querySelectorAll(selector);
            if (matches.length === 1) approved.set(matches[0], selector);
        } catch { /* Playwright-only locators are not DOM selectors. */ }
    }
    const seen = new Set();
    const scanLimit = Math.max(200, 5 * limit);
    let truncated = false;
    const text = value =>
        value && value.replace(/\\u200b/g, '').trim().slice(0, textLimit) || null;
    const naturalRole = element => {
        if (element.matches('a[href]')) return 'link';
        if (element.matches('button,summary,input[type=button],input[type=submit],input[type=reset]'))
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
    const unique = selector =>
        selector.length <= 512 && document.querySelectorAll(selector).length === 1;
    const cssHint = (element, href) => {
        const tag = CSS.escape(element.localName);
        const name = element.getAttribute('name');
        const selectors = [];
        if (element.id) selectors.push('#' + CSS.escape(element.id));
        if (name) selectors.push(tag + '[name=' + CSS.escape(name) + ']');
        if (href) selectors.push(tag + '[href=' + CSS.escape(href) + ']');
        if (element.matches('[contenteditable=true]')) {
            selectors.push(tag + '[contenteditable=true]');
        }
        for (const className of Array.from(element.classList).slice(0, 4)) {
            selectors.push(tag + '.' + CSS.escape(className));
        }
        return selectors.find(unique) || null;
    };
    const collect = (nodes, include = () => true) => {
        for (let index = 0; index < Math.min(nodes.length, scanLimit); index++) {
            const element = nodes[index];
            if (seen.has(element) || element.closest('[inert],[aria-hidden=true]') ||
                !element.getClientRects().length ||
                getComputedStyle(element).visibility !== 'visible' || !include(element)) continue;
            if (elements.length === limit) {
                truncated = true;
                return;
            }
            seen.add(element);
            const labelIds = (element.getAttribute('aria-labelledby') || '').split(/\\s+/);
            const labelled = labelIds.map(id => document.getElementById(id)?.innerText || '').join(' ');
            const labels = Array.from(element.labels || [], label => label.innerText).join(' ');
            const label = text(labelled) || text(element.getAttribute('aria-label')) || text(labels);
            const contents = element.matches('input,textarea,select,[contenteditable]')
                ? null : text(element.innerText);
            const testId = element.getAttribute('data-testid');
            const href = element.getAttribute('href');
            const localLink = element instanceof HTMLAnchorElement &&
                href && !href.startsWith('#') && element.origin === location.origin &&
                !element.search && !element.hash && !element.username && !element.password;
            const css = cssHint(element, localLink ? href : null);
            elements.push({
                role: text(element.getAttribute('role')) || naturalRole(element),
                name: label || contents || (approved.has(element) ? text(element.getAttribute('placeholder')) : null),
                approved_css: approved.get(element),
                text: contents,
                label,
                placeholder: text(element.getAttribute('placeholder')),
                test_id: testId && unique('[data-testid=' + CSS.escape(testId) + ']')
                    ? testId : null,
                css,
                href: localLink && !css ? element.href : null,
                enabled: !element.matches(':disabled') && !element.closest('[aria-disabled=true]'),
            });
        }
        if (nodes.length > scanLimit) truncated = true;
    };
    // A focused form can follow a long page and contain many icon-only controls.
    const fields =
        'input:not([type=hidden], [type=button], [type=reset], [type=submit]), ' +
        'textarea, select, [contenteditable=true], [role=textbox], [role=combobox]';
    const buttons = 'button, [role=button], input[type=submit]';
    const options = '[role=option], [role=menuitem], [role=menuitemradio], [role=menuitemcheckbox]';
    const choices = 'summary, [role=listbox], [aria-haspopup], ' + options;
    const actionButton = element =>
        element.matches('[type=submit]') || Boolean(text(element.innerText));
    collect([...approved.keys()]);
    const activeForm = document.activeElement?.closest(
        'form, dialog, [role=dialog], [role=alertdialog]'
    );
    if (activeForm) {
        collect(activeForm.querySelectorAll(fields));
        collect(activeForm.querySelectorAll(choices));
        collect(activeForm.querySelectorAll(buttons), actionButton);
    }
    collect(document.querySelectorAll(options));
    collect(document.querySelectorAll(fields));
    collect(document.querySelectorAll(buttons), actionButton);
    collect(document.querySelectorAll('a[href], [role=link]'), element =>
        Boolean(text(element.innerText) || text(element.getAttribute('aria-label')))
    );
    collect(candidates);
    return {elements, truncated};
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
    if control["css"]:
        return {"strategy": "css", "value": control["css"]}
    if control["label"]:
        return {"strategy": "label", "value": control["label"]}
    if control["role"] in ROLES and control["name"]:
        return {"strategy": "role", "role": control["role"], "name": control["name"]}
    if control["placeholder"]:
        return {"strategy": "placeholder", "value": control["placeholder"]}
    return None
