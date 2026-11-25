// Deterministic UI checks for the five repository practice scenarios.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { parseEnv } = require('node:util');
const { chromium, expect } = require('../apps/web/node_modules/@playwright/test');

const root = path.resolve(__dirname, '..');
const url = 'http://127.0.0.1:3000/';
const addProject = '[class*="Projects_headerButtonGroup"] button[class*="Projects_addButton"]';
const account = 'waataadmin';
const password = parseEnv(fs.readFileSync(path.join(root, '.local/4gaboards/.env'), 'utf8'))
  .BOARDS_ADMIN_PASSWORD;
const ticket = new Date().toISOString().replace(/\D/g, '').slice(0, 14);
const output = path.join(root, '.local', '4gaboards', 'acceptance', ticket);
const prepareOnly = process.argv.includes('--prepare-only');
const selected = new Set(process.argv.slice(2).filter((arg) => arg !== '--prepare-only'));
const title = (text) => '[title=' + JSON.stringify(text) + ']';

function operations(page, trace) {
  const act = async (name, perform) => {
    assert(trace.length < 35, 'Course action limit reached');
    const entry = { action: name, ok: false };
    trace.push(entry);
    await perform();
    entry.ok = true;
  };
  return {
    visit: (address) => act('navigate', () => page.goto(address)),
    reload: () => act('reload', () => page.reload()),
    click: (name, locator) => act(name, () => locator.click()),
    fill: (name, locator, value) => act(name, () => locator.fill(value)),
  };
}

async function login(page, op) {
  await op.visit(url);
  await op.fill('fill login name', page.locator('input[name=emailOrUsername]'), account);
  await op.fill('fill password', page.locator('input[name=password]'), password);
  await op.click('submit login', page.locator('button[type=submit]'));
  await page.locator(addProject).waitFor();
}

const button = (page, name) => page.getByRole('button', { name, exact: true });
const projectTile = (page, name) => page.locator('[class*="projectTitle"]' + title(name));
const projectLink = (page, name) => page
  .locator('a[class*="sidebarItemInner"]:has(:text-is(' + JSON.stringify(name) + '))');
const listTitle = (page, name) => page.locator('[class*="List_headerName"]' + title(name));
const nameForm = (page, control = 'input') => page.locator('form').filter({
  has: page.locator(control + '[name="name"]:visible'),
});

async function newProject(page, op, name) {
  await op.click('open dashboard Add Project', page.locator(addProject));
  const form = nameForm(page);
  await op.fill('fill project name', form.locator('input[name=name]'), name);
  await op.click('submit new project', form.locator('button[type=submit]'));
  await page.waitForURL(/\/projects\/[^/]+/);
  return page.url();
}

async function newBoard(page, op, name, kanban = false) {
  const current = page.url();
  await op.click('open project Add Board', page.locator('button[class*="Boards_addButton"]:visible').first());
  const form = nameForm(page);
  await op.fill('fill board name', form.locator('input[name=name]'), name);
  if (kanban) {
    await op.click('open template dropdown', form.getByPlaceholder('Empty', { exact: true }));
    await op.click('select Kanban template', page.locator('#kanban'));
    await expect(form.getByPlaceholder('Kanban', { exact: true })).toBeVisible();
  }
  await op.click('submit new board', form.locator('button[type=submit]'));
  await page.waitForURL((next) => /\/boards\/[^/]+/.test(next.pathname) && next.href !== current);
  return page.url();
}

async function newList(page, op, name) {
  await op.click('open board Add List', page.locator('button[class*="Board_addListButton"]'));
  const form = nameForm(page, 'textarea');
  await op.fill('fill list name', form.locator('textarea[name=name]'), name);
  await op.click('submit new list', form.locator('button[type=submit]'));
  await expect(listTitle(page, name)).toBeVisible();
}

async function assertProject(page, name) {
  await expect(projectTile(page, name)).toHaveCount(1);
  await expect(projectTile(page, name)).toBeVisible();
  await expect(projectLink(page, name)).toBeVisible();
  const tileLink = await projectTile(page, name).evaluate((el) => el.closest('a').getAttribute('href'));
  assert.equal(await projectLink(page, name).getAttribute('href'), tileLink);
}

