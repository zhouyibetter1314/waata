// Deterministic UI checks for the 4gaBoards course scenarios.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { parseEnv } = require('node:util');
const { chromium, expect } = require('../apps/web/node_modules/@playwright/test');
const advanced = require('./4gaboards-advanced-plan.cjs');

const root = path.resolve(__dirname, '..');
const url = 'http://127.0.0.1:3000/';
const addProject = '[class*="Projects_headerButtonGroup"] button[class*="Projects_addButton"]';
const account = 'waataadmin';
const password = parseEnv(fs.readFileSync(path.join(root, '.local/4gaboards/.env'), 'utf8'))
  .BOARDS_ADMIN_PASSWORD;
const verifyArg = process.argv.find((arg) => arg.startsWith('--verify-file='));
const savedFixture = verifyArg ? JSON.parse(fs.readFileSync(verifyArg.slice(14), 'utf8')) : null;
const ticket = savedFixture?.ticket ?? new Date().toISOString().replace(/\D/g, '').slice(0, 14);
const output = path.join(root, '.local', '4gaboards', 'acceptance', ticket + (savedFixture ? '-verify' : ''));
const prepareOnly = process.argv.includes('--prepare-only');
const headed = process.argv.includes('--headed');
const advancedModel = process.argv.includes('--advanced-model');
const replayPlan = process.argv.find(arg => arg.startsWith('--advanced-replay='));
const selected = new Set(savedFixture ? [savedFixture.id] : process.argv.slice(2).filter((arg) => !arg.startsWith('--')));
const title = (text) => '[title=' + JSON.stringify(text) + ']';
let batchModel;

async function runActions(id, actions, fallback) {
  for (const step of batchModel?.plan[id] ?? fallback) await actions[step]();
}

