import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "C:/Users/15936/Desktop/xiao/outputs/sms-template";
await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Sheet1");
sheet.showGridLines = false;

sheet.getRange("A1:D3").values = [
  ["客户手机号", "短信内容变量1", "短信内容变量2", "短信内容变量3"],
  ["+8615936889988", "123456", "", ""],
  ["+8615936882179", "123457", "", ""],
];

sheet.getRange("A1:D1").format = {
  fill: "#EAF3FF",
  font: { bold: true, color: "#1F2937" },
  borders: { preset: "all", style: "thin", color: "#D9E2F3" },
};
sheet.getRange("A2:D3").format = {
  borders: { preset: "all", style: "thin", color: "#E5E7EB" },
};
sheet.getRange("A:D").format.numberFormat = "@";
sheet.getRange("A:D").format.columnWidth = 20;
sheet.getRange("A1:D3").format.rowHeight = 24;
sheet.freezePanes.freezeRows(1);

const inspect = await workbook.inspect({
  kind: "table",
  range: "Sheet1!A1:D3",
  include: "values",
  tableMaxRows: 5,
  tableMaxCols: 4,
});
console.log(inspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 20 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

const preview = await workbook.render({ sheetName: "Sheet1", range: "A1:D3", scale: 2, format: "png" });
await fs.writeFile(`${outputDir}/国内短信群发模板_标准验证码测试.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/国内短信群发模板_标准验证码测试.xlsx`);