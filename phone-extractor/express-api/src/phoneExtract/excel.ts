import ExcelJS from 'exceljs';

/** Build an .xlsx with one "Phone" column. Numbers are stored as text so Excel never mangles them. */
export async function buildPhonesWorkbook(phones: string[]): Promise<Buffer> {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet('Phones');
  ws.columns = [{ header: 'Phone', key: 'phone', width: 18, style: { numFmt: '@' } }];
  ws.getRow(1).font = { bold: true };
  for (const phone of phones) ws.addRow({ phone });
  return Buffer.from(await wb.xlsx.writeBuffer());
}
   