import argparse
import sys
from pathlib import Path

from metadata_assessment import assess_xml_file


ISO_NS_BYTES = (
    b"http://www.isotc211.org/2005/gmd",
    b"http://www.isotc211.org/2005/gco",
    b"http://www.isotc211.org/2005/srv",
)

DCAT_INDICATORS = (
    b"http://www.w3.org/ns/dcat#",
    b"<dcat:catalog",
    b"<dcat:dataset",
)


def detect_format(xml_bytes: bytes) -> str:
    """Detect whether the metadata is ISO 19139 or DCAT RDF/XML."""
    lowered = xml_bytes.lower()

    if sum(namespace in lowered for namespace in ISO_NS_BYTES) >= 2:
        return "iso"

    if any(indicator in lowered for indicator in DCAT_INDICATORS):
        return "dcat"

    return "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate ISO 19139 or DCAT metadata "
            "using the SPALOD metadata assessment."
        )
    )

    parser.add_argument(
        "metadata_file",
        type=Path,
        help="Path to an ISO 19139 or DCAT RDF/XML metadata file.",
    )

    parser.add_argument(
        "--data",
        type=Path,
        help=(
            "Optional dataset file (JSON/GeoJSON) used as "
            "additional evidence during evaluation."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata_path = args.metadata_file
    data_path = args.data

    # Validate metadata file
    if not metadata_path.exists():
        print(
            f"Error: File not found: {metadata_path}",
            file=sys.stderr,
        )
        return 1

    if not metadata_path.is_file():
        print(
            f"Error: Not a file: {metadata_path}",
            file=sys.stderr,
        )
        return 1

    # Validate optional dataset file
    if data_path is not None:
        if not data_path.exists():
            print(
                f"Error: Dataset file not found: {data_path}",
                file=sys.stderr,
            )
            return 1

        if not data_path.is_file():
            print(
                f"Error: Dataset path is not a file: {data_path}",
                file=sys.stderr,
            )
            return 1

    # Read metadata
    try:
        xml_bytes = metadata_path.read_bytes()
    except OSError as exc:
        print(
            f"Error: Could not read file: {exc}",
            file=sys.stderr,
        )
        return 1

    # Detect metadata format
    metadata_format = detect_format(xml_bytes)

    if metadata_format == "unknown":
        print(
            "Error: Unsupported metadata format. "
            "Expected ISO 19139 or DCAT RDF/XML.",
            file=sys.stderr,
        )
        return 1

    print(f"Metadata file: {metadata_path}")
    print(f"Detected format: {metadata_format.upper()}")

    # ISO evaluation
    if metadata_format == "iso":
        try:
            result = assess_xml_file(
                metadata_path,
                data_path=data_path,
            )
        except Exception as exc:
            print(
                f"Error: Could not evaluate metadata: {exc}",
                file=sys.stderr,
            )
            return 1

        print()
        print("Metadata Evaluation")
        print("-------------------")
        print(f"Dataset: {result.dataset}")
        print(f"Scope: {result.scope}")
        print(f"LETTER: {result.letter_code}")
        print(f"Stars: {result.star_range}")
        print()

        for letter, decision in result.letters.items():
            status = "PASS" if decision["passed"] else "FAIL"
            print(f"{letter}: {status}")
            print(f"   {decision['reason']}")

        return 0

    if metadata_format == "dcat":
        print()
        print("DCAT metadata detected.")
        return 0

    return 1

if __name__ == "__main__":
    raise SystemExit(main())