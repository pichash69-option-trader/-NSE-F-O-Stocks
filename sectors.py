# -*- coding: utf-8 -*-
"""
sectors.py — curated symbol → sector mapping for the NSE F&O universe.

Static (no extra data fetch). Covers the well-known F&O stocks; anything not
listed falls back to "Other". Sectors are broad/macro groupings for the Sector
view — not exact NSE industry codes. Edit freely as the F&O list changes.
"""

SECTORS = {
    "Banking": [
        "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
        "BANKBARODA", "PNB", "FEDERALBNK", "IDFCFIRSTB", "AUBANK", "BANDHANBNK",
        "RBLBANK", "CANBK", "INDIANB", "BANKINDIA", "UNIONBANK", "IDFC", "YESBANK",
    ],
    "Financials (NBFC/Insurance/Mkt)": [
        "BAJFINANCE", "BAJAJFINSV", "HDFCLIFE", "SBILIFE", "ICICIPRULI", "ICICIGI",
        "SBICARD", "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM", "LICHSGFIN", "PFC",
        "RECLTD", "IRFC", "HUDCO", "SHRIRAMFIN", "ABCAPITAL", "360ONE", "ANGELONE",
        "BSE", "MCX", "CDSL", "KFINTECH", "POLICYBZR", "PAYTM", "JIOFIN", "IEX",
        "HDFCAMC", "NAM-INDIA", "LICI", "IIFL", "POONAWALLA", "L&TFH", "M&MFIN",
        "SAMMAANCAP", "PEL", "BAJAJHLDNG", "CAMS", "IREDA", "LTF",
        "MFSL", "NUVAMA", "PNBHOUSING", "MOTILALOFS",
    ],
    "IT": [
        "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "LTTS", "PERSISTENT",
        "COFORGE", "MPHASIS", "OFSS", "KPITTECH", "TATATECH", "CYIENT", "BSOFT",
        "TATAELXSI", "ZENSARTECH",
    ],
    "Auto & Ancillary": [
        "MARUTI", "M&M", "TATAMOTORS", "TMPV", "BAJAJ-AUTO", "HEROMOTOCO",
        "EICHERMOT", "TVSMOTOR", "ASHOKLEY", "BOSCHLTD", "MOTHERSON", "BHARATFORG",
        "TIINDIA", "BALKRISIND", "MRF", "APOLLOTYRE", "EXIDEIND", "SONACOMS",
        "UNOMINDA", "ESCORTS", "FORCEMOT", "HYUNDAI",
    ],
    "Pharma & Healthcare": [
        "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "LUPIN", "AUROPHARMA", "ALKEM",
        "TORNTPHARM", "ZYDUSLIFE", "BIOCON", "GLENMARK", "LAURUSLABS", "GRANULES",
        "ABBOTINDIA", "IPCALAB", "SYNGENE", "PPLPHARMA", "MANKIND", "APOLLOHOSP",
        "MAXHEALTH", "FORTIS", "LALPATHLAB", "METROPOLIS", "JBCHEPHARM",
    ],
    "FMCG": [
        "HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "GODREJCP",
        "MARICO", "COLPAL", "TATACONSUM", "VBL", "UBL", "UNITDSPR", "PGHH",
        "EMAMILTD", "RADICO", "MCDOWELL-N", "PATANJALI",
    ],
    "Metals & Mining": [
        "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "SAIL", "NMDC",
        "NATIONALUM", "HINDCOPPER", "JSL", "APLAPOLLO", "HINDZINC", "RATNAMANI",
        "COALINDIA",
    ],
    "Oil & Gas": [
        "RELIANCE", "ONGC", "IOC", "BPCL", "HPCL", "GAIL", "OIL", "PETRONET",
        "IGL", "MGL", "GUJGASLTD", "ATGL", "GSPL", "HINDPETRO",
    ],
    "Power & Utilities": [
        "NTPC", "POWERGRID", "TATAPOWER", "ADANIPOWER", "ADANIGREEN", "ADANIENSOL",
        "JSWENERGY", "NHPC", "SJVN", "TORNTPOWER", "CESC", "POWERINDIA",
    ],
    "Cement": [
        "ULTRACEMCO", "SHREECEM", "AMBUJACEM", "ACC", "DALBHARAT", "JKCEMENT",
        "RAMCOCEM", "INDIACEM",
    ],
    "Capital Goods & Infra": [
        "LT", "SIEMENS", "ABB", "BHEL", "BEL", "HAL", "BDL", "CGPOWER", "THERMAX",
        "CUMMINSIND", "POLYCAB", "HAVELLS", "KEI", "SUZLON", "INOXWIND", "KAYNES",
        "NCC", "IRB", "RVNL", "IRCON", "KEC", "GMRAIRPORT", "GMRINFRA", "TITAGARH",
        "ADANIPORTS", "CONCOR", "DELHIVERY", "MAZDOCK", "COCHINSHIP", "GESHIP",
        "GRINDWELL", "CARBORUNIV", "PREMIERENE", "WAAREEENER", "GRAVITA",
        "GVT&D", "NBCC", "SOLARINDS",
    ],
    "Chemicals & Fertilizers": [
        "PIDILITIND", "SRF", "DEEPAKNTR", "AARTIIND", "TATACHEM", "PIIND",
        "NAVINFLUOR", "ATUL", "COROMANDEL", "CHAMBLFERT", "GNFC", "UPL", "SUMICHEM",
        "FLUOROCHEM", "VMM",
    ],
    "Paints": ["ASIANPAINT", "BERGEPAINT", "KANSAINER", "AKZOINDIA"],
    "Consumer & Retail": [
        "TITAN", "DMART", "AVENUE", "TRENT", "ABFRL", "PAGEIND", "VOLTAS", "DIXON",
        "WHIRLPOOL", "CROMPTON", "BATAINDIA", "RELAXO", "JUBLFOOD", "DEVYANI",
        "VEDANTFASHIONS", "METROBRAND", "BLUESTARCO", "AMBER", "PGEL", "HONASA",
        "KALYANKJIL", "ASTRAL", "SUPREMEIND", "GODFRYPHLP", "SWIGGY",
        "NAUKRI", "NYKAA",
        "ETERNAL",
    ],
    "Telecom & Media": [
        "BHARTIARTL", "IDEA", "INDUSTOWER", "TATACOMM", "HFCL", "ZEEL", "SUNTV",
        "PVRINOX", "NAZARA", "SAREGAMA",
    ],
    "Realty": [
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "PHOENIXLTD", "LODHA",
        "BRIGADE", "SOBHA",
    ],
    "Diversified / Other": [
        "ADANIENT", "GRASIM", "IRCTC", "INDHOTEL", "CHALET", "DELTACORP", "INDIGO",
    ],
}

# invert: symbol -> sector
SECTOR_OF = {sym: sec for sec, syms in SECTORS.items() for sym in syms}


def sector_of(symbol):
    """Return the macro-sector for a symbol (or 'Other' if unmapped)."""
    return SECTOR_OF.get(symbol, "Other")
