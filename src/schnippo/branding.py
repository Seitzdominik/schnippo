"""Names, links and brand files in ONE place: the bundle build, server, cards, setup texts and the update check read them."""

from pathlib import Path

DISPLAY_NAME = "Schnippo"
SLUG = "schnippo"  # technical id: bundle name, cache folder, MCP server name; change only with a migration
TAGLINE = "KI-Rohschnitt für DaVinci Resolve"
TRADEMARK = "DaVinci Resolve ist eine Marke von Blackmagic Design. Schnippo ist ein unabhängiges Projekt und nicht mit Blackmagic Design verbunden."
AUTHOR = "Seitz Dominik Visuals"
AUTHOR_URL = "https://sdv.design"
HOMEPAGE = "https://schnippo.com"
REPOSITORY = "https://github.com/Seitzdominik/schnippo"
REPO_SLUG = "Seitzdominik/schnippo"
SUPPORT_URL = REPOSITORY + "/issues"  # later schnippo.com: change here only
DOCS_URL = REPOSITORY + "#readme"
RELEASES_URL = REPOSITORY + "/releases/latest"
PRIVACY_URL = HOMEPAGE + "/privacy"

LEGACY_SLUG = "resolve-cut"  # the working title: old folders stay readable
LEGACY_EXPORT = "resolve-cut-export"


def brand_file(name: str, placeholder: Path | None = None) -> Path | None:
    """assets/brand/<name>, or the placeholder as long as the real file is not there."""
    f = Path(__file__).resolve().parents[2] / "assets" / "brand" / name
    return f if f.is_file() else placeholder
