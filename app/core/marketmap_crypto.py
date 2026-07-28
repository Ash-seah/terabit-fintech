"""Crypto market-map tiles with logos, categories, and approx market caps."""

from __future__ import annotations

from app.core.marketmap_common import MarketMapAsset

_ICON = "https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/{slug}.png"


def _crypto(
    symbol: str,
    name: str,
    description: str,
    sector: str,
    market_cap: float,
    icon_slug: str | None = None,
) -> MarketMapAsset:
    slug = icon_slug or symbol.split("-", 1)[0].lower()
    return MarketMapAsset(
        symbol=symbol,
        name=name,
        description=description,
        sector=sector,
        market_cap=market_cap,
        logo=_ICON.format(slug=slug),
    )


MARKETMAP_CRYPTO: tuple[MarketMapAsset, ...] = (
    _crypto("BTC-USD", "Bitcoin", "Largest cryptocurrency by market cap; digital store of value.", "Bitcoin", 1.3e12, "btc"),
    _crypto("ETH-USD", "Ethereum", "Smart-contract platform and DeFi settlement layer.", "Ethereum", 4.0e11, "eth"),
    _crypto("BNB-USD", "BNB", "BNB Chain gas token and Binance utility asset.", "Layer 1", 9.0e10, "bnb"),
    _crypto("SOL-USD", "Solana", "High-throughput Layer 1 for DeFi and consumer apps.", "Layer 1", 8.0e10, "sol"),
    _crypto("XRP-USD", "XRP", "Cross-border payments token (Ripple).", "Layer 1", 1.4e11, "xrp"),
    _crypto("ADA-USD", "Cardano", "Proof-of-stake Layer 1 focused on research-driven design.", "Layer 1", 2.5e10, "ada"),
    _crypto("AVAX-USD", "Avalanche", "Subnet-capable Layer 1 for DeFi and enterprises.", "Layer 1", 1.4e10, "avax"),
    _crypto("DOT-USD", "Polkadot", "Multi-chain interoperability protocol.", "Layer 1", 1.0e10, "dot"),
    _crypto("TON-USD", "Toncoin", "Telegram-adjacent Layer 1 blockchain.", "Layer 1", 1.8e10, "ton"),
    _crypto("TRX-USD", "TRON", "High-throughput chain popular for stablecoin settlement.", "Layer 1", 2.2e10, "trx"),
    _crypto("NEAR-USD", "NEAR", "Us-friendly sharded Layer 1.", "Layer 1", 6.0e9, "near"),
    _crypto("APT-USD", "Aptos", "Move-based Layer 1 from Meta alumni.", "Layer 1", 5.5e9, "apt"),
    _crypto("SUI-USD", "Sui", "Move-based Layer 1 optimized for parallel execution.", "Layer 1", 1.0e10, "sui"),
    _crypto("ATOM-USD", "Cosmos", "IBC hub for interoperable app chains.", "Layer 1", 3.5e9, "atom"),
    _crypto("ICP-USD", "Internet Computer", "On-chain compute / web services network.", "Layer 1", 4.0e9, "icp"),
    _crypto("HBAR-USD", "Hedera", "Hashgraph public network for enterprise use cases.", "Layer 1", 8.0e9, "hbar"),
    _crypto("ALGO-USD", "Algorand", "Pure proof-of-stake Layer 1.", "Layer 1", 2.0e9, "algo"),
    _crypto("XTZ-USD", "Tezos", "Self-amending proof-of-stake Layer 1.", "Layer 1", 1.2e9, "xtz"),
    _crypto("EOS-USD", "EOS", "Delegated proof-of-stake smart-contract chain.", "Layer 1", 8.0e8, "eos"),
    _crypto("ETC-USD", "Ethereum Classic", "Original Ethereum chain after the DAO fork.", "Layer 1", 3.0e9, "etc"),
    _crypto("BCH-USD", "Bitcoin Cash", "Bitcoin fork focused on larger blocks / payments.", "Layer 1", 1.0e10, "bch"),
    _crypto("LTC-USD", "Litecoin", "Early Bitcoin-like payments coin.", "Layer 1", 6.0e9, "ltc"),
    _crypto("XLM-USD", "Stellar", "Fast cross-border payment network.", "Layer 1", 1.0e10, "xlm"),
    _crypto("SEI-USD", "Sei", "Trading-focused Layer 1.", "Layer 1", 2.0e9, "sei"),
    _crypto("KAS-USD", "Kaspa", "BlockDAG proof-of-work Layer 1.", "Layer 1", 3.0e9, "kas"),
    _crypto("STX-USD", "Stacks", "Smart contracts and apps anchored to Bitcoin.", "Layer 1", 2.5e9, "stx"),
    _crypto("USDT-USD", "Tether", "Largest USD-pegged stablecoin.", "Stablecoin", 1.2e11, "usdt"),
    _crypto("USDC-USD", "USD Coin", "Regulated USD stablecoin from Circle.", "Stablecoin", 3.5e10, "usdc"),
    _crypto("LINK-USD", "Chainlink", "Decentralized oracle network.", "DeFi", 1.0e10, "link"),
    _crypto("UNI-USD", "Uniswap", "Leading decentralized exchange governance token.", "DeFi", 6.0e9, "uni"),
    _crypto("AAVE-USD", "Aave", "Decentralized lending protocol token.", "DeFi", 3.0e9, "aave"),
    _crypto("MKR-USD", "Maker", "Governance token of the MakerDAO / DAI system.", "DeFi", 1.5e9, "mkr"),
    _crypto("RUNE-USD", "THORChain", "Cross-chain liquidity protocol.", "DeFi", 1.2e9, "rune"),
    _crypto("JUP-USD", "Jupiter", "Solana DEX aggregator token.", "DeFi", 2.5e9, "jup"),
    _crypto("PYTH-USD", "Pyth", "High-frequency oracle network.", "DeFi", 2.0e9, "pyth"),
    _crypto("INJ-USD", "Injective", "DeFi / exchange-focused Layer 1.", "DeFi", 2.2e9, "inj"),
    _crypto("ARB-USD", "Arbitrum", "Ethereum optimistic rollup token.", "Infrastructure", 3.5e9, "arb"),
    _crypto("OP-USD", "Optimism", "Ethereum optimistic rollup token.", "Infrastructure", 2.5e9, "op"),
    _crypto("POL-USD", "Polygon", "Ethereum scaling and AggLayer ecosystem token.", "Infrastructure", 4.0e9, "matic"),
    _crypto("FIL-USD", "Filecoin", "Decentralized storage network.", "Infrastructure", 2.5e9, "fil"),
    _crypto("GRT-USD", "The Graph", "Indexing protocol for blockchain data.", "Infrastructure", 1.5e9, "grt"),
    _crypto("RENDER-USD", "Render", "Distributed GPU rendering network.", "Infrastructure", 3.0e9, "rndr"),
    _crypto("FET-USD", "ASI", "Artificial Superintelligence Alliance token.", "Infrastructure", 2.0e9, "fet"),
    _crypto("TAO-USD", "Bittensor", "Decentralized machine-learning network.", "Infrastructure", 4.5e9, "tao"),
    _crypto("TIA-USD", "Celestia", "Modular data-availability network.", "Infrastructure", 2.0e9, "tia"),
    _crypto("THETA-USD", "Theta", "Decentralized video delivery network.", "Infrastructure", 1.3e9, "theta"),
    _crypto("IMX-USD", "Immutable", "Gaming / NFT scaling for Ethereum.", "Infrastructure", 2.0e9, "imx"),
    _crypto("FLOW-USD", "Flow", "Consumer / NFT focused blockchain.", "Infrastructure", 1.0e9, "flow"),
    _crypto("VET-USD", "VeChain", "Supply-chain enterprise blockchain.", "Infrastructure", 2.2e9, "vet"),
    _crypto("EGLD-USD", "MultiversX", "Sharded smart-contract platform.", "Infrastructure", 1.4e9, "egld"),
    _crypto("FTM-USD", "Fantom", "Lachesis-based smart-contract platform.", "Infrastructure", 1.0e9, "ftm"),
    _crypto("WLD-USD", "Worldcoin", "Identity / UBI project token.", "Infrastructure", 2.5e9, "wld"),
    _crypto("DOGE-USD", "Dogecoin", "Original meme coin; payments community token.", "Meme", 2.5e10, "doge"),
    _crypto("SHIB-USD", "Shiba Inu", "Ethereum-based meme / ecosystem token.", "Meme", 1.2e10, "shib"),
    _crypto("PEPE-USD", "Pepe", "Popular frog-themed meme token.", "Meme", 5.0e9, "pepe"),
    _crypto("WIF-USD", "dogwifhat", "Solana meme coin.", "Meme", 2.0e9, "wif"),
    _crypto("BONK-USD", "Bonk", "Solana community meme coin.", "Meme", 1.8e9, "bonk"),
    _crypto("FLOKI-USD", "FLOKI", "Meme / utility community token.", "Meme", 1.5e9, "floki"),
    _crypto("SAND-USD", "Sandbox", "Metaverse / gaming land platform.", "Meme", 1.2e9, "sand"),
    _crypto("MANA-USD", "Decentraland", "Virtual-world LAND / MANA ecosystem.", "Meme", 8.0e8, "mana"),
    _crypto("AXS-USD", "Axie Infinity", "Play-to-earn gaming ecosystem token.", "Meme", 1.0e9, "axs"),
)


def marketmap_crypto() -> tuple[MarketMapAsset, ...]:
    return MARKETMAP_CRYPTO
