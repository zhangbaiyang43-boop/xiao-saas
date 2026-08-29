const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const demoPath = path.join(__dirname, 'owner-experience-card-ab-demo.html');

test('老板体验卡 Demo 包含 A/B 版、正反面与 A6 打印规则', () => {
  const html = fs.readFileSync(demoPath, 'utf8');

  assert.match(html, /data-variant="a"/);
  assert.match(html, /data-variant="b"/);
  assert.match(html, /data-side="front"/);
  assert.match(html, /data-side="back"/);
  assert.match(html, /@page\s*{[^}]*size:\s*A6 portrait/s);
  assert.match(html, /演示二维码占位/);
  assert.match(html, /老板扫码进入Demo工作台/);
  assert.match(html, /进入后生成本次专属顾客点餐码/);
  assert.match(html, /顾客下单 → 商家接单 → 制作完成 → 确认上菜/);
  assert.match(html, /两部手机/);
  assert.match(html, /当前二维码不可扫码，请勿直接印刷/);
});

test('页面没有外部依赖，也不使用不适合销售物料的长横线字符', () => {
  const html = fs.readFileSync(demoPath, 'utf8');

  assert.doesNotMatch(html, /<script[^>]+src=/i);
  assert.doesNotMatch(html, /<link[^>]+rel=["']stylesheet["']/i);
  assert.doesNotMatch(html, /[—–]/);
});
