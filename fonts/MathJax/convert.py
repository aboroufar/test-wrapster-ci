#!/usr/bin/env python3
#

# require
# `pip install fonttools`
#

import io
import struct
import sys
import zlib
from urllib.request import urlopen
from fontTools.ttLib import TTFont

# MathJax woff fonts
BASE_URL = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2"
SRC_MAP = {
    "MJXZERO": "MathJax_Zero.woff",
    "MJXTEX": "MathJax_Main-Regular.woff",
    "MJXTEX-B": "MathJax_Main-Bold.woff",
    "MJXTEX-I": "MathJax_Math-Italic.woff",
    "MJXTEX-MI": "MathJax_Main-Italic.woff",
    "MJXTEX-BI": "MathJax_Math-BoldItalic.woff",
    "MJXTEX-S1": "MathJax_Size1-Regular.woff",
    "MJXTEX-S2": "MathJax_Size2-Regular.woff",
    "MJXTEX-S3": "MathJax_Size3-Regular.woff",
    "MJXTEX-S4": "MathJax_Size4-Regular.woff",
    "MJXTEX-A": "MathJax_AMS-Regular.woff",
    "MJXTEX-C": "MathJax_Calligraphic-Regular.woff",
    "MJXTEX-CB": "MathJax_Calligraphic-Bold.woff",
    "MJXTEX-FR": "MathJax_Fraktur-Regular.woff",
    "MJXTEX-FRB": "MathJax_Fraktur-Bold.woff",
    "MJXTEX-SS": "MathJax_SansSerif-Regular.woff",
    "MJXTEX-SSB": "MathJax_SansSerif-Bold.woff",
    "MJXTEX-SSI": "MathJax_SansSerif-Italic.woff",
    "MJXTEX-SC": "MathJax_Script-Regular.woff",
    "MJXTEX-T": "MathJax_Typewriter-Regular.woff",
    "MJXTEX-V": "MathJax_Vector-Regular.woff",
    "MJXTEX-VB": "MathJax_Vector-Bold.woff",
}


def convert_streams(infile: io.BytesIO, outfile: io.BufferedWriter) -> None:
    """Convert a WOFF font stream to an OTF font stream."""
    woff_header = {
        "signature": struct.unpack(">I", infile.read(4))[0],
        "flavor": struct.unpack(">I", infile.read(4))[0],
        "length": struct.unpack(">I", infile.read(4))[0],
        "numTables": struct.unpack(">H", infile.read(2))[0],
        "reserved": struct.unpack(">H", infile.read(2))[0],
        "totalSfntSize": struct.unpack(">I", infile.read(4))[0],
        "majorVersion": struct.unpack(">H", infile.read(2))[0],
        "minorVersion": struct.unpack(">H", infile.read(2))[0],
        "metaOffset": struct.unpack(">I", infile.read(4))[0],
        "metaLength": struct.unpack(">I", infile.read(4))[0],
        "metaOrigLength": struct.unpack(">I", infile.read(4))[0],
        "privOffset": struct.unpack(">I", infile.read(4))[0],
        "privLength": struct.unpack(">I", infile.read(4))[0],
    }

    outfile.write(struct.pack(">I", woff_header["flavor"]))
    outfile.write(struct.pack(">H", woff_header["numTables"]))
    maximum = list(
        filter(
            lambda x: x[1] <= woff_header["numTables"], [(n, 2**n) for n in range(64)]
        )
    )[-1]
    search_range = maximum[1] * 16
    outfile.write(struct.pack(">H", search_range))
    entry_selector = maximum[0]
    outfile.write(struct.pack(">H", entry_selector))
    range_shift = woff_header["numTables"] * 16 - search_range
    outfile.write(struct.pack(">H", range_shift))

    offset = outfile.tell()

    table_directory_entries = []
    for _i in range(0, woff_header["numTables"]):
        table_directory_entries.append(
            {
                "tag": struct.unpack(">I", infile.read(4))[0],
                "offset": struct.unpack(">I", infile.read(4))[0],
                "compLength": struct.unpack(">I", infile.read(4))[0],
                "origLength": struct.unpack(">I", infile.read(4))[0],
                "origChecksum": struct.unpack(">I", infile.read(4))[0],
            }
        )
        offset += 4 * 4

    for entry in table_directory_entries:
        outfile.write(struct.pack(">I", entry["tag"]))
        outfile.write(struct.pack(">I", entry["origChecksum"]))
        outfile.write(struct.pack(">I", offset))
        outfile.write(struct.pack(">I", entry["origLength"]))
        entry["outOffset"] = offset
        offset += entry["origLength"]
        if (offset % 4) != 0:
            offset += 4 - (offset % 4)

    for entry in table_directory_entries:
        infile.seek(entry["offset"])
        compressed_data = infile.read(entry["compLength"])

        if entry["compLength"] != entry["origLength"]:
            uncompressed_data = zlib.decompress(compressed_data)
        else:
            uncompressed_data = compressed_data

        outfile.seek(entry["outOffset"])
        outfile.write(uncompressed_data)
        offset = entry["outOffset"] + entry["origLength"]
        padding = 0
        if (offset % 4) != 0:
            padding = 4 - (offset % 4)
        outfile.write(bytearray(padding))


def rename_fontname(fontfilepath: str, new_fontname: str) -> None:
    """Rename the font family and style in the font's name table."""
    font = TTFont(fontfilepath)
    namerecord_list = font["name"].names

    def get_style() -> str:
        # determine font style for this file path from name record nameID 2
        for record in namerecord_list:
            if record.nameID == 2:
                return str(record)
        return ""

    style = get_style()
    if len(style) == 0:
        sys.stderr.write(
            f"Unable to detect the font style from the OpenType name table in '{fontfilepath}'."
        )
        return

    # used for the Postscript name in the name table (no spaces allowed)
    postscript_font_name = new_fontname.replace(" ", "")
    # font family name
    name_id1_string = new_fontname
    name_id16_string = new_fontname
    # full font name
    name_id4_string = f"{new_fontname} {style}"
    # Postscript name
    # - no spaces allowed in family name or the PostScript suffix. should be dash delimited
    name_id6_string = f"{postscript_font_name}-{style.replace(' ', '')}"

    # modify the opentype table data in memory with updated values
    for record in namerecord_list:
        if record.nameID == 1:
            record.string = name_id1_string
        elif record.nameID == 4:
            record.string = name_id4_string
        elif record.nameID == 6:
            record.string = name_id6_string
        elif record.nameID == 16:
            record.string = name_id16_string

    # write changes to the font file
    try:
        font.save(fontfilepath)
    except Exception as e:
        sys.stderr.write(
            f"ERROR: Unable to write new name to OpenType name table for '{fontfilepath}': {e}."
        )


def main() -> int:
    """Download, convert, and rename MathJax WOFF fonts to OTF format."""
    for family, src_filename in SRC_MAP.items():
        dst_filename = src_filename.split(".")[0] + ".otf"
        src_url = f"{BASE_URL}/{src_filename}"
        print(f'font: "{dst_filename}" <== "{src_url}"')

        with io.BytesIO(urlopen(src_url).read()) as src:
            with open(dst_filename, mode="wb") as dst:
                convert_streams(src, dst)
            rename_fontname(dst_filename, family)

    return 0


# MAIN
if __name__ == "__main__":
    sys.exit(main())
