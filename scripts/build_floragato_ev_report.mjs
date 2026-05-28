import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputPath = "reports/grading_ev/floragato_ev_report.xlsx";

const assumptions = {
  targetCard: "Simplified Chinese Gem Pack Vol. 5 Floragato 2207/07 Triple Rare",
  probabilityPrior: "Japanese Night Wanderer Houndoom 066/064 BGS population snapshot",
  valueCurve: "User-provided S-Chinese Floragato graded value estimates",
  rawSalePrice: 32.50,
  rawMarketplaceFeeRate: 0.1325,
  bgsGradingFee: 15.00,
  inboundShippingAllocation: 1.25,
  returnShippingAllocation: 2.00,
  gradedSaleShipping: 5.00,
  gradedMarketplaceFeeRate: 0.1325,
};

const gradeRows = [
  ["BGS 7", 0.000, 0, 32.50, 5.00, null, "Fallback to raw value", "Below-BGS-9 outcome uses raw estimate"],
  ["BGS 7.5", 0.010, 1, 32.50, 5.00, null, "Fallback to raw value", "Below-BGS-9 outcome uses raw estimate"],
  ["BGS 8", 0.000, 0, 32.50, 5.00, null, "Fallback to raw value", "Below-BGS-9 outcome uses raw estimate"],
  ["BGS 8.5", 0.000, 0, 32.50, 5.00, null, "Fallback to raw value", "Below-BGS-9 outcome uses raw estimate"],
  ["BGS 9", 0.057, 6, 45.00, 5.00, null, "Manual BGS 9 estimate", "User-provided estimate"],
  ["BGS 9.5", 0.733, 77, 65.00, 5.00, null, "Manual BGS 9.5 estimate", "User-provided estimate"],
  ["BGS 10 Pristine", 0.181, 19, 250.00, 5.00, null, "Manual BGS 10 estimate", "User-provided estimate"],
  ["BGS 10 Black Label", 0.019, 2, 2500.00, 5.00, null, "Manual BGS Black Label estimate", "User-provided estimate"],
];

const sourceRows = [
  ["Raw S-Chinese Floragato sale baseline", "Manual scenario input", "$32.50", "User-provided baseline for raw S-Chinese Floragato triple rare"],
  ["Japanese BGS population prior", "GemRate public Beckett-style table", "105 total BGS submissions", "Japanese Houndoom used as closest current print-quality prior"],
  ["Below BGS 9 fallback", "Manual scenario rule", "$32.50", "BGS 7 through BGS 8.5 use raw value as fallback"],
  ["BGS 9", "Manual scenario input", "$45.00", "User-provided Floragato estimate"],
  ["BGS 9.5", "Manual scenario input", "$65.00", "User-provided Floragato estimate"],
  ["BGS 10", "Manual scenario input", "$250.00", "User-provided Floragato estimate"],
  ["BGS Black Label", "Manual scenario input", "$2,500.00", "User-provided Floragato estimate"],
  ["Graded sale shipping", "Manual scenario input", "$5.00", "Added to graded sale total before marketplace fee"],
  ["BGS Bulk profile", "Local grading profile", "$18.25 total cost", "$15 grading + $1.25 inbound + $2 return"],
];

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidthPx = width;
  });
}

function header(range) {
  range.format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
  };
}

function moneyRange(sheet, address) {
  sheet.getRange(address).format.numberFormat = "$#,##0.00";
}

function pctRange(sheet, address) {
  sheet.getRange(address).format.numberFormat = "0.0%";
}

await fs.mkdir("reports/grading_ev", { recursive: true });

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const detail = workbook.worksheets.add("Grade Detail");
const sources = workbook.worksheets.add("Sources");

summary.getRange("A1").values = [["Floragato Grading EV Report"]];
summary.getRange("A1:F1").merge();
summary.getRange("A1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF", size: 16 },
};

summary.getRange("A3:B13").values = [
  ["Target card", assumptions.targetCard],
  ["Probability prior", assumptions.probabilityPrior],
  ["Value curve", assumptions.valueCurve],
  ["Raw sale price", assumptions.rawSalePrice],
  ["Raw marketplace fee rate", assumptions.rawMarketplaceFeeRate],
  ["Raw net", null],
  ["BGS grading fee", assumptions.bgsGradingFee],
  ["Inbound shipping allocation", assumptions.inboundShippingAllocation],
  ["Return shipping allocation", assumptions.returnShippingAllocation],
  ["Total grading cost", null],
  ["Graded sale shipping", assumptions.gradedSaleShipping],
];
summary.getRange("B8").formulas = [["=B6*(1-B7)"]];
summary.getRange("B12").formulas = [["=SUM(B9:B11)"]];

