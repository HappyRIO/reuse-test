"""Known pubkey-exposed puzzle targets (easy order for BSGS)."""
from __future__ import annotations

# Compressed pubkeys for unsolved puzzles with on-chain exposed keys.
PUZZLES: dict[int, dict[str, str]] = {
    140: {
        "pubkey": "031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640",
        "address": "1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo",
    },
    145: {
        "pubkey": "03afdda497369e219a2c1c369954a930e4d3740968e5e4352475bcffce3140dae5",
        "address": "19GpszRNUej5yYqxXoLnbZWKew3KdVLkXg",
    },
    150: {
        "pubkey": "03137807790ea7dc6e97901c2bc87411f45ed74a5629315c4e4b03a0a102250c49",
        "address": "",
    },
    155: {
        "pubkey": "035cd1854cae45391ca4ec428cc7e6c7d9984424b954209a8eea197b9e364c05f6",
        "address": "1AoeP37TmHdFh8uN72fu9AqgtLrUwcv2wJ",
    },
    160: {
        "pubkey": "02e0a8b039282faf6fe0fd769cfbc4b6b4cf8758ba68220eac420e32b91ddfa673",
        "address": "1NBC8uXJy1GiJ6drkiZa1WuKn51ps7EPTv",
    },
}


def list_puzzles() -> list[int]:
    return sorted(PUZZLES)


def get_puzzle(bits: int) -> dict[str, str] | None:
    return PUZZLES.get(int(bits))