const name = (prefix) => prefix + ' ' + ticket;
const specs = {
  B01: {
    async run(page, op) {
      const project = name('B01 Release Lab');
      await newProject(page, op, project);
      await op.visit(url);
      await assertProject(page, project);
    },
  },
  B02: {
    prepare: (p, op) => newProject(p, op, name('B02 Draft Lab')),
    async run(page, op, projectUrl) {
      const oldName = name('B02 Draft Lab');
      const newName = name('B02 Review Lab');
      const row = projectLink(page, oldName).locator('xpath=..');
      await row.hover();
      await op.click('open project edit menu', row.locator('button[title="Edit Project"]'));
      await op.click('select Rename Project', button(page, 'Rename Project'));
      const form = nameForm(page, 'textarea');
      await op.fill('replace project name', form.locator('textarea[name=name]'), newName);
      await op.click('save project name', form.locator('button[type=submit]'));
      await expect(projectLink(page, newName)).toBeVisible();
      await op.reload();
      await assertProject(page, newName);
      await expect(projectTile(page, oldName)).toHaveCount(0);
      await expect(projectLink(page, oldName)).toHaveCount(0);
      assert.equal(await projectLink(page, newName).getAttribute('href'), new URL(projectUrl).pathname);
    },
  },
  B03: {
    prepare: (p, op) => newProject(p, op, name('B03 Delivery Lab')),
    async run(page, op, projectUrl) {
      await op.visit(projectUrl);
      await newBoard(page, op, name('B03 Workflow'), true);
      for (const list of ['Open', 'Todo', 'In Progress', 'To Test', 'Done']) {
        await expect(listTitle(page, list)).toBeVisible();
      }
    },
  },
  B04: {
    async prepare(p, op) {
      await newProject(p, op, name('B04 Project'));
      return newBoard(p, op, name('B04 Intake'));
    },
    async run(page, op, boardUrl) {
      await op.visit(boardUrl);
      await newList(page, op, name('B04 Incoming'));
      await op.reload();
      await expect(listTitle(page, name('B04 Incoming'))).toHaveCount(1);
      assert.equal(page.url(), boardUrl);
    },
  },
  B05: {
    async prepare(p, op) {
      await newProject(p, op, name('B05 Project'));
      const board = await newBoard(p, op, name('B05 Support'));
      await newList(p, op, name('B05 Inbox'));
      return board;
    },
    async run(page, op, boardUrl) {
      await op.visit(boardUrl);
      const list = listTitle(page, name('B05 Inbox')).locator('xpath=ancestor::*[contains(@class,"List_innerWrapper")][1]');
      await op.click('open Add Card in Inbox', list.locator('button[class*="List_addCardButton"]'));
      const form = nameForm(page, 'textarea');
      const card = name('B05 Confirm delivery');
      await op.fill('fill card title', form.locator('textarea[name=name]'), card);
      await op.click('submit new card', form.locator('button[type=submit]'));
      const cardName = '[class*="Card_name"]' + title(card);
      const persistedCard = list.locator('div[class*="Card_content__"]').filter({
        has: page.locator(cardName),
      });
      await expect(persistedCard).toBeVisible();
      await op.click('open saved card in Inbox', persistedCard);
      await page.waitForURL(/\/cards\/[^/]+/);
      const modalTitle = page.locator('[class*="CardModal_headerTitle__"]');
      await expect(modalTitle).toBeVisible();
      await expect(modalTitle).toHaveText(card);
    },
  },
};

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.WAATA_BROWSER_EXECUTABLE || undefined,
  });
  try {
    for (const [id, spec] of Object.entries(specs)) {
      if (selected.size && !selected.has(id)) continue;
      if (prepareOnly && !spec.prepare) continue;
      const fixtureTrace = [];
      const trace = [];
      const result = { id, kind: 'scripted UI', ticket, tokens: 0, fixtureTrace, trace };
      let context;
      let page;
      let started;
      try {
        let fixture;
        if (spec.prepare) {
          context = await browser.newContext({ locale: 'en-US' });
          page = await context.newPage();
          page.setDefaultTimeout(5500);
          const setup = operations(page, fixtureTrace);
          await login(page, setup);
          fixture = await spec.prepare(page, setup);
          await context.close();
        }
        if (prepareOnly) {
          const data = { id, ticket, url: fixture, fixtureTrace };
          fs.writeFileSync(path.join(output, id + '-fixture.json'), JSON.stringify(data, null, 2));
          console.log(JSON.stringify(data));
          continue;
        }
        context = await browser.newContext({ locale: 'en-US' });
        page = await context.newPage();
        page.setDefaultTimeout(5500);
        const op = operations(page, trace);
        started = Date.now();
        await login(page, op);
        await spec.run(page, op, fixture);
        result.verdict = 'passed';
      } catch (error) {
        result.verdict = started ? 'failed' : 'fixture-error';
        result.error = String(error.message).replaceAll(password, '[redacted]').split('\n').slice(0, 8).join('\n');
      } finally {
        result.elapsedSeconds = started ? (Date.now() - started) / 1000 : null;
        result.operations = trace.length;
        if (page && !page.isClosed()) {
          result.lastPage = page.url();
          if (result.lastPage.startsWith(url) && !result.lastPage.endsWith('/login')) {
            const screenshot = path.join(output, id + '.png');
            await page.screenshot({ path: screenshot, mask: [page.locator('input,textarea,[contenteditable]')] }).then(
              () => { result.screenshot = screenshot; }, () => {},
            );
          }
        }
        await context?.close();
      }
      fs.writeFileSync(path.join(output, id + '.json'), JSON.stringify(result, null, 2));
      console.log(JSON.stringify({ id, verdict: result.verdict, operations: result.operations, seconds: result.elapsedSeconds, error: result.error, report: path.join(output, id + '.json') }));
      if (result.verdict !== 'passed') process.exitCode = 1;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1; });
