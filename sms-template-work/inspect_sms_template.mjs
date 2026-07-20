import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const inputPath = "C:/Users/15936/Downloads/国内短信群发模板.xlsx";
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const overview = await workbook.inspect({ kind: "workbook,sheet,table,region", maxChars: 8000, tableMaxRows: 12, tableMaxCols: 12, tableMaxCellChars: 120 });
console.log(overview.ndjson);