summary.getRange("D3:E8").values = [
  ["Expected graded gross", null],
  ["Expected graded selling fees", null],
  ["Expected graded net", null],
  ["Expected raw net", null],
  ["EV delta", null],
  ["Direction", null],
];
summary.getRange("E3").formulas = [["='Grade Detail'!I12"]];
summary.getRange("E4").formulas = [["='Grade Detail'!J12"]];
summary.getRange("E5").formulas = [["=E3-E4-B12"]];
summary.getRange("E6").formulas = [["=B8"]];
summary.getRange("E7").formulas = [["=E5-E6"]];
summary.getRange("E8").formulas = [["=IF(E7>0,\"Positive\",IF(E7<0,\"Negative\",\"Breakeven\"))"]];

summary.getRange("A15:A21").values = [
  ["Interpretation"],
  ["This is a first-pass model, not a final grading recommendation."],
  ["The S-Chinese card uses Japanese Houndoom BGS grade rates as a proxy because direct Chinese population data is sparse."],
  ["The model is strongly positive under the supplied manual value assumptions."],
  ["The EV is highly sensitive to the BGS 10 and Black Label price estimates."],
  ["There is no public pricing data in this scenario; values should be treated as editable assumptions."],
  ["Below-BGS-9 outcomes currently fall back to raw value rather than a lower-grade discount."],
];
summary.getRange("A15:F15").merge();
summary.getRange("A16:F21").merge(true);

header(summary.getRange("A3:B3"));
header(summary.getRange("D3:E3"));
moneyRange(summary, "B6:B6");
moneyRange(summary, "B8:B13");
pctRange(summary, "B7:B7");
moneyRange(summary, "E3:E7");
setWidths(summary, [210, 560, 30, 230, 150, 40]);

detail.getRange("A1:K1").values = [[
  "Grade outcome",
  "Probability",
  "Population count",
  "Item price",
  "Shipping",
  "Sale total",
  "Value source",
  "Notes",
  "Expected gross contribution",
  "Fee contribution",
  "Expected net before grading cost",
]];
header(detail.getRange("A1:K1"));
detail.getRange("A2:H9").values = gradeRows;
detail.getRange("F2:F9").formulas = gradeRows.map((_, index) => [`=D${index + 2}+E${index + 2}`]);
detail.getRange("I2:I9").formulas = gradeRows.map((_, index) => [`=B${index + 2}*F${index + 2}`]);
detail.getRange("J2:J9").formulas = gradeRows.map((_, index) => [`=I${index + 2}*Summary!$B$7`]);
detail.getRange("K2:K9").formulas = gradeRows.map((_, index) => [`=I${index + 2}-J${index + 2}`]);
detail.getRange("H12:K12").values = [["Totals", null, null, null]];
detail.getRange("I12").formulas = [["=SUM(I2:I9)"]];
detail.getRange("J12").formulas = [["=SUM(J2:J9)"]];
detail.getRange("K12").formulas = [["=SUM(K2:K9)"]];

pctRange(detail, "B2:B9");
moneyRange(detail, "D2:F9");
moneyRange(detail, "I2:K12");
setWidths(detail, [150, 105, 115, 105, 90, 105, 260, 380, 180, 145, 190]);
detail.getRange("A1:K12").format.wrapText = true;

const chartDataStart = 14;
detail.getRange(`A${chartDataStart}:B${chartDataStart}`).values = [["Grade outcome", "Expected gross"]];
detail.getRange(`A${chartDataStart + 1}:A${chartDataStart + gradeRows.length}`).formulas =
  gradeRows.map((_, index) => [`=A${index + 2}`]);
detail.getRange(`B${chartDataStart + 1}:B${chartDataStart + gradeRows.length}`).formulas =
  gradeRows.map((_, index) => [`=I${index + 2}`]);
const chart = detail.charts.add("bar", detail.getRange(`A${chartDataStart}:B${chartDataStart + gradeRows.length}`));
chart.title = "Expected Gross Contribution by Grade";
chart.hasLegend = false;
chart.xAxis = { axisType: "textAxis" };
chart.yAxis = { numberFormatCode: "$#,##0" };
chart.setPosition("D14", "K30");

sources.getRange("A1:D1").values = [["Input", "Source", "Value", "Notes"]];
header(sources.getRange("A1:D1"));
sources.getRange(`A2:D${sourceRows.length + 1}`).values = sourceRows;
setWidths(sources, [260, 280, 180, 560]);
sources.getRange(`A1:D${sourceRows.length + 1}`).format.wrapText = true;

for (const sheet of [summary, detail, sources]) {
  sheet.getRange("A1:K40").format.font = { name: "Aptos", size: 10 };
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
const summaryPreview = await workbook.render({
  sheetName: "Summary",
  autoCrop: "all",
  scale: 1,
  format: "png",
});
await fs.writeFile(
  "reports/grading_ev/floragato_ev_report_summary_preview.png",
  new Uint8Array(await summaryPreview.arrayBuffer()),
);
const detailPreview = await workbook.render({
  sheetName: "Grade Detail",
  autoCrop: "all",
  scale: 1,
  format: "png",
});
await fs.writeFile(
  "reports/grading_ev/floragato_ev_report_detail_preview.png",
  new Uint8Array(await detailPreview.arrayBuffer()),
);
console.log(outputPath);
