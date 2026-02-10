"""CRM Sales Bot canonical package namespace."""

from src.import_aliases import install_legacy_import_aliases

# Install compatibility aliases early to prevent duplicate module identities.
install_legacy_import_aliases()