function operations(page, trace, limit = 35) {
  const act = async (name, perform) => {
    assert(trace.length < limit, 'Course action limit reached');
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
    upload: (locator, file) => act('select local test archive', () => locator.setInputFiles(file)),
    dragBefore: (second, first) => act('drag second card above first', async () => {
      const a = await second.boundingBox();
      const b = await first.boundingBox();
      assert(a && b, 'Both cards must be visible');
      await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
      await page.mouse.down();
      try {
        // Cross the drag sensor threshold, then land comfortably within the target.
        await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2 - 8, {steps: 3});
        await page.mouse.move(b.x + b.width / 2, b.y + Math.min(8, b.height / 4), {steps: 15});
        await page.waitForTimeout(250);
      } finally {
        await page.mouse.up();
      }
    }),
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
    prepare: async () => url,
    async run(page, op) {
      const project = name('B01 Release Lab');
      if (!savedFixture) await newProject(page, op, project);
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
      await op.visit(savedFixture ? boardUrl.url : boardUrl);
      const list = listTitle(page, name('B05 Inbox')).locator('xpath=ancestor::*[contains(@class,"List_innerWrapper")][1]');
      const card = name('B05 Confirm delivery');
      if (!savedFixture) {
        await op.click('open Add Card in Inbox', list.locator('button[class*="List_addCardButton"]'));
        const form = nameForm(page, 'textarea');
        await op.fill('fill card title', form.locator('textarea[name=name]'), card);
        await op.click('submit new card', form.locator('button[type=submit]'));
      }
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

const cardTitle = (page, text) => page.locator('[class*="Card_name"]' + title(text));
const listRow = (page, text) => page.locator('[class*="List_innerWrapper"]').filter({has: listTitle(page, text)});
const byTitle = (page, text) => page.locator('button' + title(text));
async function newCard(page, op, list, card) {
  const row = listRow(page, list);
  const form = row.locator('form').filter({has: page.locator('textarea[name="name"]:visible')});
  if (!(await form.locator('textarea[name=name]').isVisible())) {
    await op.click('open Add card', row.locator('button[class*="List_addCardButton"]'));
  }
  await op.fill('card title', form.locator('textarea[name=name]'), card);
  await op.click('save card', form.locator('button[type=submit]'));
  await expect(cardTitle(page, card)).toBeVisible();
}
async function openCard(page, op, card) {
  const saved = page.locator('div[class*="Card_content__"]').filter({has: cardTitle(page, card)});
  await op.click('open saved card', saved);
  await page.waitForURL('**/cards/*');
}

for (const [id, boardName, listName, cardName] of [
  ['B06', 'Notes', 'Queue', 'Handover'], ['B07', 'Search', 'Queue', 'Quartz queue'],
  ['B08', 'Labels', 'Queue', 'Red parcel'], ['B09', 'Work', 'Pending', 'Verify totals'],
  ['B10', 'Requests', 'Queue', 'Inspect parcel'],
]) {
  const board = name(id + ' ' + boardName);
  const list = name(id + ' ' + listName);
  const card = name(id + ' ' + cardName);
  const other = name(id + (id === 'B07' ? ' Amber queue' : ' Blue parcel'));
  const label = name('B08 Priority');
  const destination = name(id === 'B09' ? 'B09 Reviewed' : 'B10 Received');
  const secondBoard = name('B10 Fulfilment');
  specs[id] = {
    async prepare(page, op) {
      const projectUrl = await newProject(page, op, name(id + ' Fixture'));
      const source = await newBoard(page, op, board);
      await newList(page, op, list);
      await newCard(page, op, list, card);
      if (id === 'B07' || id === 'B08') await newCard(page, op, list, other);
      if (id === 'B08') {
        await openCard(page, op, card);
        const cardId = new URL(page.url()).pathname.split('/').at(-1);
        const token = (await page.context().cookies(url)).find((c) => c.name === 'accessToken')?.value;
        assert(token, 'Missing authorized fixture session');
        async function seed(route, data) {
          const response = await page.request.post(url + 'api/' + route,
            {data, headers:{Authorization:'Bearer ' + token}});
          assert(response.ok(), 'Label fixture setup failed: ' + response.status());
          return (await response.json()).item;
        }
        const item = await seed('boards/' + new URL(source).pathname.split('/').at(-1) + '/labels',
          {name:label, color:'berry-red'});
        await seed('cards/' + cardId + '/labels', {labelId:item.id});
      }
      if (id === 'B09') await newList(page, op, destination);
      let destinationUrl;
      if (id === 'B10') {
        await op.visit(projectUrl);
        destinationUrl = await newBoard(page, op, secondBoard);
        await newList(page, op, destination);
      }
      return {url: source, destinationUrl, board, list, card, other, label, destination, secondBoard};
    },
    async run(page, op, fixture) {
      await op.visit(fixture.url);
      if (id === 'B06') {
        await openCard(page, op, card);
        const cardUrl = page.url();
        if (!savedFixture) {
          await op.click('open description editor', page.locator('button[class*="CardModal_descriptionButton__"]'));
          const editor = page.getByPlaceholder('Enter description...', {exact:true});
          await op.fill('fill description', editor, 'Confirm pickup at the north desk.');
          await op.click('save description', button(page, 'Save'));
          await expect(page.getByText('Confirm pickup at the north desk.', {exact:true})).toBeVisible();
          await op.visit(fixture.url);
          await op.visit(cardUrl);
        }
        await expect(page.getByText('Confirm pickup at the north desk.', {exact:true})).toBeVisible();
        await expect(page.locator('button[class*="CardModal_descriptionText__"]')).toHaveText(
          'Confirm pickup at the north desk.');
        await expect(page.locator('[class*="CardModal_headerTitle__"]')).toHaveText(card);
      } else if (id === 'B07' || id === 'B08') {
        await expect(cardTitle(page, other)).toBeVisible();
        if (id === 'B07') {
          await op.fill('filter card text', page.getByPlaceholder('Filter cards...'), 'Quartz');
        } else {
          await op.click('open label filter', byTitle(page, 'Filter By Labels'));
          await op.click('select label', page.locator('span[class*="Item_name__"]' + title(label)));
          await op.click('close filter picker', byTitle(page, 'Filter By Labels'));
          await expect(page.locator('[class*="Filters_filterItem"]:has(:text-is(' + JSON.stringify(label) + '))')).toHaveCount(1);
        }
        await expect(cardTitle(page, card)).toBeVisible();
        await expect(cardTitle(page, other)).toHaveCount(0);
      } else if (id === 'B09') {
        const field = page.locator('[class*="CardModal_headerListField__"]');
        if (!savedFixture) {
          await openCard(page, op, card);
          await op.click('open list picker', field);
          await op.click('select destination list', page.locator('[class*="Dropdown_dropdownItem"][name=' + JSON.stringify(destination) + ']'));
          await expect(field).toHaveText(destination);
          await op.visit(fixture.url);
        }
        await expect(listTitle(page, list)).toBeVisible();
        await expect(listTitle(page, destination)).toBeVisible();
        await expect(listRow(page, list).locator(cardTitle(page, card))).toHaveCount(0);
        await expect(listRow(page, destination).locator(cardTitle(page, card))).toHaveCount(1);
        await openCard(page, op, card);
        await expect(field).toHaveText(destination);
      } else {
        if (!savedFixture) {
        await op.click('open edit card menu', byTitle(page, 'Edit Card'));
        await op.click('open Move Card', button(page, 'Move Card'));
        await op.click('open board picker', page.locator('input[name=boardId]'));
        await op.click('choose destination board', page.locator('[class*="Dropdown_dropdownItem"][name=' + JSON.stringify(secondBoard) + ']'));
        await op.click('open destination list picker', page.locator('input[name=listId]'));
        await op.click('choose destination list', page.locator('[class*="Dropdown_dropdownItem"][name=' + JSON.stringify(destination) + ']'));
        await op.click('confirm Move', button(page, 'Move'));
        await op.visit(fixture.url);
        }
        await expect(listTitle(page, list)).toBeVisible();
        await expect(cardTitle(page, card)).toHaveCount(0);
        await page.screenshot({path:path.join(output, 'B10-source.png'), mask:[page.locator('input,textarea,[contenteditable]')]});
        await op.visit(fixture.destinationUrl);
        await expect(listRow(page, destination).locator(cardTitle(page, card))).toHaveCount(1);
      }
    },
  };
}

const archive = path.join(output, 'B12-board.tgz');
const ready = name('B12 Ready');
const archiveCard = name('B12 Archive item');
specs.B11 = {
  async prepare(page, op) {
    await newProject(page, op, name('B11 Fixture'));
    const board = await newBoard(page, op, name('B11 Sequence'));
    const list = name('B11 Queue');
    await newList(page, op, list);
    await newCard(page, op, list, name('B11 First parcel'));
    await newCard(page, op, list, name('B11 Second parcel'));
    return board;
  },
  async run(page, op, board) {
    const first = name('B11 First parcel');
    const second = name('B11 Second parcel');
    const cards = listRow(page, name('B11 Queue')).locator('[class*="Card_name"][title]');
    const names = () => cards.evaluateAll((items) => items.map((el) => el.title));
    await op.visit(board);
    await expect.poll(names).toEqual([first, second]);
    const persisted = (text) => page.locator('div[class*="Card_content__"]').filter({has:cardTitle(page, text)});
    const reverse = 'drag Second parcel before First parcel';
    await runActions('B11', {
      [reverse]: () => op.dragBefore(persisted(second), persisted(first)),
      'drag First parcel before Second parcel': () => op.dragBefore(persisted(first), persisted(second)),
    }, [reverse]);
    await expect.poll(names).toEqual([second, first]);
    await op.reload();
    await expect.poll(names).toEqual([second, first]);
    return { initialOrder: [first, second], reloadedOrder: await names() };
  },
};
specs.B12 = {
  async prepare(page, op) {
    await newProject(page, op, name('B12 Fixture'));
    const board = await newBoard(page, op, name('B12 Sample Export'));
    await newList(page, op, ready);
    await newCard(page, op, ready, archiveCard);
    return board;
  },
  async run(page, op, board) {
    await op.visit(board);
    const link = page.locator('a[href=' + JSON.stringify(new URL(board).pathname) + ']').first();
    const row = link.locator('xpath=ancestor::div[.//button[@title="Edit Board"]][1]');
    const option = page.getByText(/skip attachments/i).locator('..');
    const checkbox = option.locator('input[type=checkbox]');
    let download;
    const actions = {
      'open board settings': async () => {
        await row.hover();
        await op.click('open Edit Board', row.locator('button[title="Edit Board"]'));
      },
      'open export options': () => op.click('open Export Board', button(page, 'Export Board')),
      'skip attachments': () => op.click('skip attachments', checkbox),
      'submit export': async () => {
        await expect(checkbox).toBeChecked();
        [download] = await Promise.all([page.waitForEvent('download', {timeout:8000}),
          op.click('export archive', button(page, 'Export Board'))]);
      },
    };
    await runActions('B12', actions, Object.keys(actions));
    assert(download.suggestedFilename().endsWith('.tgz'));
    await download.saveAs(archive);
    const size = fs.statSync(archive).size;
    assert(size > 0 && size <= 2 * 1024 * 1024);
    const entries = execFileSync('tar', ['-tzf', archive], {encoding:'utf8', timeout:4000, maxBuffer:65000});
    const members = entries.trim().split(/\r?\n/);
    for (const required of ['boards.csv', 'lists.csv', 'cards.csv']) {
      assert(members.includes(required), `Missing archive member: ${required}`);
    }
    return {
      skipAttachments: true,
      archive: path.basename(archive),
      bytes: size,
      sha256: createHash('sha256').update(fs.readFileSync(archive)).digest('hex'),
      members,
    };
  },
};
specs.B13 = {
  prepare: (page, op) => newProject(page, op, name('B13 Import Lab')),
  async run(page, op, project) {
    assert(fs.existsSync(archive), 'Run B12 first in this offline batch');
    await op.visit(project);
    const boardName = name('B13 Restored Board');
    const actions = {
      'open add-board form': () => op.click('open Add Board', page.locator('div[class*="Boards_headerButtonGroup"] button[title="Add Board"]')),
      'enter board name': () => op.fill('board name', page.locator('input[name=name]'), boardName),
      'open import options': () => op.click('open Import', byTitle(page, 'Import')),
      'attach registered archive': () => op.upload(page.locator('input[type=file][accept=".tgz"]'), archive),
      'submit import': () => op.click('submit import', button(page, 'Import Board')),
    };
    await runActions('B13', actions, Object.keys(actions));
    await page.waitForURL('**/boards/*');
    const importedUrl = page.url();
    await expect(page.getByText(boardName, {exact:true}).first()).toBeVisible();
    await expect(listRow(page, ready).locator(cardTitle(page, archiveCard))).toHaveCount(1);
    await op.visit(project);
    await expect(page.locator('a[href=' + JSON.stringify(new URL(importedUrl).pathname) + ']').filter({
      has: page.getByText(boardName, {exact:true}),
    }).first()).toBeVisible();
    await op.visit(importedUrl);
    await expect(listRow(page, ready).locator(cardTitle(page, archiveCard))).toHaveCount(1);
    await op.reload();
    await expect(page.getByText(boardName, {exact:true}).first()).toBeVisible();
    await expect(listRow(page, ready).locator(cardTitle(page, archiveCard))).toHaveCount(1);
    return { project, importedUrl, boardName, restoredList: ready, restoredCard: archiveCard };
  },
};

async function main() {
  fs.mkdirSync(output, { recursive: true });
  if (replayPlan) {
    assert(!advancedModel && !prepareOnly && !savedFixture && selected.size === 1 && selected.has('B11'),
      '--advanced-replay only replays B11 from a saved model plan');
    const recorded = JSON.parse(fs.readFileSync(replayPlan.slice('--advanced-replay='.length), 'utf8'));
    batchModel = {model: recorded.model, requests: 0, tokens: 0, plan: advanced.validate({B11: recorded.plan.B11}, ['B11']), replay: true};
    fs.writeFileSync(path.join(output, 'model-plan.json'), JSON.stringify(batchModel, null, 2));
  }
  if (advancedModel) {
    const ids = [...selected].sort();
    assert(!prepareOnly && !savedFixture && ['B11', 'B11,B12,B13'].includes(ids.join(',')),
      '--advanced-model requires B11 alone or all of B11 B12 B13');
    batchModel = await advanced.propose(path.join(root, '.env'), ids);
    fs.writeFileSync(path.join(output, 'model-plan.json'), JSON.stringify(batchModel, null, 2));
    console.log(JSON.stringify({kind: 'shared model request', model: batchModel.model, requests: 1, tokens: batchModel.tokens}));
  }
  const browser = await chromium.launch({
    executablePath: process.env.WAATA_BROWSER_EXECUTABLE || undefined,
    downloadsPath: output,
    headless: !headed,
    slowMo: headed ? 180 : 0,
  });
  try {
    for (const [id, spec] of Object.entries(specs)) {
      if (selected.size && !selected.has(id)) continue;
      if (prepareOnly && !spec.prepare) continue;
      const fixtureTrace = [];
      const trace = [];
      const result = { id, kind: batchModel?.replay ? 'saved model plan replay + local Playwright' : batchModel ? 'real model plan + local Playwright' : savedFixture ? 'independent verification' : 'scripted UI', ticket, tokens: batchModel && !batchModel.replay ? null : 0, fixtureTrace, trace };
      if (batchModel) result.modelPlan = {model: batchModel.model, sharedReceipt: 'model-plan.json', actions: batchModel.plan[id]};
      let context;
      let page;
      let started;
      try {
        let fixture = savedFixture;
        if (spec.prepare && !savedFixture) {
          context = await browser.newContext({ locale: 'en-US' });
          page = await context.newPage();
          page.setDefaultTimeout(5500);
          const setup = operations(page, fixtureTrace);
          await login(page, setup);
          fixture = await spec.prepare(page, setup);
          await context.close();
        }
        if (prepareOnly) {
          const data = { id, ticket, ...(typeof fixture === 'string' ? {url:fixture} : fixture), fixtureTrace };
          fs.writeFileSync(path.join(output, id + '-fixture.json'), JSON.stringify(data, null, 2));
          console.log(JSON.stringify(data));
          continue;
        }
        context = await browser.newContext({ locale: 'en-US' });
        page = await context.newPage();
        page.setDefaultTimeout(5500);
        const scenarioLimit = {B11:10, B12:13, B13:17}[id];
        const op = operations(page, trace, scenarioLimit);
        started = Date.now();
        await login(page, op);
        const checks = await spec.run(page, op, fixture);
        if (checks) result.checks = checks;
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
