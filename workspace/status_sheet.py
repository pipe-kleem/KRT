"""Rig & Model Status -> production tracker sheet (.xlsx, opens in Excel and imports into Google Sheets).

Pure Python (zipfile + XML) - no extra packages. One tab per asset type. Columns:
    CH | DRAFT 1 | DRAFT 2 | HAIR/CLOTH STATUS | MasterModel Date-Time | Ready for RIG | RIG STATUS DRAFT 1 |
    RIG STATUS DRAFT 2 | Rigging_Date:Time
Status cells are drop-downs (DONE / WIP / Not Ready) coloured by value. Values KRT can know are filled in:
    Ready for RIG = DONE when the model exists, MasterModel Date-Time = model date,
    RIG STATUS DRAFT 1 = DONE (rig up to date) / WIP (rig older than the model) / Not Ready (no rig), Rigging_Date:Time = rig date.
The drafts and hair/cloth columns stay "Not Ready" for the team to fill in.
"""
import os
import time
import zipfile
from xml.sax.saxutils import escape

HEADERS = ["CH", "DRAFT 1", "DRAFT 2", "HAIR/CLOTH STATUS", "MasterModel Date-Time", "Ready for RIG",
           "RIG STATUS DRAFT 1", "RIG STATUS DRAFT 2", "Rigging_Date:Time"]
_TAB_NAMES = {"characters": "CH", "props": "PROPS", "locations": "LOCATIONS"}
_HEAD_NAMES = {"characters": "CH", "props": "PROP", "locations": "LOC"}
_WIDTHS = [28, 14, 14, 22, 24, 16, 22, 22, 22]


def _col(i):
    return "ABCDEFGHIJ"[i]


def _fmt(t):
    return time.strftime("%d-%m-%Y", time.localtime(t)) if t else ""


def _row_values(r):
    has_model = bool(r.get("model") or r.get("cc"))
    st = r.get("state")
    if not r.get("rig"):
        rig = "Not Ready"
    elif st == "old":
        rig = "WIP"
    else:
        rig = "DONE"
    return ["Not Ready", "Not Ready", "Not Ready", _fmt(max(r.get("model_t", 0), 0)),
            "DONE" if has_model else "Not Ready", rig, "Not Ready", _fmt(r.get("rig_t", 0))]


def _cell(ref, text, style, num=False):
    if text == "" or text is None:
        return '<c r="%s" s="%d"/>' % (ref, style)
    return '<c r="%s" s="%d" t="inlineStr"><is><t>%s</t></is></c>' % (ref, style, escape(str(text)))


def _sheet_xml(asset_type, rows):
    n = len(rows) + 1
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<dimension ref="A1:I%d"/>' % n,
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
           '<sheetFormatPr defaultRowHeight="18"/>', '<cols>']
    for i, w in enumerate(_WIDTHS, 1):
        out.append('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i, i, w))
    out.append('</cols><sheetData>')
    head = list(HEADERS)
    head[0] = _HEAD_NAMES.get(asset_type, (asset_type or "CH").upper())
    out.append('<row r="1" ht="22" customHeight="1">' + "".join(_cell("%s1" % _col(i), h, 1) for i, h in enumerate(head)) + '</row>')
    for k, r in enumerate(rows, 2):
        vals = _row_values(r)
        # CH cell: light blue; light red when the rig is older than the model
        ch_style = 3 if r.get("state") == "old" else 2
        cells = [_cell("A%d" % k, r["asset"], ch_style)]
        for i, v in enumerate(vals, 1):
            cells.append(_cell("%s%d" % (_col(i), k), v, 4))
        out.append('<row r="%d">%s</row>' % (k, "".join(cells)))
    out.append('</sheetData>')
    out.append('<autoFilter ref="A1:I%d"/>' % n)
    last = max(n, 2) + 500            # room to add more rows with the same drop-downs
    rng = "B2:D%d F2:H%d" % (last, last)
    for pr, dxf in (('"DONE"', 0), ('"Not Ready"', 1), ('"WIP"', 2)):
        out.append('<conditionalFormatting sqref="%s"><cfRule type="cellIs" dxfId="%d" priority="%d" operator="equal"><formula>%s</formula></cfRule></conditionalFormatting>'
                   % (rng, dxf, dxf + 1, pr.replace('"', '&quot;')))
    out.append('<dataValidations count="1"><dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="%s">'
               '<formula1>"DONE,WIP,Not Ready"</formula1></dataValidation></dataValidations>' % rng)
    out.append('</worksheet>')
    return "".join(out)


_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<fonts count="3"><font><sz val="10"/><name val="Arial"/></font>'
           '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>'
           '<font><b/><sz val="10"/><name val="Arial"/></font></fonts>'
           '<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
           '<fill><patternFill patternType="solid"><fgColor rgb="FF434343"/></patternFill></fill>'
           '<fill><patternFill patternType="solid"><fgColor rgb="FFCFE2F3"/></patternFill></fill>'
           '<fill><patternFill patternType="solid"><fgColor rgb="FFEA9999"/></patternFill></fill></fills>'
           '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
           '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
           '<cellXfs count="5">'
           '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
           '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
           '<xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
           '<xf numFmtId="0" fontId="2" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
           '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center"/></xf>'
           '</cellXfs>'
           '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
           '<dxfs count="3">'
           '<dxf><font><b/><color rgb="FFFFFFFF"/></font><fill><patternFill patternType="solid"><fgColor rgb="FF0B8043"/><bgColor rgb="FF0B8043"/></patternFill></fill></dxf>'
           '<dxf><font><color rgb="FFFFFFFF"/></font><fill><patternFill patternType="solid"><fgColor rgb="FF434343"/><bgColor rgb="FF434343"/></patternFill></fill></dxf>'
           '<dxf><font><color rgb="FF1155CC"/></font><fill><patternFill patternType="solid"><fgColor rgb="FFCFE2F3"/><bgColor rgb="FFCFE2F3"/></patternFill></fill></dxf>'
           '</dxfs></styleSheet>')


def write_xlsx(path, rows):
    """rows: dicts from status_page.scan_project. One tab per asset type. -> path"""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("type") or "assets", []).append(r)
    if not groups:
        groups = {"characters": []}
    order = sorted(groups, key=lambda t: (t != "characters", t))
    names, used = [], set()
    for t in order:
        nm = _TAB_NAMES.get(t, t.upper())[:28]
        base, i = nm, 2
        while nm in used:
            nm = "%s_%d" % (base[:25], i)
            i += 1
        used.add(nm)
        names.append(nm)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i, nm in enumerate(names, 1):
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i)
        wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(nm), i, i))
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i, i))
    rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' % (len(names) + 1))
    ct.append('</Types>')
    wb.append('</sheets></workbook>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", _STYLES)
        for i, t in enumerate(order, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, _sheet_xml(t, sorted(groups[t], key=lambda r: r["asset"].lower())))
    return path
