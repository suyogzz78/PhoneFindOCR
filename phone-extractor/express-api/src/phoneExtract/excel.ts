import ExcelJS from 'exceljs';

/** Build an .xlsx with one "Phone" column. Numbers are stored as text so Excel never mangles them. */
export async function buildPhonesWorkbook(
  phones: string[],
  failedPages: number[] = [],
): Promise<Buffer> {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet('Phones');
  ws.columns = [{ header: 'Phone', key: 'phone', width: 18, style: { numFmt: '@' } }];
  ws.getRow(1).font = { bold: true };
  for (const phone of phones) ws.addRow({ phone });

  if (failedPages.length > 0) {
    const notes = wb.addWorksheet('Notes');
    notes.getColumn(1).width = 90;
    notes.addRow(['Failed pages: ' + failedPages.join(', ')]);
    notes.getRow(1).font = { bold: true, color: { argb: 'FFFF0000' } };
  }
  return Buffer.from(await wb.xlsx.writeBuffer());
}
   