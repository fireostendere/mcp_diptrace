import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.operations import SetComponentPropertiesOperation
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

PATH = Path(__file__).with_name("attiny85-arduino-clone.dchxml")

PARTS = {
    "U1": ("Microchip Technology", "ATTINY85-20SU", "C89852"),
    "U2": ("Silicon Labs", "CP2102-GM", "C430012"),
    "U3": ("Texas Instruments", "TPS63802DLAR", "C2845237"),
    "J1": ("Amphenol FCI", "10118194-0001LF", "C132563"),
    "J2": ("Generic", "HDR-2x3", ""),
    "J3": ("Generic", "HDR-2x4", ""),
    "L1": ("Coilcraft", "XFL4015-471MEC", "C18221164"),
    "R1": ("Yageo", "RC0402FR-07511KL", "C163461"),
    "R2": ("Uniroyal Elec", "0402WGF9102TCE", "C4147"),
    "R3": ("Uniroyal Elec", "0402WGF1003TCE", "C25741"),
    "R4": ("Uniroyal Elec", "0402WGF4702TCE", "C25792"),
    "R5": ("Uniroyal Elec", "0402WGF2402TCE", "C25769"),
    "R6": ("Uniroyal Elec", "0402WGF1002TCE", "C25744"),
    "C1": ("Samsung Electro-Mechanics", "CL10A106KP8NNNC", "C19702"),
    "C2": ("Samsung Electro-Mechanics", "CL21A226MAQNNNE", "C45783"),
    "C3": ("Samsung Electro-Mechanics", "CL05A105KA5NQNC", "C52923"),
    "C4": ("FH", "0402B104K160NT", "C41851"),
    "C5": ("FH", "0402B104K160NT", "C41851"),
    "C6": ("FH", "0402B104K160NT", "C41851"),
}


def main() -> None:
    document = DipTraceDocument.load(PATH, 10_000_000)
    operations = []
    for refdes, (manufacturer, mpn, lcsc) in PARTS.items():
        fields = {"Manufacturer": manufacturer, "MPN": mpn}
        if lcsc:
            fields["LCSC"] = lcsc
        operations.append(
            SetComponentPropertiesOperation(
                selector=QuerySelector(refdes=[refdes]),
                fields=fields,
            )
        )
    result = apply_semantic_operations(document, operations)
    root = ET.fromstring(result.raw_bytes)
    parts = {
        part.findtext("./RefDes"): part for part in root.findall("./Schematic/Components/Part")
    }
    for refdes in ("C5", "C6"):
        assert parts[refdes].findtext("./Name") == parts["C4"].findtext("./Name")
        parts[refdes].set("ComponentStyle", parts["C4"].get("ComponentStyle", ""))
    PATH.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"updated {len(PARTS)} parts; sha256={DipTraceDocument.load(PATH, 10_000_000).sha256}")


if __name__ == "__main__":
    main()
