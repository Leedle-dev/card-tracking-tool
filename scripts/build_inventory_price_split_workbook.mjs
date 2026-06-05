import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [outputPath, ...inputArgs] = process.argv.slice(2);
if (!outputPath || inputArgs.length % 2 !== 0) {
  throw new Error(
    "Usage: node scripts/build_inventory_price_split_workbook.mjs output.xlsx 'Sheet Name' input.tsv [...]",
  );
}

function parseTsv(text) {
  return text
    .trimEnd()
    .split(/\r?\n/)
    .map((line) => line.split("\t").map((value) => parseCell(value)));
}

function parseCell(value) {
  if (value === "") {
    return null;
  }
  if (/^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }
  return value;
}

function columnName(index) {
  let value = "";
  let current = index + 1;
  while (current > 0) {
    const remainder = (current - 1) % 26;
    value = String.fromCharCode(65 + remainder) + value;
    current = Math.floor((current - 1) / 26);
  }
  return value;
}

function setWidths(sheet, columnCount) {
  for (let index = 0; index < columnCount; index += 1) {
    const width = index < 10 ? 140 : index < 14 ? 120 : 115;
    sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidthPx = width;
  }
}

const workbook = Workbook.create();

for (let index = 0; index < inputArgs.length; index += 2) {
  const sheetName = inputArgs[index];
  const inputPath = inputArgs[index + 1];
  const rows = parseTsv(await fs.readFile(inputPath, "utf8"));
  const sheet = workbook.worksheets.add(sheetName);
  const rowCount = rows.length;
  const columnCount = rows[0]?.length ?? 0;
  const lastColumn = columnName(columnCount - 1);

  sheet.getRange(`A1:${lastColumn}${rowCount}`).values = rows;
  sheet.getRange(`A1:${lastColumn}1`).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
  };
  sheet.getRange(`A1:${lastColumn}${rowCount}`).format.font = { name: "Aptos", size: 10 };
  sheet.getRange(`A1:${lastColumn}${rowCount}`).format.wrapText = true;
  setWidths(sheet, columnCount);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await fs.mkdir(outputPath.split(/[\\/]/).slice(0, -1).join("/") || ".", { recursive: true });
await output.save(outputPath);
console.log(outputPath);
